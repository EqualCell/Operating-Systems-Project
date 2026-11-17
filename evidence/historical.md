# Historical deduplication-only evidence

The previous checked-in evidence/final run predates durable grants and this repair.
It reported 42 PASS, 0 FAIL, 0 ERROR, revision not recorded.
These are historical results, not validation of the present implementation.
The raw per-case logs, duplicate generated report and compressed disk images
were removed after checking test/tool references. Current tools generate new
logs and lossless block differences on demand; see ../docs/testing.md.

The original contributor history, MIT license, upstream README, fixtures,
test cases, mutation definitions and debugger inspection tools are retained.
