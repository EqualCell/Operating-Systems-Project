"""
agent — Host-side deterministic bridge for xv6 effect system.

This package provides a Python host agent that communicates with xv6
running in QEMU over the serial console (PTY). It uses a deterministic
planner with allowlisted tools and durable request journals, and only
invokes the dedicated `effectctl` guest utility — never arbitrary shell
commands.
"""

__version__ = "0.1.0"

from agent.journal import RequestJournal
from agent.bridge import QEMUBridge
from agent.planner import DeterministicPlanner
from agent.tools import TOOL_REGISTRY

__all__ = [
    "RequestJournal",
    "QEMUBridge",
    "DeterministicPlanner",
    "TOOL_REGISTRY",
]
