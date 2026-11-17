"""Trusted approval client. Never called by Agent or a planner.

The VM's administrative console is privileged host access. Exact requests and
stable grant IDs are journaled before this separate client dispatches them.
"""
import re
from .journal import new_key
from .tools import validate_action
from .bridge import MAX_LINE


class Controller:
    def __init__(self, bridge, journal):
        self.bridge, self.journal = bridge, journal

    def issue(self, tool, args, grant_id=None):
        action = validate_action({'tool': tool, 'args': args})
        if tool not in ('append_file', 'create_file'):
            raise ValueError('only filesystem effects can be approved')
        grant_id = new_key() if grant_id is None else grant_id
        op = self.journal.begin('grant_issue', action, grant_id=grant_id)
        return grant_id, self._dispatch(op)

    def revoke(self, grant_id):
        op = self.journal.begin('grant_revoke', {}, grant_id=grant_id)
        return self._dispatch(op)

    def _dispatch(self, op):
        g = op['grant_id']
        if not isinstance(g, int) or not 0 < g < 2**64:
            raise ValueError('invalid grant ID')
        if op['tool'] == 'grant_issue':
            a = op['args']
            validate_action(a)
            verb = 'append' if a['tool'] == 'append_file' else 'create'
            # Printable payload is hex encoded; grantctl supports issuehex so
            # spaces are data, never parsed as shell syntax.
            line = f"grantctl issuehex {g:x} 0 {verb} {a['args']['path']} {a['args']['text'].encode().hex()}"
        elif op['tool'] == 'grant_revoke':
            line = f'grantctl revoke {g:x}'
        else:
            raise ValueError('not a controller journal')
        if len(line) >= MAX_LINE:
            raise ValueError('controller request too long')
        self.bridge.recover()
        comm = self.bridge.reserve_id()
        self.journal.attempt(op['op'], comm)
        out, status = self.bridge.vm.run(line)
        match = re.search(r'^GRANT .* rc=(-?\d+) outcome=(\w+)$', out, re.M)
        if status != 'ok' or not match:
            self.journal.result(op['op'], 'unknown', reason=f'controller {status}: missing reply')
            return None
        rc = int(match[1])
        self.journal.result(op['op'], 'done' if rc >= 0 else 'failed', rc=rc, outcome=match[2])
        return rc

    def resume(self):
        return [(op['grant_id'], self._dispatch(op)) for op in self.journal.pending()]
