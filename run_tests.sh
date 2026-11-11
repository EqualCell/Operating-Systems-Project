#!/bin/sh
# One command: build everything, then run the full test suite and write evidence.
#   ./run_tests.sh            # all cases except the slow usertests regression
#   ./run_tests.sh --slow     # also run `usertests -q` (about a minute)
#   ./run_tests.sh --only B2 C1 ...
set -e
cd "$(dirname "$0")"
. ./env.sh
make -j8 kernel/kernel fs.img > build.log 2>&1 || { echo "BUILD FAILED, see build.log"; tail -20 build.log; exit 1; }
exec python3 tests/run_all.py "$@"
