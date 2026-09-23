"""Bounded native-GDB name-entry observation; no monitor extension."""
import sys, os, re, json, time, signal, subprocess, importlib.util, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BUILD=Path(os.environ.get('BUG036_BUILD',str(ROOT/'build'))).resolve()
OUT=Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('native_adapter',ROOT/'repro/rsch009/preflight-package/supervisor.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
def symbols(name):
    return {k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/name).read_text(),re.M)}
main=symbols('ladybug.map');pres=symbols('ladybug-presentation-runtime.map');hs=symbols('ladybug-highscore-runtime.map')
started=time.monotonic(); children=[]; checks=[]; result={'status':'incomplete'}
def check():
    if time.monotonic()-started>=50: raise TimeoutError('50-second observation boundary; closure reserved10 seconds')
def cmd(stage,lines): return adapter.native_command(gdb,log,OUT,stage,lines,check)
def reach(addr):
    cmd('continue',[f'break *0x{addr:x}','continue','delete breakpoints', 'printf "PC=%u\\n", $pc'])
def dump(name,addr,size,extra=()):
    path=OUT/name
    cmd('capture',[*extra,f'dump binary memory {path} 0x{addr:x} 0x{addr+size:x}'])
    return path.read_bytes()
def identity(name,addr,artifact,extra=(),length=None):
    data=(BUILD/artifact).read_bytes();data=data if length is None else data[:length]
    actual=dump(name+'.bin',addr,len(data),extra)
    ok=actual==data;checks.append(dict(name=name,exact=ok,sha256=hashlib.sha256(data).hexdigest()))
    if not ok: raise AssertionError('identity '+name)
try:
    # ss reads the listener table; never open a probe connection to the stub.
    occupied=subprocess.run(['ss','-H','-ltn','sport','=','65521'],capture_output=True,text=True,timeout=2)
    if occupied.stdout.strip(): raise RuntimeError('GDB port65521 occupied')
    xlog=(OUT/'xroar.log').open('wb',buffering=0)
    xroar=subprocess.Popen(['/usr/local/bin/xroar','-ui','null','-ao','null','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(BUILD/'ladybug.rom'),'-cart-autorun','-gdb','-gdb-ip','127.0.0.1','-gdb-port','65521','-no-ratelimit'],stdout=xlog,stderr=subprocess.STDOUT,start_new_session=True)
    children.append(xroar)
    until=time.monotonic()+3
    while time.monotonic()<until:
        check()
        listing=subprocess.run(['ss','-H','-ltnp','sport','=','65521'],capture_output=True,text=True,timeout=1).stdout
        if f'pid={xroar.pid},' in listing: break
        time.sleep(.05)
    else: raise TimeoutError('owned listener not ready')
    gdb=subprocess.Popen(['/usr/local/bin/m6809-gdb','-q','-nx'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    children.append(gdb);os.set_blocking(gdb.stdin.fileno(),False);os.set_blocking(gdb.stdout.fileno(),False)
    log=(OUT/'gdb.log').open('wb',buffering=0)
    cmd('setup',['set pagination off','set confirm off','set remotetimeout 3','set architecture m6809','target remote 127.0.0.1:65521'])
    print('phase=name-entry-native marker=mainloop/name_tick limit50s; timeout=observation boundary failed',flush=True)
    reach(main['mainloop'])
    identity('resident',0xc000,'ladybug-runtime.rom',length=0x3e00)
    identity('enemy-lowram',0x0800,'ladybug-enemy-runtime.rom')
    identity('presentation',0x1900,'ladybug-presentation-runtime.bin')
    identity('helper-staged',0xac40,'ladybug-highscore-helper.bin',['set {unsigned char}0xffa5=0x23'])
    identity('owner-staged',0xa880,'ladybug-highscore-runtime.bin')
    cmd('restore',['set {unsigned char}0xffa5=0x34'])
    reach(pres['pft_ready']);cmd('credit',['set {unsigned char}0x00a9=2'])
    reach(pres['pft_ready']);cmd('start',['set {unsigned char}0x00a9=1'])
    reach(pres['normal_tick']);dump('normal-dp.bin',0,256);cmd('terminal-death',[f'set {{unsigned short}}0x001d={0 if "--nonqual" in sys.argv else 0x0950}','set {unsigned char}0x001f=0','set {unsigned char}0x004d=4'])
    reach(main['mainloop'])
    identity('owner-after-gameover-install',0x300,'ladybug-highscore-runtime.bin')
    if '--nonqual' in sys.argv:
        cmd('continue',[f'break *0x{main["mainloop"]:x} if *(unsigned char*)0xa6==3','continue','delete breakpoints'])
        dp=dump('nonqual-dp.bin',0,256)
        checks.append(dict(name='nonqualifying-bypass',insert=dp[0xc9],screen=dp[0xa6],score=dp[0xbf:0xc2].hex(),passed=dp[0xc9]==255 and dp[0xa6]==3 and dp[0xbf:0xc2]==bytes(3)))
        result=dict(status='captured',checks=checks,rom_sha256=hashlib.sha256((BUILD/'ladybug.rom').read_bytes()).hexdigest())
        raise StopIteration
    reach(hs['name_tick'])
    dump('entry-dp.bin',0,256)
    identity('owner-loaded',0x300,'ladybug-highscore-runtime.bin')
    identity('helper-live',0xac40,'ladybug-highscore-helper.bin',['set {unsigned char}0xffa5=0x23'])
    cmd('restore',['set {unsigned char}0xffa5=0x34'])
    if '--dispatch' in sys.argv:
        reach(main['main_game_tick'])
        dp=dump('gameplay-leak-dp.bin',0,256)
        checks.append(dict(name='gameplay-executes-during-name',mode=dp[0xa5],screen=dp[0xa6],confirmed=dp[0xa5]==8))
    states=[]
    if '--active-timing' in sys.argv:
        samples=[]
        for i in range(10):
            reach(0x1900)
            cmd('active-state',['set {unsigned char}0x3=0','set {unsigned char}0x5=3','set {unsigned char}0xf=3']+(['set {unsigned char}0xe8=59'] if i==0 else []))
            before=cmd('cycles',['monitor cycles before'])
            # READ_JOY may replace the synthetic direction; inject again after it.
            reach(hs['name_joy_ready'])
            cmd('resolved-input',['set {unsigned char}0x5=3','set {unsigned char}0xf=3','set {unsigned char}0x3=0'])
            reach(main['mainloop'])
            after=cmd('cycles',['monitor cycles after'])
            a=int(re.search(r'(\d+) cycles',before)[1]);b=int(re.search(r'(\d+) cycles',after)[1])
            dp=dump(f'active-{i}.bin',0,256)
            samples.append(dict(cycles=2*(b-a),phase=dp[0xe1],box=dp[0xe9],steps=dp[0xde],animation=dp[0x4f]))
        checks.append(dict(name='active-timer-movement',samples=samples,limit=27000,passed=max(s['cycles'] for s in samples)<=27000))
    if '--timeout' in sys.argv:
        # Force only the final timer boundary; retain natural commit/score shift.
        initial=dump('scores-before.bin',0xaf84,90)
        pending=dump('pending-before.bin',0xafde,7)
        cmd('last-timer',['set {unsigned char}0xe8=59','set {unsigned char}0xe9=91'])
        cmd('continue',[f'break *0x{main["mainloop"]:x} if *(unsigned char*)0xa6==3','continue','delete breakpoints'])
        scores=dump('scores-after.bin',0xaf84,90,['set {unsigned char}0xffa5=0x34'])
        dp=dump('timeout-dp.bin',0,256)
        passed=scores[:10]==bytes.fromhex('095000')+pending and scores[10:]==initial[:80] and dp[0xa6]==3
        checks.append(dict(name='timeout-commit-and-shift',passed=passed,screen=dp[0xa6],record=scores[:10].hex()))
        cmd('continue',[f'break *0x{main["mainloop"]:x} if *(unsigned char*)0xa5==5','continue','delete breakpoints'])
        dp=dump('ranking-ready-dp.bin',0,256)
        checks.append(dict(name='ranking-hydration-completes',passed=dp[0xa5]==5 and dp[0xa6]==3,mode=dp[0xa5],screen=dp[0xa6]))
        result=dict(status='captured',checks=checks,rom_sha256=hashlib.sha256((BUILD/'ladybug.rom').read_bytes()).hexdigest())
        if not passed:raise AssertionError('timeout commit')
        raise StopIteration
    if '--natural-timer' in sys.argv:
        cmd('continue',[f'break *0x{hs["name_tick"]:x} if *(unsigned char*)0xe9==1','continue','delete breakpoints'])
        dp=dump('natural-timer-dp.bin',0,256)
        passed=dp[0xa5]==8 and dp[0xa6]==5 and dp[0xe9]==1 and dp[0x91]==0
        checks.append(dict(name='natural-first-timer-no-input',passed=passed,mode=dp[0xa5],screen=dp[0xa6],box=dp[0xe9],pending=dp[0x91]))
        assert passed,'natural first timer transition'
        identity('owner-after-first-timer',0xa880,'ladybug-highscore-runtime.bin',['set {unsigned char}0xffa5=0x23'])
        identity('helper-after-first-timer',0xac40,'ladybug-highscore-helper.bin')
        cmd('restore',['set {unsigned char}0xffa5=0x34'])
        if '--timer-move' in sys.argv:
            start=int.from_bytes(dp[11:13],'big')
            for _ in range(4):
                reach(hs['name_joy_ready'])
                cmd('resolved-west',['set {unsigned char}0x5=3','set {unsigned char}0xf=3','set {unsigned char}0x3=0'])
                reach(main['mainloop'])
            moved=dump('natural-timer-move-dp.bin',0,256)
            finish=int.from_bytes(moved[11:13],'big')
            passed=finish<start and moved[0xa5]==8 and moved[0xa6]==5
            checks.append(dict(name='move-after-first-timer',passed=passed,start=start,finish=finish))
            assert passed,'post-timer movement'
    if '--timer' in sys.argv:
        cmd('timer-seed',['set {unsigned char}0x00e8=59'])
        for i in range(5):reach(hs['name_tick'])
        dp=dump('timer-dp.bin',0,256)
        checks.append(dict(name='first-timer-box-both-owners',box=dp[0xe9],phase=dp[0xe1]))
    if '--controls' in sys.argv:
        for direction in (3,3,1,1,0,0,3,3,3,3,2,2):
            reach(hs['name_joy_ready'])
            cmd('input',[f'set {{unsigned char}}0x0005={direction}',f'set {{unsigned char}}0x000f={direction}','set {unsigned char}0x0003=0'])
            reach(main['mainloop'])
            dp=dump(f'control-{len(states)}.bin',0,256)
            states.append(dict(direction=direction,player_fb=int.from_bytes(dp[11:13],'big'),x=dp[9],y=dp[10],steps=dp[0xde],dir=dp[6],mode=dp[0xa5]))
    if '--edit' in sys.argv or '--max-name' in sys.argv or '--late-turn' in sys.argv:
        # Path comes from authored edge table; drive resolved directional input,
        # never patch position or framebuffer state to teleport onto an action.
        from collections import deque
        meta=json.loads((BUILD/'ladybug-presentation.json').read_text())['high_score_name_entry']
        cold=(BUILD/'ladybug-presentation-cold.bin').read_bytes()
        inc=(BUILD/'ladybug_presentation.inc').read_text()
        offset=int(re.search(r'PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE equ \$([0-9A-F]+)',inc)[1],16)
        edges=cold[offset:offset+576]
        def path_to(start,target):
            q=deque([(start,[])]);seen={start}
            while q:
                (x,y),path=q.popleft()
                if (x,y)==target:return path
                for d,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
                    n=x+dx,y+dy
                    if edges[y*24+x]&(1<<d) and n not in seen:seen.add(n);q.append((n,path+[d]))
            raise AssertionError('unreachable action '+str(target))
        current=(11,22)
        reach(hs['name_joy_ready'])
        neighbor=next((8+dx,4+dy) for d,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))) if edges[4*24+8]&(1<<d))
        targets=([(8,4),neighbor]*8+[(8,4),(3,4),(19,20)]) if '--max-name' in sys.argv else [(8,4),(3,4),(19,20)]
        if '--late-turn' in sys.argv:
            q=deque([(11,22)]);seen={(11,22)};corner=None
            while q:
                x,y=q.popleft()
                if edges[y*24+x]&3==3:corner=(x,y);break
                for d,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
                    n=x+dx,y+dy
                    if edges[y*24+x]&(1<<d) and n not in seen and n!=(19,20):seen.add(n);q.append(n)
            assert corner is not None,'reachable perpendicular junction'
            targets=[corner]
        for visit,target in enumerate(targets):
            route=path_to(current,target)
            lines=[f'break *0x{hs["name_joy_ready"]:x}']
            for index,d in enumerate(route):
                if target==(19,20) and index==len(route)-1:
                    lines+=['set $moves=3','while $moves>0',f'set {{unsigned char}}0x5={d}',f'set {{unsigned char}}0xf={d}','set {unsigned char}0x3=0','continue','set $moves=$moves-1','end','delete breakpoints',f'break *0x{main["mainloop"]:x}',f'set {{unsigned char}}0x5={d}',f'set {{unsigned char}}0xf={d}','set {unsigned char}0x3=0','continue']
                    continue
                lines+=['set $moves=4','while $moves>0',f'set {{unsigned char}}0x5={d}',f'set {{unsigned char}}0xf={d}','set {unsigned char}0x3=0','continue','set $moves=$moves-1','end']
            # END flags commit on following tick; stop at arrival before that.
            lines+=['delete breakpoints']
            cmd('continue',lines)
            dp=dump(f'edit-{visit}-{target[0]}-{target[1]}.bin',0,256,['set {unsigned char}0xffa5=0x34'])
            pending=dump(f'pending-{visit}-{target[0]}-{target[1]}.bin',0xafde,7)
            checks.append(dict(name='edit-route',target=target,cells=len(route),actual=[dp[9]-8,dp[10]],length=dp[0xcb],flags=dp[0xe2],pending=pending.hex()))
            if '--max-name' in sys.argv and visit==16:
                assert dp[0xcb]==7 and pending==bytes([0x24])*7, 'maximum name cap'
                checks.append(dict(name='maximum-seven-and-eighth-rejected',passed=True))
                reach(main['mainloop']);reach(0x1900)
                cmd('full-name-timer',['set {unsigned char}0xe8=59'])
                before=cmd('cycles',['monitor cycles before'])
                reach(main['mainloop'])
                after=cmd('cycles',['monitor cycles after'])
                cycles=2*(int(re.search(r'(\d+) cycles',after)[1])-int(re.search(r'(\d+) cycles',before)[1]))
                checks.append(dict(name='full-name-plus-timer-cycles',cycles=cycles,limit=27000,passed=cycles<=27000))
                assert cycles<=27000,'full name timer timing'
                reach(hs['name_joy_ready'])
            if target==(3,4) and '--max-name' in sys.argv:
                assert dp[0xcb]==6 and pending==bytes([0x24])*6+bytes([0xb2]),'delete last character'
                checks.append(dict(name='delete-last-character',passed=True))
            current=target
            if target==(19,20):break
        if '--late-turn' in sys.argv:
            before=dump('turn-before.bin',0,256)
            origin=int.from_bytes(before[11:13],'big')
            observations=[]
            for d in (1,0,255,0,0,0,0):
                cmd('turn-input',[f'set {{unsigned char}}0x5={d}',f'set {{unsigned char}}0xf={d}' if d!=255 else 'set $neutral=1','set {unsigned char}0x3=0'])
                reach(main['mainloop'])
                dp=dump(f'turn-{len(observations)}.bin',0,256)
                observations.append(dict(pointer=int.from_bytes(dp[11:13],'big'),steps=dp[0xde],snap=dp[0x56],x=dp[9]-8,y=dp[10],face=dp[7]))
                reach(hs['name_joy_ready'])
            expected=[origin+1,origin+1,origin+1,origin-320,origin-640,origin-960,origin-1280]
            passed=[o['pointer'] for o in observations]==expected and observations[1]['snap']==1 and observations[-1]['steps']==0
            checks.append(dict(name='late-turn-and-neutral-pause',corner=corner,observations=observations,passed=passed))
            assert passed,'late turn geometry'
    if '--timing' in sys.argv:
        samples=[]
        for i in range(4):
            reach(0x1900)
            before=cmd('cycles',['monitor cycles before'])
            reach(main['mainloop'])
            after=cmd('cycles',['monitor cycles after'])
            a=int(re.search(r'(\d+) cycles',before)[1]);b=int(re.search(r'(\d+) cycles',after)[1]);samples.append(2*(b-a))
        checks.append(dict(name='name-foreground-fast-cycle-equivalent',samples=samples,limit=27000))
    for i in range(4):
        dp=dump(f'dp-{i}.bin',0,256)
        states.append(dict(tick=i,dp=dp.hex(),player_fb=int.from_bytes(dp[11:13],'big'),front=dp[0x8f],back=dp[0x90],pending=dp[0x91]))
        if i<3: reach(main['mainloop'] if '--edit' in sys.argv or '--max-name' in sys.argv else hs['name_tick'])
    if '--edit' in sys.argv or '--max-name' in sys.argv:
        scores=dump('committed-scores.bin',0xaf84,90,['set {unsigned char}0xffa5=0x34'])
        passed=scores[:10]==bytes.fromhex('095000')+pending
        checks.append(dict(name='end-committed-record',passed=passed,record=scores[:10].hex()))
        assert passed,'END record persistence'
    for owner in (0,1):
        lines=[f'set {{unsigned char}}0xffa{j+1}={0x30-owner*4+j}' for j in range(4)]
        dump(f'frame-{owner}.bin',0x2000,30720,lines)
    result=dict(status='captured',checks=checks,states=states,rom_sha256=hashlib.sha256((BUILD/'ladybug.rom').read_bytes()).hexdigest())
except StopIteration:
    pass
except Exception as exc:
    result=dict(status='fail',error=repr(exc),checks=checks)
finally:
    for p in children:
        try: os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError: pass
    for p in children:
        try: p.wait(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=1)
    result['elapsed_seconds']=time.monotonic()-started
    result['children']=[dict(pid=p.pid,exit=p.returncode) for p in children]
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
sys.exit(0 if result['status']=='captured' else 1)
