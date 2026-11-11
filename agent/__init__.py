"""Host-side agent for the xv6 exactly-once effect project.

Layers (each in its own file, top to bottom):
    planner.py  user goal  -> structured tool call      ("rules first, LLM later")
    tools.py    tool call  -> VALIDATED tool call       (allowlist + schema)
    agent.py    runs the loop, keeps the audit trace, retries with the SAME key
    journal.py  durable record of side-effecting requests (key + arguments)
    bridge.py   validated call -> fixed guest command -> framed reply
    qemu.py     boots xv6, types on its serial console
"""
