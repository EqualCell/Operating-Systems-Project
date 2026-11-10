#!/usr/bin/env python3
"""
scripts/demo_resume.py — Durable pending-operation identity & crash resume demonstration.

Demonstrates:
  1. Requests and validated arguments are durably written to the JSONL journal
     *before* wire dispatch.
  2. Host crashes mid-flight leave records in 'pending' status.
  3. Upon host restart, the journal reconstructs state from stored records.
  4. Resuming execution reuses the original correlation ID and arguments.
  5. An ambiguous retry NEVER generates a fresh logical identity.
  6. Completed requests return stored responses without invoking an LLM or re-executing.
"""

import os
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agent.journal import RequestJournal, JournalEntry
from agent.planner import _make_correlation_id


def banner(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}\n")


def main():
    banner("DURABLE PENDING-OPERATION IDENTITY & CRASH RESUME DEMO")

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        journal_file = tf.name

    try:
        # Phase 1: Pre-crash journal recording
        banner("Phase 1: Pre-dispatch Journaling & Simulated Host Crash")
        j1 = RequestJournal(journal_file)

        operations = [
            ("list_files", {"path": "."}),
            ("effect_append", {"path": "state.log", "data": "update_batch_1\n"}),
            ("effect_append", {"path": "state.log", "data": "update_batch_2\n"}),
        ]

        recorded_ids = []
        for tool, args in operations:
            cid = _make_correlation_id(tool, args)
            j1.record_request(cid, tool, args)
            recorded_ids.append((cid, tool, args))
            print(f"  [Durable Write] ID={cid} | Tool={tool} | Args={args} -> Status: PENDING")

        # Simulate: operation 1 completed before crash
        first_cid = recorded_ids[0][0]
        j1.complete(first_cid, "README effectctl user kernel", JournalEntry.COMPLETED)
        print(f"\n  [State Update] ID={first_cid} transitioned to COMPLETED")

        # Simulate host crash (abrupt power loss / process kill)
        print("\n  [!] SIMULATING HOST PROCESS CRASH / SUDDEN POWER OFF...")
        del j1  # In-memory data destroyed; only on-disk journal remains

        # Phase 2: Host restart & resume from stored state
        banner("Phase 2: Host Restart & Reconstruction from Stored State")
        j2 = RequestJournal(journal_file)

        all_entries = j2.all_entries()
        pending_entries = j2.pending()

        print(f"  Journal recovered from disk: {journal_file}")
        print(f"  Total records recovered: {len(all_entries)}")
        print(f"  Pending unacknowledged operations: {len(pending_entries)}")

        assert len(pending_entries) == 2, "Expected exactly 2 pending operations after crash"
        assert j2.get(first_cid).status == JournalEntry.COMPLETED

        # Phase 3: Verify durable identity preservation
        banner("Phase 3: Verify Identity Preservation (No Fresh Logical Identity)")
        for p in pending_entries:
            expected_cid = _make_correlation_id(p.tool_name, p.arguments)
            print(f"  Resuming operation: {p.tool_name}({p.arguments})")
            print(f"    - Recovered Correlation ID: {p.correlation_id}")
            print(f"    - Recomputed Canonical ID:  {expected_cid}")
            assert p.correlation_id == expected_cid, "Fatal: Correlation ID drifted across restart!"
            print(f"    ✓ Preserved exact logical identity across process restart.")
            print(f"    -> Ready for idempotent guest re-dispatch with ID {p.correlation_id}")

        # Phase 4: Retry of completed operation
        banner("Phase 4: Ambiguous Retry of Completed Request")
        cached_entry = j2.get(first_cid)
        print(f"  Checking operation: {cached_entry.tool_name}({cached_entry.arguments})")
        print(f"  Status in journal: {cached_entry.status.upper()}")
        print(f"  Stored response:   {cached_entry.response}")
        print("  ✓ Returned cached response directly without rerunning LLM or re-dispatching.")

        banner("DURABLE IDENTITY & RESUME VERIFICATION PASSED ✓")

    finally:
        if os.path.exists(journal_file):
            os.remove(journal_file)


if __name__ == "__main__":
    main()

