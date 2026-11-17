"""Real kernel authorization, recovery and independent disk-image checks."""
import os
import re
import shutil
import struct
from tests.framework import case, kv, effect
from tests.lib.fsimage import Image
from agent.qemu import VM, VMError

BASE = b'boot-entry-0\n'

def grant(ctx, vm, command):
    out, status = ctx.sh(vm, 'grantctl ' + command)
    d = kv(next((l for l in out.splitlines() if l.startswith('GRANT ')), ''))
    return int(d['rc']) if 'rc' in d else None, d.get('outcome'), status


def _guest(name):
    @case('S-' + name, 'Authorization syscall regressions: ' + name, 'security', params=dict(cpus=3))
    def run(ctx):
        img = ctx.new_image()
        vm = ctx.boot(img, name, cpus=3)
        out, status = ctx.sh(vm, 'grtest ' + name)
        ctx.check('guest completed', 'ok', status)
        ctx.check('no failed guest assertion', False, 'FAIL ' in out)
        ctx.check('guest result', True, 'GRTEST failures=0' in out)
        vm.kill()
        f = Image.load(img)
        ctx.check('independent consistency', [], f.check_consistency())
        if name in ('same', 'different'):
            ctx.check('single completion', 1, len(f.completions()))
            ctx.check('single file effect', BASE + b'RACE', f.read_file('/log.txt'))
        if name == 'revoke':
            ctx.check('serialized revoke/effect result', True,
                      (f.grants()[0]['state'], f.read_file('/log.txt')) in
                      [(2, BASE), (3, BASE + b'RACE')])
        if name == 'auth':
            ctx.check('only approved bytes', BASE + b'SAFE', f.read_file('/log.txt'))
        if name == 'capacity':
            ctx.check('no create after full', None, f.read_file('/cap.txt'))
            ctx.check('all slots retained', 32, len(f.grants()))
            vm = ctx.boot(img, 'full-reboot', cpus=3)
            ctx.check('capacity persists across reboot', -3, grant(ctx, vm, 'issue 100 0 create /cap.txt BAD')[0])
            ctx.check('completion retained at capacity', (1, 'REPLAYED'), grant(ctx, vm, 'drop effect 1 1 append /log.txt X')[:2])
            vm.kill()
    return run

for _name in ['auth', 'invalid', 'stale', 'same', 'different', 'revoke', 'capacity', 'create-race', 'legacy-create-race', 'distinct']:
    _guest(_name)


@case('S-keys', 'Full-width grant/request IDs and global completion identity', 'security')
def keys(ctx):
    img = ctx.new_image(); vm = ctx.boot(img, 'keys', cpus=3)
    for g in ('1', '100000001'):
        ctx.check('issue ' + g, 0, grant(ctx, vm, f'issue {g} 0 append /log.txt X')[0])
        ctx.check('effect ' + g, 1, grant(ctx, vm, f'drop effect {g} {g} append /log.txt X')[0])
    ctx.check('third approval', 0, grant(ctx, vm, 'issue 2 0 append /log.txt X')[0])
    ctx.check('request reused across grants', -4, grant(ctx, vm, 'drop effect 2 1 append /log.txt X')[0])
    vm.kill(); f = Image.load(img)
    ctx.check('two exact effects', BASE+b'XX', f.read_file('/log.txt'))
    ctx.check('full-width identities', {1, 0x100000001}, {r['request_id'] for r in f.completions()})


def _crash(action, stage):
    @case(f'S-crash-{action}-{stage}', f'Grant {action} crash stage {stage}, same-image recovery', 'security-crash')
    def run(ctx):
        img = ctx.new_image(); vm = ctx.boot(img, 'before', cpus=3)
        if action != 'issue':
            ctx.check('issue approval', 0, grant(ctx, vm, 'issue 1 0 append /log.txt ONCE')[0])
        cmd = {'issue': 'issue 1 0 append /log.txt ONCE',
               'effect': 'effect 1 9 append /log.txt ONCE', 'revoke': 'revoke 1'}[action]
        rc, _, status = grant(ctx, vm, f'-s {stage} ' + cmd)
        ctx.check('injected crash', 'panic', status)
        vm.kill()
        raw = Image.load(img); recovered = raw.with_log_replayed()
        ctx.check('raw header commit indication', stage != 1, raw.log_header()[0] > 0)
        ctx.check('recovered offline consistency', [], recovered.check_consistency())
        if action == 'effect':
            ctx.check('offline completion atomic with file', stage != 1, bool(recovered.completions()))
            ctx.check('offline exact contents', BASE + (b'ONCE' if stage != 1 else b''), recovered.read_file('/log.txt'))
        vm = ctx.boot(img, 'reboot', cpus=3)
        r, outcome, status = grant(ctx, vm, cmd)
        ctx.check('retry result', 4 if action == 'effect' else 0, r)
        if action == 'effect': ctx.check('retry classification', 'EXECUTED' if stage == 1 else 'REPLAYED', outcome)
        if action == 'revoke': ctx.check('revocation effective', -21, grant(ctx, vm, 'drop effect 1 9 append /log.txt ONCE')[0])
        vm.kill(); final = Image.load(img)
        ctx.check('boot recovery matches oracle', [], final.check_consistency())
        if action == 'effect': ctx.check('one final effect', BASE+b'ONCE', final.read_file('/log.txt'))
    return run
for _action in ('issue', 'effect', 'revoke'):
    for _stage in (1,2,3,4): _crash(_action, _stage)


@case('S-create', 'Authorized CREATE, destination binding and pinning', 'security')
def create(ctx):
    img=ctx.new_image(); vm=ctx.boot(img,'create',cpus=3)
    ctx.check('issue CREATE',0,grant(ctx,vm,'issue 1 0 create /new.txt CONTENT')[0])
    ctx.check('wrong name rejected',-4,grant(ctx,vm,'drop effect 1 2 create /wrong.txt CONTENT')[0])
    ctx.check('execute',7,grant(ctx,vm,'drop effect 1 2 create /new.txt CONTENT')[0])
    ctx.check('replay',('REPLAYED'),grant(ctx,vm,'drop effect 1 2 create /new.txt CONTENT')[1])
    ctx.sh(vm,'rm /new.txt'); ctx.sh(vm,'ln /new.txt /alias')
    vm.kill(); f=Image.load(img)
    ctx.check('original inode survives',b'CONTENT',f.read_file('/new.txt'))
    ctx.check('no alias',None,f.read_file('/alias'))
    ctx.check('pinned version',True,f.root_entries()['new.txt'] in f.versions())
    ctx.check('consistency',[],f.check_consistency())


@case('S-manual', 'Reproduce BASE/pre/post crash observation with repeated cat, CPUS=3', 'security')
def manual(ctx):
    img=ctx.new_image(); vm=ctx.boot(img,'initial',cpus=3)
    ctx.check('create BASE',5,effect(ctx,vm,'create','0x10','/ex.txt','BASE-')['rc'])
    original_cat = Image.load(ctx.run.pristine).read_file('/cat')
    for stage, text, key in [(1,'pre','0x11'),(2,'post','0x12')]:
        r=effect(ctx,vm,'append',key,'/ex.txt',text,arm=f'-s {stage}:1')
        ctx.check('crash', 'panic',r['status']); vm.kill()
        vm=ctx.boot(img,'reboot'+str(stage),cpus=3)
        r=effect(ctx,vm,'append',key,'/ex.txt',text)
        ctx.check('retry','EXECUTED' if stage==1 else 'REPLAYED',r['outcome'])
    for i in range(30):
        out, status=ctx.sh(vm,'cat /ex.txt')
        ctx.check(f'cat {i}',('BASE-prepost','ok'),(out,status))
    vm.kill(); f=Image.load(img)
    ctx.check('cat executable unchanged',original_cat,f.read_file('/cat'))
    ctx.check('filesystem allocation consistency',[],f.check_consistency())
    ctx.note('Manual exec-cat failure was not reproduced. Each exec failure now reports pid/path/stage/allocated size; console/shell buffers match the bounded protocol.')


@case('S-format', 'Unsupported grant format fails closed at boot', 'security')
def badformat(ctx):
    img=ctx.new_image(); f=Image.load(img)
    with open(img,'r+b') as out:
        out.seek(f.grstart*1024+4); out.write(struct.pack('<I',999))
    vm=VM(img,kernel=ctx.kernel,cpus=3,log_path=os.path.join(ctx.dir,'badformat.log'))
    try:
        vm.boot(timeout=4)
    except VMError:
        ctx.check('invalid format diagnosed',True,'unsupported grant format' in vm.buf)
    else:
        ctx.check('must refuse unsupported format',False,True)
    finally: vm.kill()

@case('S-diskfull', 'Secured short writes, empty CREATE, zero progress and indirect allocation cleanup', 'security')
def diskfull(ctx):
    img=ctx.new_image(); vm=ctx.boot(img,'diskfull',cpus=3)
    out,status=ctx.sh(vm,'grtest disksetup')
    ctx.check('setup',True,'GRTEST failures=0' in out)
    ctx.check('edge approval',0,grant(ctx,vm,'issue 1 0 append /edge.txt 0123456789')[0])
    ctx.check('big approval',0,grant(ctx,vm,'issue 2 0 append /big.txt X')[0])
    ctx.sh(vm,'diskfill',timeout=60)
    ctx.check('empty create grant',0,grant(ctx,vm,'issue 3 0 create /empty.txt DATA')[0])
    ctx.check('empty create records zero',0,grant(ctx,vm,'drop effect 3 3 create /empty.txt DATA')[0])
    ctx.check('empty create replays zero',(0,'REPLAYED'),grant(ctx,vm,'drop effect 3 3 create /empty.txt DATA')[:2])
    ctx.check('short append',4,grant(ctx,vm,'drop effect 1 1 append /edge.txt 0123456789')[0])
    ctx.check('short replay',(4,'REPLAYED'),grant(ctx,vm,'drop effect 1 1 append /edge.txt 0123456789')[:2])
    ctx.sh(vm,'rm /spare') # exactly one free data block
    for _ in range(3):
        ctx.check('indirect no progress EIO',-5,grant(ctx,vm,'drop effect 2 2 append /big.txt X')[0])
    vm.kill(); f=Image.load(img)
    ctx.check('unused indirect allocation rolled back',1,f.free_blocks())
    ctx.check('no orphan indirect pointer',0,f.inode(f.root_entries()['big.txt'])['addrs'][12])
    ctx.check('zero progress leaves grant active',1,next(r for r in f.grants() if r['grant_id']==2)['state'])
    ctx.check('empty file exists',b'',f.read_file('/empty.txt'))
    ctx.check('short saved result',4,next(r for r in f.grants() if r['grant_id']==1)['result'])
    ctx.check('consistent',[],f.check_consistency())


@case('S-budget', 'Worst-case secured direct-to-indirect APPEND log reservation', 'security')
def budget(ctx):
    img=ctx.new_image(); vm=ctx.boot(img,'budget',cpus=3)
    text='X'*256
    ctx.check('issue 256 bytes',0,grant(ctx,vm,f'issue 1 0 append /big.txt {text}')[0])
    # The post-header crash exposes exactly the blocks in this transaction.
    ctx.check('commit crash','panic',grant(ctx,vm,f'-s 2 effect 1 1 append /big.txt {text}')[2])
    vm.kill(); raw=Image.load(img); n,blocks=raw.log_header()
    ctx.param(distinct_blocks=n,block_numbers=blocks,reservation=10)
    ctx.check('within MAXOPBLOCKS',True,0<n<=10)
    f=raw.with_log_replayed()
    ctx.check('full payload',True,f.read_file('/big.txt').endswith(text.encode()))
    ctx.check('consumed',3,f.grants()[0]['state'])
    ctx.check('version atomic',f.grants()[0]['version']+1,f.versions()[f.grants()[0]['inum']])
    ctx.check('consistency',[],f.check_consistency())


@case('S-comparison', 'Isolated unsafe comparison build demonstrates duplicate/revoked writes', 'comparison')
def comparison(ctx):
    from tests.cases.c_regress import build_tree
    tree, rc=build_tree(ctx,'compare','TESTHOOKS=1 UNSAFE_COMPARISONS=1')
    ctx.check('explicit comparison build',0,rc)
    img=os.path.join(ctx.dir,'compare.img'); shutil.copy(os.path.join(tree,'fs.img'),img)
    vm=ctx.boot(img,'comparison',cpus=3,kernel=os.path.join(tree,'kernel/kernel'))
    out,status=ctx.sh(vm,'compare')
    ctx.check('real comparisons completed',True,'COMPARE atomic=1 retry=1 outcome=2' in out)
    vm.kill(); f=Image.load(img)
    ctx.check('ordinary retries duplicate',b'XX',f.read_file('/ordinary'))
    ctx.check('dedup retries retained once',b'X',f.read_file('/dedup'))
    ctx.check('non-atomic check writes AFTER revoke',b'X',f.read_file('/nonatomic'))
    ctx.check('non-atomic grant is revoked',2,f.grants()[0]['state'])
    ctx.check('integrated grant retained once',b'X',f.read_file('/atomic'))
    shutil.rmtree(tree)

@case('S-create-budget', 'Authorized CREATE transaction budget and crash recovery', 'security')
def create_budget(ctx):
    img=ctx.new_image(); vm=ctx.boot(img,'create-budget',cpus=3)
    text='C'*256
    ctx.check('approval',0,grant(ctx,vm,f'issue 1 0 create /created {text}')[0])
    ctx.check('crash','panic',grant(ctx,vm,f'-s 2 effect 1 1 create /created {text}')[2])
    vm.kill(); raw=Image.load(img); n,blocks=raw.log_header()
    ctx.param(distinct_blocks=n,block_numbers=blocks,reservation=10)
    ctx.check('within reservation',True,0<n<=10)
    view=raw.with_log_replayed()
    ctx.check('offline file',text.encode(),view.read_file('/created'))
    ctx.check('offline completion',3,view.grants()[0]['state'])
    vm=ctx.boot(img,'recovered-create',cpus=3)
    ctx.check('replay',(256,'REPLAYED'),grant(ctx,vm,f'drop effect 1 1 create /created {text}')[:2])
    vm.kill(); ctx.check('consistent',[],Image.load(img).check_consistency())

@case('S-controller-recovery', 'Trusted controller journal retries issuance/revocation after lost crash replies', 'security')
def controller_recovery(ctx):
    from agent.bridge import GuestBridge
    from agent.controller import Controller
    from agent.journal import Journal
    for stage in (1,2):
        img=ctx.new_image('controller'+str(stage))
        journal=os.path.join(ctx.dir,f'controller-{stage}.jsonl')
        bridge=GuestBridge(img,kernel=ctx.kernel,cpus=3,log_dir=ctx.dir).start()
        try:
            ctl=Controller(bridge,Journal(journal))
            ctx.sh(bridge.vm,f'crashctl stage {stage} 1')
            g,rc=ctl.issue('append_file',{'path':'/log.txt','text':'APPROVED'})
            ctx.check('issuance missing reply is unknown',None,rc)
            bridge.needs_restart=True
            restarted=Controller(bridge,Journal(journal))
            ctx.check('resume stable grant',[(g,0)],restarted.resume())
            ctx.sh(bridge.vm,'crashctl stage 2 1')
            ctx.check('revoke missing reply unknown',None,restarted.revoke(g))
            bridge.needs_restart=True
            ctx.check('resume durable revoke',[(g,0)],Controller(bridge,Journal(journal)).resume())
            r=bridge.call('append_file',{'path':'/log.txt','text':'APPROVED'},key=7,grant_id=g)
            ctx.check('revoked effect reported',('ERR',-21,'REVOKED'),(r.status,r.rc,r.guest_status))
        finally: bridge.stop()
        f=Image.load(img)
        ctx.check('one approval despite issuance retry',1,len(f.grants()))
        ctx.check('no effect',BASE,f.read_file('/log.txt'))
        ctx.check('consistent',[],f.check_consistency())

# Authorized CREATE gets independent before/partial/installed crash trials too.
for _stage in (1,3,4):
    def register_create_crash(stage):
        @case(f'S-create-crash-{stage}', f'Authorized CREATE crash stage {stage}', 'security-crash')
        def run(ctx):
            img=ctx.new_image(); vm=ctx.boot(img,'create-before',cpus=3)
            ctx.check('issue',0,grant(ctx,vm,'issue 1 0 create /created NEW')[0])
            ctx.check('crash','panic',grant(ctx,vm,f'-s {stage} effect 1 1 create /created NEW')[2])
            vm.kill(); raw=Image.load(img); view=raw.with_log_replayed()
            ctx.check('offline create atomic',None if stage==1 else b'NEW',view.read_file('/created'))
            ctx.check('offline consumed',1 if stage==1 else 3,view.grants()[0]['state'])
            vm=ctx.boot(img,'create-after',cpus=3)
            ctx.check('retry',(3,'EXECUTED' if stage==1 else 'REPLAYED'),grant(ctx,vm,'drop effect 1 1 create /created NEW')[:2])
            vm.kill(); ctx.check('consistent',[],Image.load(img).check_consistency())
    register_create_crash(_stage)
