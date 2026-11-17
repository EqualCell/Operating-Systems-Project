#!/usr/bin/env python3
"""Generate compact, revision-bound evidence. Raw artifacts remain reproducible.
Usage: python3 tools/summarize.py evidence/run-ID [evidence/summary.md]
"""
import json
import sys
from pathlib import Path
if len(sys.argv) < 2:
    raise SystemExit(__doc__)
src=Path(sys.argv[1]); dst=Path(sys.argv[2] if len(sys.argv)>2 else 'evidence/summary.md')
doc=json.loads((src/'results.json').read_text())
env, rows, summary=doc['environment'],doc['results'],doc['summary']
checks=sum(len(r['checks']) for r in rows)
lines=['# Fresh verification summary','',
       f"Source revision: `{env.get('source_revision', 'unknown')}`; dirty entries: {env.get('git_dirty_files', 'unknown')}.",
       f"Results: **{summary['PASS']} PASS, {summary['FAIL']} FAIL, {summary['ERROR']} ERROR**; {checks} checks; {doc['total_seconds']} seconds.",'',
       'Command: `./run_tests.sh --slow` (all cases, including independent crash checks, mutants and stock usertests).',
       'Run date: 2026-11-17. Raw outputs are regenerated under ignored `evidence/run-*/` directories.','',
       '## Environment','']
for k,v in env.items():
    if k!='source_sha256': lines.append(f'- {k}: `{v}`')
lines+=['','## Cases','','| Case | Group | Result | Checks | Seconds |','|---|---|---|---|---|']
for r in rows:
    lines.append(f"| {r['id']} | {r['group']} | {r['result']} | {sum(c['pass_'] for c in r['checks'])}/{len(r['checks'])} | {r['seconds']} |")
lines+=['','## Measured transaction budgets','']
for r in rows:
    if r['id'] in ('S-budget','S-create-budget'):
        lines.append(f"- {r['id']}: {r['params'].get('distinct_blocks')} distinct blocks; reservation {r['params'].get('reservation')}.")
lines+=['','## Interpretation and limits','',
        'Mutation-case PASS means the deliberately broken kernel was detected, not that it behaved correctly.',
        'The CPUS=3 BASE/pre/post investigation did not reproduce exec-cat failures in 30 repeated cat commands; executable bytes and allocation metadata were checked.',
        'Tests demonstrate bounded retained-request at-most-once effects and one-time grant consumption under the documented xv6/QEMU redo-log assumptions. They are not an exhaustive interleaving proof or a physical power-loss test.',
        'Protected inodes are pinned permanently; 32 grant/completion slots, no GC, one controller/agent domain, root-only names and 256-byte kernel payloads. Host planner payloads are limited to 32 printable bytes.',
        'Local Ubuntu 26.04.1 toolchain was exercised; Ubuntu 24.04 CI configuration was prepared but no remote CI run or fresh package installation is claimed.','',
        '## Source hashes','']
for name,digest in env['source_sha256'].items(): lines.append(f'- `{name}`: `{digest}`')
dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text('\n'.join(lines)+'\n')
print(dst)
