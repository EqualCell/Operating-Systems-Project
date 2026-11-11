"""All tunable policy in one place (so it is easy to explain and to change)."""

# Files the agent may APPEND to / the only place it may CREATE files.
# Everything else is read-only for the agent (least privilege).
WRITABLE_PATHS = ("/log.txt", "/notes.txt")

# Largest text the agent may send in one append/create. The kernel allows 256
# bytes; the console line buffer of xv6 is 128 bytes, and the payload travels
# hex-encoded (2 chars/byte), so 32 bytes is what safely fits on one line.
MAX_TEXT = 32

# Guest paths: one leading '/', then 1..30 characters of [A-Za-z0-9._-].
# (xv6 root directory only; no sub-directories, no "..", no spaces.)
PATH_REGEX = r"^/[A-Za-z0-9._-]{1,30}$"

# Cap on text handed to the host-side summarize tool.
MAX_SUMMARY_INPUT = 2048

# Timeouts (seconds)
BOOT_TIMEOUT = 60
CALL_TIMEOUT = 15

# How many times the agent re-sends an effect whose outcome is unknown
# (always with the SAME key and SAME arguments) before giving up as PENDING.
MAX_ATTEMPTS = 3
