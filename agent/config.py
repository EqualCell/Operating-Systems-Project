"""All tunable policy in one place (so it is easy to explain and to change)."""

# Files the agent may APPEND to / the only place it may CREATE files.
# This host allowlist supplements the kernel grant checks.
WRITABLE_PATHS = ("/log.txt", "/notes.txt")

# Largest text the agent may send in one append/create. The kernel allows 256
# bytes; the host intentionally limits planner payloads to 32 bytes. The console and
# shell buffers are 1024 bytes; hexadecimal transport avoids shell parsing.
MAX_TEXT = 32

# Guest paths: one leading '/', then 1..14 characters of [A-Za-z0-9._-].
# (xv6 root directory only; no sub-directories, no "..", no spaces.)
PATH_REGEX = r"^/[A-Za-z0-9._-]{1,14}$"

# Cap on text handed to the host-side summarize tool.
MAX_SUMMARY_INPUT = 2048

# Timeouts (seconds)
BOOT_TIMEOUT = 60
CALL_TIMEOUT = 15

# How many times the agent re-sends an effect whose outcome is unknown
# (always with the SAME key and SAME arguments) before giving up as PENDING.
MAX_ATTEMPTS = 3
