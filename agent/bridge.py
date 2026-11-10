"""
QEMUBridge — host-side serial transport to xv6 running in QEMU.

Responsibilities:
  - Spawn or attach to a QEMU process.
  - Frame / deframe BridgeMessages over the serial line.
  - Handle partial reads, timeouts, and correlation ID matching.
  - Detect guest crashes (EOF / unexpected disconnect).
  - Reject malformed or tainted input from the guest.

The bridge never interprets tool semantics — it only transports framed
messages.  Tool dispatch is the planner's job.
"""

from __future__ import annotations
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from agent.protocol import BridgeMessage, MsgType, MAX_LINE_BYTES


class QEMUBridge:
    """Manages the QEMU process and host↔guest serial communication."""

    # Sentinel the guest effectctl prints when ready for commands.
    READY_SENTINEL = "READY:"
    RESPONSE_SENTINEL = "RESPONSE:"
    ERROR_SENTINEL = "ERROR:"
    BOOT_SENTINEL = "BOOT:"

    def __init__(
        self,
        project_dir: str,
        timeout_seconds: float = 10.0,
        boot_timeout: float = 30.0,
    ):
        self.project_dir = project_dir
        self.timeout = timeout_seconds
        self.boot_timeout = boot_timeout
        self._proc: Optional[subprocess.Popen] = None
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._booted = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch QEMU and wait for boot + shell prompt."""
        self._proc = subprocess.Popen(
            ["make", "qemu"],
            cwd=self.project_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        os.set_blocking(self._proc.stdout.fileno(), False)
        # Wait for the xv6 shell prompt.
        self._wait_for_prompt(self.boot_timeout)
        self._booted = True

    def stop(self) -> None:
        """Terminate QEMU."""
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        self._booted = False

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def _raw_read(self, timeout: float) -> bytes:
        """Non-blocking read with timeout. Returns whatever is available."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = os.read(self._proc.stdout.fileno(), 4096)
                if chunk:
                    return chunk
            except (BlockingIOError, OSError):
                pass
            time.sleep(0.05)
        return b""

    def _raw_write(self, data: bytes) -> None:
        """Write to QEMU's stdin."""
        if not self._proc or not self._proc.stdin:
            raise ConnectionError("QEMU process not running")
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def _drain_until(self, sentinel: str, timeout: float) -> str:
        """Read output until a line containing `sentinel` appears.

        Returns all accumulated text.  Raises TimeoutError if the
        sentinel does not appear within `timeout` seconds.
        """
        deadline = time.time() + timeout
        accumulated = ""
        while time.time() < deadline:
            chunk = self._raw_read(min(0.5, deadline - time.time()))
            if chunk:
                text = chunk.decode("utf-8", errors="replace")
                accumulated += text
                if sentinel in accumulated:
                    return accumulated
            if not self.is_alive:
                raise ConnectionError("QEMU exited unexpectedly")
        raise TimeoutError(
            f"timed out waiting for {sentinel!r} after {timeout}s"
        )

    def _wait_for_prompt(self, timeout: float) -> None:
        """Wait for the xv6 shell '$' prompt."""
        self._drain_until("$ ", timeout)

    # ------------------------------------------------------------------
    # Command execution (fixed commands only)
    # ------------------------------------------------------------------

    def send_guest_command(self, command_line: str, correlation_id: str) -> str:
        """Send a single fixed command to the guest and wait for response.

        The command_line must be a pre-validated effectctl invocation.
        Returns the raw text output from the guest.

        Raises:
            TimeoutError: if the guest does not respond in time.
            ConnectionError: if QEMU dies.
            ValueError: if the response is malformed.
        """
        with self._lock:
            if not self.is_alive:
                raise ConnectionError("QEMU is not running")

            # Send the command.
            self._raw_write((command_line + "\n").encode("utf-8"))

            # Drain output until we see the shell prompt again.
            try:
                raw_output = self._drain_until("$ ", self.timeout)
            except TimeoutError:
                return f"CRASH:{correlation_id}:timeout after {self.timeout}s"

            # Extract the response portion.
            return self._extract_response(raw_output, correlation_id)

    def _extract_response(self, raw: str, correlation_id: str) -> str:
        """Parse structured response lines from raw guest output.

        Looks for lines matching our protocol framing.  Anything else
        is treated as untrusted observation text.
        """
        lines = raw.strip().split("\n")
        for line in lines:
            line = line.strip()
            # Look for protocol-framed responses.
            if line.startswith(self.RESPONSE_SENTINEL):
                try:
                    msg = BridgeMessage.decode(line.encode("utf-8"))
                    if msg.correlation_id == correlation_id:
                        return msg.payload
                except ValueError:
                    continue  # Malformed — skip.
            elif line.startswith(self.ERROR_SENTINEL):
                try:
                    msg = BridgeMessage.decode(line.encode("utf-8"))
                    if msg.correlation_id == correlation_id:
                        return f"ERROR:{msg.payload}"
                except ValueError:
                    continue

        # No protocol-framed response found — return raw output but mark
        # it as unstructured (the planner must treat this as tainted).
        return f"UNSTRUCTURED:{raw.strip()}"

    # ------------------------------------------------------------------
    # High-level tool dispatch
    # ------------------------------------------------------------------

    def invoke_tool(
        self, tool_name: str, guest_cmd: str, args_str: str, correlation_id: str
    ) -> str:
        """Build and send a fixed effectctl command.

        The command is always:  effectctl <subcommand> <correlation_id> <args...>

        Never runs arbitrary commands — only the effectctl utility with
        validated arguments.
        """
        cmd = f"effectctl {guest_cmd} {correlation_id} {args_str}"
        return self.send_guest_command(cmd, correlation_id)
