"""Deliberately BROKEN kernels ("mutants"), used to prove the test suite can
fail. Each mutant is a small source edit applied to a scratch COPY of the tree;
the production source is never touched.

  name -> (description, file, [(old, new), ...], test-case ids that must catch it)
"""

MUTANTS = {
    "truncate-key": (
        "key truncated to 32 bits (the classic argint() mistake)",
        "kernel/effect.c",
        [("  argaddr(0, &key);\n", "  argaddr(0, &key);\n  key = (uint32)key; // MUTANT\n")],
        ["B4"],
    ),
    "split-transaction": (
        "table entry written in a SECOND transaction after the file effect committed",
        "kernel/effect.c",
        [("  int executed = 0;\n", "  int executed = 0, late_put = 0;\n"),
         ("      store_put(slot, key, res, sig);\n      logged = log_nblocks(); // distinct blocks this transaction logged\n      executed = 1;",
          "      late_put = 1; // MUTANT: record later\n      logged = log_nblocks();\n      executed = 1;"),
         ("  end_op(); // commit point is reached inside here (if we were the last op)\n",
          "  end_op();\n  if (late_put) { begin_op(); store_put(slot, key, res, sig); end_op(); } // MUTANT\n")],
        ["C1"],
    ),
    "no-replay-lookup": (
        "known key is ignored: the effect is executed again",
        "kernel/effect.c",
        [("  if (found == 1) {\n    if (e.sig != sig) {", "  if (found == 1 && 0) { // MUTANT\n    if (e.sig != sig) {")],
        ["B2"],
    ),
    "ignore-mismatch": (
        "same key with a different request silently replays the old result",
        "kernel/effect.c",
        [("    if (e.sig != sig) {\n      res = EFF_EMISMATCH;", "    if (0 && e.sig != sig) { // MUTANT\n      res = EFF_EMISMATCH;")],
        ["B5"],
    ),
    "commit-order": (
        "xv6 log bug: install blocks BEFORE writing the commit header (breaks crash atomicity)",
        "kernel/log.c",
        [("    write_head();     // Write header to disk -- the real commit\n    crash_stage_check(CRASH_AFTER_HEADER);  // [effect] committed, not installed\n    install_trans(0); // Now install writes to home locations\n",
          "    install_trans(0); // MUTANT: install first\n    write_head();\n    crash_stage_check(CRASH_AFTER_HEADER);\n")],
        ["C1"],
    ),
}
