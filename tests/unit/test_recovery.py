import json
import os
import tempfile
import unittest
from agent.journal import Journal

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'journal')

    def test_restart_append_restart_repairs_torn_tail(self):
        first = Journal(self.path).begin('append_file', {'text': 'x'})
        with open(self.path, 'ab') as f:
            f.write(b'{"ev":"beg')
        j = Journal(self.path)
        second = j.begin('append_file', {'text': 'y'})
        reloaded = Journal(self.path)
        self.assertEqual(set(reloaded.ops), {first['op'], second['op']})

    def test_complete_bad_record_is_corruption_even_at_tail(self):
        Journal(self.path).begin('append_file', {})
        with open(self.path, 'ab') as f:
            f.write(b'broken\n')
        with self.assertRaisesRegex(ValueError, 'corrupt journal'):
            Journal(self.path)

    def test_bad_reference_cannot_be_appended(self):
        j = Journal(self.path)
        j.begin('append_file', {})
        before = open(self.path, 'rb').read()
        with self.assertRaises(KeyError):
            j.result('missing', 'done')
        self.assertEqual(open(self.path, 'rb').read(), before)

    def test_interleaved_instances_do_not_reuse_operation_ids(self):
        a, b = Journal(self.path), Journal(self.path)
        a.begin('append_file', {})
        b.begin('append_file', {})
        self.assertEqual(len(Journal(self.path).ops), 2)

    def test_failure_reason_survives_restart(self):
        j = Journal(self.path)
        op = j.begin('append_file', {})
        j.result(op['op'], 'failed', reason='revoked')
        self.assertEqual(Journal(self.path).ops[op['op']]['reason'], 'revoked')
