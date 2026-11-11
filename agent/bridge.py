"""The host -> guest BRIDGE (documented in docs/bridge.md).

Method chosen: serial-console interaction with ONE fixed guest program,
`agentcall`, instead of free-form shell text.

    validated tool call --build_command()--> "agentcall 17 read /report.txt"
    xv6 echoes the line, runs it, and prints a FRAMED reply:
        @@BEGIN 17
        | The server handled 100 requests.
        @@END 17 rc=34 status=OK
    parse_reply() extracts the body and result.

Safety properties
  * Only commands built here by build_command() are ever sent: fixed templates,
    each argument already validated by tools.validate_action(); the payload is
    hex-encoded so no shell metacharacter can matter. There is no eval and no
    host shell anywhere.
  * Every reply is matched on its attempt id (a different thing from the
    effect key!), so a stale or forged frame is not accepted as the answer.
  * Anything that is not a complete, well-formed frame -- timeout, kernel panic,
    garbage, missing @@END -- is reported as UNKNOWN. We never invent success.
    (UNKNOWN is NOT "failed": the effect may or may not have happened. Only a
    retry with the same key can find out.)
"""
import re
import time

from . import config
from .qemu import VM


class GuestReply:
    """status: OK (guest said rc >= 0) | ERR (guest/kernel refused: definitive)
               | UNKNOWN (no complete reply: outcome unknown)"""

    def __init__(self, status, rc=None, guest_status="", body=None, raw="", reason="", comm_id=None):
        self.status = status
        self.rc = rc
        self.guest_status = guest_status
        self.body = body or []
        self.raw = raw
        self.reason = reason
        self.comm_id = comm_id

    @property
    def text(self):
        return "\n".join(self.body)

    @property
    def outcome(self):
        """EXECUTED / REPLAYED for effects (parsed from the EFFECT line)."""
        for ln in self.body:
            m = re.match(r"EFFECT op=\w+ key=\S+ rc=-?\d+ outcome=(\w+)", ln)
            if m:
                return m.group(1)
        return None

    def as_dict(self):
        return dict(status=self.status, rc=self.rc, guest_status=self.guest_status,
                    body=self.body, reason=self.reason, comm_id=self.comm_id,
                    outcome=self.outcome)


MAX_LINE = 120  # xv6 console line buffer is 128 bytes


def build_command(comm_id, tool, args, key=None):
    """Fixed templates. `args` must already be validated."""
    if tool == "list_files":
        line = f"agentcall {comm_id} list"
    elif tool == "read_file":
        line = f"agentcall {comm_id} read {args['path']}"
    elif tool in ("append_file", "create_file"):
        if key is None:
            raise ValueError("side-effecting tools need an idempotency key")
        verb = "append" if tool == "append_file" else "create"
        line = f"agentcall {comm_id} {verb} {key:x} {args['path']} {args['text'].encode().hex()}"
    else:
        raise ValueError(f"tool {tool!r} has no guest command")
    if len(line) >= MAX_LINE:
        raise ValueError(f"guest command too long ({len(line)} >= {MAX_LINE})")
    return line


def parse_reply(output, comm_id):
    """Parse the console text produced by one command. Never raises."""
    lines = output.split("\n")
    begin = f"@@BEGIN {comm_id}"
    try:
        b = lines.index(begin)
    except ValueError:
        return GuestReply("UNKNOWN", raw=output, reason="no @@BEGIN frame for this attempt id", comm_id=comm_id)
    end_re = re.compile(rf"^@@END {comm_id} rc=(-?\d+) status=(\S+)$")
    for i in range(b + 1, len(lines)):
        m = end_re.match(lines[i])
        if m:
            body = [ln[2:] for ln in lines[b + 1:i] if ln.startswith("| ")]
            rc = int(m.group(1))
            return GuestReply("OK" if rc >= 0 else "ERR", rc=rc, guest_status=m.group(2),
                              body=body, raw=output, comm_id=comm_id)
    return GuestReply("UNKNOWN", raw=output, reason="@@BEGIN seen but no @@END (incomplete reply)", comm_id=comm_id)


class GuestBridge:
    def __init__(self, img, kernel=None, cpus=1, log_dir=None, call_timeout=config.CALL_TIMEOUT):
        self.img = img
        self.kernel = kernel
        self.cpus = cpus
        self.log_dir = log_dir
        self.call_timeout = call_timeout
        self.vm = None
        self.boots = 0
        self._next_id = 100
        self.drop_replies = 0          # TEST-ONLY fault injection: lose the next N replies
        self.needs_restart = False
        self.history = []              # every command + raw output (evidence)

    # ---- lifecycle ----
    def start(self):
        self.boots += 1
        log = None
        if self.log_dir:
            import os
            os.makedirs(self.log_dir, exist_ok=True)
            log = os.path.join(self.log_dir, f"qemu-boot{self.boots}.log")
        self.vm = VM(self.img, kernel=self.kernel, cpus=self.cpus, log_path=log)
        self.vm.boot(timeout=config.BOOT_TIMEOUT)
        self.needs_restart = False
        return self

    def stop(self):
        if self.vm:
            self.vm.kill()

    def restart(self):
        """Power-cycle the guest on the SAME disk image (crash recovery runs at boot)."""
        self.stop()
        return self.start()

    def recover(self):
        if self.needs_restart or self.vm is None or self.vm.proc.poll() is not None:
            self.restart()

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()

    # ---- the one entry point ----
    def call(self, tool, args, key=None):
        comm_id = self._next_id
        self._next_id += 1
        line = build_command(comm_id, tool, args, key)
        return self._send(comm_id, line)

    def _send_raw_for_tests(self, line):
        """TEST-ONLY: send an arbitrary line (used to prove the guest refuses
        commands outside its allowlist). The agent never calls this."""
        comm_id = self._next_id
        self._next_id += 1
        return self._send(comm_id, line.replace("@ID@", str(comm_id)))

    def _send(self, comm_id, line):
        t0 = time.time()
        out, status = self.vm.run(line, timeout=self.call_timeout)
        if status != "ok":
            self.needs_restart = True
            reply = GuestReply("UNKNOWN", raw=out, comm_id=comm_id,
                               reason=f"guest {status} (no prompt returned): outcome unknown")
        elif self.drop_replies > 0:
            self.drop_replies -= 1
            reply = GuestReply("UNKNOWN", raw="", comm_id=comm_id,
                               reason="reply lost (injected fault): outcome unknown")
        else:
            reply = parse_reply(out, comm_id)
        self.history.append(dict(comm_id=comm_id, sent=line, raw=out, vm_status=status,
                                 reply=reply.as_dict(), seconds=round(time.time() - t0, 3)))
        return reply
