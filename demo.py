#!/usr/bin/env python3
"""Authorized append/replay/crash demo; uses a new dedicated experiment folder."""
import argparse
import os
import shutil
import tempfile
from agent.agent import Agent
from agent.bridge import GuestBridge
from agent.controller import Controller
from agent.journal import Journal
from tests.lib.fsimage import Image


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workdir',help='NEW experiment directory; existing paths are refused')
    ap.add_argument('--crash',choices=['post','pre','lost','none'],default='post')
    args=ap.parse_args()
    os.makedirs('runs',exist_ok=True)
    work=args.workdir
    if work:
        os.makedirs(work,exist_ok=False)
    else:
        work=tempfile.mkdtemp(prefix='demo-',dir='runs')
    img=os.path.join(work,'demo.img'); shutil.copy('fs.img',img)
    print('Experiment:',work)
    with GuestBridge(img,cpus=3,log_dir=work) as bridge:
        ctl=Controller(bridge,Journal(os.path.join(work,'controller.jsonl')))
        g,rc=ctl.issue('append_file',{'path':'/log.txt','text':'authorized'})
        assert rc==0,rc
        print('Controller issued grant:',hex(g))
        if args.crash in ('pre','post'):
            stage=1 if args.crash=='pre' else 2
            armed, status = bridge.vm.run(f'crashctl stage {stage} 1')
            assert status == 'ok' and 'CRASHCTL rc=0' in armed, 'Run make test-build before crash demos'
            print(armed.strip())
        elif args.crash=='lost': bridge.drop_replies=1
        ag=Agent(bridge,Journal(os.path.join(work,'agent.jsonl')),grants=[g])
        report=ag.handle('append authorized to /log.txt')
        print(report.final); assert report.outcome=='OK',report.as_dict()
        op=next(iter(ag.journal.ops.values()))
        repeat=bridge.call(op['tool'],op['args'],key=int(op['key'],16),grant_id=g)
        print('Identical retry:',repeat.guest_status,repeat.rc)
        print('Revoke after completion:',ctl.revoke(g),'(consumed; cannot undo)')
        print('Historical status:',bridge.call('effect_status',{},key=int(op['key'],16),grant_id=g).text)
    # QEMU has stopped: inspect actual recovered home blocks offline.
    f=Image.load(img)
    expected=b'boot-entry-0\nauthorized'
    print('Offline file:',repr(f.read_file('/log.txt')))
    print('Offline grant/completion:',f.completions())
    assert f.read_file('/log.txt')==expected and len(f.completions())==1
    assert not f.check_consistency(),f.check_consistency()
    print('PASS: one authorized effect, saved-result replay, consistent disk')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
