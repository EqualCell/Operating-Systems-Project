#!/bin/sh
# Build the submission ZIP: ONLY files added or modified relative to the xv6
# base commit (as the course handout requires), plus the evidence summary.
#   tools/make_zip.sh Team_Name_4        ->  ../Team_Name_4.zip
set -e
cd "$(dirname "$0")/.."
NAME="${1:-Team_Name_4}"
LIST=$(mktemp)
{ git diff --name-only; git ls-files --others --exclude-standard; } | grep -v -E '^(runs/|build.log|fs.img)' | sort -u > "$LIST"
rm -f "../$NAME.zip"
zip -q "../$NAME.zip" -@ < "$LIST"
echo "$(wc -l < "$LIST") files -> ../$NAME.zip"
cat "$LIST"
rm -f "$LIST"
