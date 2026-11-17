#!/bin/sh
# Package the complete tracked source, licenses, fixtures and compact evidence.
# The archive is created inside runs/; never include build products or .git.
set -eu
cd "$(dirname "$0")/.."
name="${1:-Operating-Systems-Project}"
case "$name" in *[!A-Za-z0-9_-]*|'') echo 'Use a simple archive name' >&2; exit 2;; esac
mkdir -p runs
# git archive includes committed source (including executable modes), reproducibly.
git archive --format=zip --prefix="$name/" -o "runs/$name.zip" HEAD
printf '%s\n' "runs/$name.zip (committed source at $(git rev-parse --short HEAD))"
