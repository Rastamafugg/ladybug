"""30-second current-artifact identity gate, reusing native GDB framing."""
import sys, os, re, json, time, signal, subprocess, importlib.util, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EXPECT_FIXED='--expect-fixed' in sys.argv[2:]
OUT=Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True,exist_ok=False)
BUILD=ROOT/'build'
spec=importlib.util.spec_from_file_location('adapter',ROOT/'repro/rsch009/preflight-package/supervisor.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
syms={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug.map').read_text(),re.M)}
start=time.monotonic(); children=[]; checks=[]; result={'marker':'artifact_identity_verified','deadline_seconds':30,'passed':False}
def check():
    if time.monotonic()-start>=28: raise TimeoutError('identity observation boundary; 2 seconds reserved for cleanup')
def cmd(stage,lines): return adapter.native_command(gdb,log,OUT,stage,lines,check)
def dump(name,addr,size,extra=()):
    path=OUT/(name+'.bin')
    cmd('capture',[*extra,f'dump binary memory {path} 0x{addr:x} 0x{addr+size:x}'])
    return path.read_bytes()
def exact(name,actual,expected):
    ok=actual==expected
    checks.append({'name':name,'bytes':len(expected),'exact':ok,'sha256':hashlib.sha256(actual).hexdigest()})
    if not ok: raise AssertionError(name+' byte identity mismatch')
try:
    if subprocess.run(['ss','-H','-ltn','sport','=','65521'],capture_output=True,text=True,timeout=2).stdout.strip():
        raise RuntimeError('port occupied; no unrelated process modified')
    xlog=(OUT/'xroar.log').open('wb',buffering=0)
    x=subprocess.Popen(['/usr/local/bin/xroar','-ui','null','-ao','null','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(BUILD/'ladybug.rom'),'-cart-autorun','-gdb','-gdb-ip','127.0.0.1','-gdb-port','65521','-no-ratelimit'],stdout=xlog,stderr=subprocess.STDOUT,start_new_session=True)
    children.append(x)
    until=time.monotonic()+3
    while time.monotonic()<until:
        check()
        if f'pid={x.pid},' in subprocess.run(['ss','-H','-ltnp','sport','=','65521'],capture_output=True,text=True,timeout=1).stdout: break
        time.sleep(.05)
    else: raise TimeoutError('owned listener not ready')
    gdb=subprocess.Popen(['/usr/local/bin/m6809-gdb','-q','-nx'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    children.append(gdb);os.set_blocking(gdb.stdin.fileno(),False);os.set_blocking(gdb.stdout.fileno(),False)
    log=(OUT/'gdb.log').open('wb',buffering=0)
    cmd('setup',['set pagination off','set confirm off','set remotetimeout 3','set architecture m6809','target remote 127.0.0.1:65521'])
    cmd('continue',[f'break *0x{syms["mainloop"]:x}','continue','delete breakpoints'])
    par=dump('par',0xffa0,8); dp=dump('dp',0,256)
    result['par_hex']=par.hex();result['front_id']=dp[0x8f];result['back_id']=dp[0x90]
    # Presentation may own PAR5 at this cold mainloop. No game-state window
    # is interpreted until the prepared gameplay renderer boundary below.
    if par[0]!=0x38 or par[6:8]!=bytes([0x3e,0x3f]): raise AssertionError('unexpected runtime code PAR mapping')
    resident=(BUILD/'ladybug-runtime.rom').read_bytes()[:0x3e00]
    rom=(BUILD/'ladybug.rom').read_bytes()
    exact('resident authored cartridge',rom[0x4000:0x7e00],resident)
    exact('resident destination',dump('resident-live',0xc000,len(resident)),resident)
    stage=bytearray()
    try:
        for page,n in [(0x21,0x2000),(0x22,0x1e00)]:
            stage.extend(dump(f'resident-stage-{page}',0xa000,n,[f'set {{unsigned char}}0xffa5={page}']))
    finally: cmd('restore',['set {unsigned char}0xffa5='+str(par[5])])
    exact('resident staged',bytes(stage),resident)
    enemy=(BUILD/'ladybug-enemy-runtime.rom').read_bytes()
    exact('enemy authored cartridge',rom[0xc800:0xc800+len(enemy)],enemy)
    exact('enemy destination',dump('enemy-live',0x800,len(enemy)),enemy)
    # Inspect the loader's original cartridge source while CPU execution is
    # stopped; restore all-RAM before interpreting any resident instruction.
    try:
        source=dump('enemy-cartridge-live',0xc800,len(enemy),['set {unsigned char}0xff50=3','set {unsigned char}0xffde=0'])
    finally:
        cmd('restore',['set {unsigned char}0xffdf=0','set {unsigned char}0xff50=1'])
    exact('enemy live cartridge source',source,enemy)
    pres={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-presentation-runtime.map').read_text(),re.M)}
    ens={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-enemy-runtime.map').read_text(),re.M)}
    def reach(addr,condition=''):
        cmd('continue',[f'break *0x{addr:x}'+(' if '+condition if condition else ''),'continue','delete breakpoints'])
    reach(pres['pft_ready']);cmd('credit',['set {unsigned char}0xa9=2'])
    reach(pres['pft_ready']);cmd('start',['set {unsigned char}0xa9=1'])
    reach(ens['fri_stage_background'])
    par=dump('renderer-par',0xffa0,8);dp=dump('renderer-dp',0,256)
    if par[5]!=0x34 or dp[0x8f]==dp[0x90] or list(par[1:5])!=list(range(0x30 if dp[0x90]==0 else 0x2c,(0x30 if dp[0x90]==0 else 0x2c)+4)):
        raise AssertionError('BACK owner mapping mismatch after prepare')
    result['renderer_par_hex']=par.hex();result['renderer_front_id']=dp[0x8f];result['renderer_back_id']=dp[0x90]
    result['passed']=True
    result['identity_duration_seconds']=time.monotonic()-start
    print('artifact_identity_verified',flush=True)
    (OUT/'identity-result.json').write_text(json.dumps(result,indent=2)+'\n')
    phase_start=time.monotonic()
    def check():
        if time.monotonic()-phase_start>=58: raise TimeoutError('controlled writer observation boundary; 2 seconds reserved for cleanup')
    pres={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-presentation-runtime.map').read_text(),re.M)}
    ens={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-enemy-runtime.map').read_text(),re.M)}
    def reach(addr,condition=''):
        cmd('continue',[f'break *0x{addr:x}'+(' if '+condition if condition else ''),'continue','delete breakpoints'])
    def capture(name):
        record=dump(name+'-record',0xa380,4)
        bg=dump(name+'-bg',0xa490,256)
        stage=dump(name+'-stage',0xad00,256) if False else dump(name+'-stage',ens['ENEMY_ZONE_STAGE'],256)
        state=dump(name+'-state',0x7f,0x23)
        old=dump(name+'-mapping',0xffa1,4)
        regions={};canaries={}
        try:
            for owner,page in [('A',0x30),('B',0x2c)]:
                lines=[f'set {{unsigned char}}0xffa{i+1}={page+i}' for i in range(4)]
                raw=dump(name+'-'+owner+'-window',0x4deb,31*160+10,lines)
                compact=bytes(v for row in range(32) for v in raw[row*160+1:row*160+9])
                canaries[owner]=bytes(v for row in range(32) for v in (raw[row*160],raw[row*160+9]))
                (OUT/(name+'-'+owner+'-region.bin')).write_bytes(compact)
                (OUT/(name+'-'+owner+'-window.bin')).unlink()
                regions[owner]=compact
        finally:
            cmd('restore',[f'set {{unsigned char}}0xffa{i+1}={old[i]}' for i in range(4)])
        return dict(record=record,bg=bg,stage=stage,regions=regions,state=state,canaries=canaries)
    cmd('fixture',['set {unsigned char}0x32=1','set {unsigned char}0xa380=12','set {unsigned char}0xa381=10','set {unsigned char}0xa382=2','set {unsigned char}0xa383=1','set {unsigned char}0x2f=2','set {unsigned char}0xa0fc=(*(unsigned char*)0xa0fc)&127'])
    reach(syms['mainloop'])
    # Allow stage damage to publish to its second owner and normal entry to
    # finish before ordinary pickup. No lifecycle skip is used.
    reach(syms['main_render'],'*(unsigned char*)0xa0==0')
    before=capture('stage')
    reach(syms['check_entity_pickup'])
    cmd('pickup-position',['set {unsigned char}0x9=12','set {unsigned char}0xa=10'])
    reach(syms['mainloop'])
    reach(syms['main_render'])
    reach(syms['mainloop'])
    picked=capture('picked')
    cmd('nest-intent',['set {unsigned char}0x87=(*(unsigned char*)0x87)|8'])
    reach(ens['compose_enemy_zone'])
    reach(syms['mainloop'])
    reach(syms['main_render'])
    reach(syms['mainloop'])
    replay=capture('replay')
    animation=None; second_award=None
    if EXPECT_FIXED:
        cmd('animation-intent',['set {unsigned char}0x87=(*(unsigned char*)0x87)|16'])
        reach(ens['compose_enemy_animation'])
        reach(syms['mainloop']);reach(syms['main_render']);reach(syms['mainloop'])
        animation=capture('animation')
        reach(syms['check_entity_pickup'])
        cmd('retry-position',['set {unsigned char}0x9=12','set {unsigned char}0xa=10'])
        score_before=dump('retry-score-before',0x1d,3)
        reach(syms['cep_next'])
        score_after=dump('retry-score-after',0x1d,3)
        second_award=score_before!=score_after
    oracle=json.loads((ROOT/'repro/rsch011-yellow/current-oracle-20260917.json').read_text())
    clean=bytes.fromhex(oracle['clean_hex']);expected=bytes.fromhex(oracle['captured_hex'])
    clean_underlay=None
    if EXPECT_FIXED:
        # The historical runtime clean region includes dormant actor pixels in
        # its lower half. Model the actor-free base from immutable stage art.
        text=(BUILD/'ladybug_screen.inc').read_text()
        def art(label):
            part=text.split('\n'+label+'\n',1)[1];values=[]
            for line in part.splitlines():
                line=line.split(';',1)[0].strip()
                if not line: continue
                if not line.startswith('fcb'): break
                values.extend(int(v.strip().replace('$','0x'),0) for v in line[3:].split(','))
            return bytes(values)
        tilemap=art('screen_map');tiles=art('screen_tiles');underlay=bytearray()
        for py in range(73,105):
            for cx in (19,20):
                tile=tilemap[(py//8)*40+cx]
                if py//8 in (9,10) and tile==14: tile=5
                off=tile*32+(py%8)*4
                underlay.extend(tiles[off:off+4])
        clean_underlay=bytes(underlay)
    writer=[]
    for owner in ['A','B']:
        a=picked['regions'][owner][:128];b=replay['regions'][owner][:128]
        offsets=[i for i in range(128) if a[i]!=b[i]]
        pixels=sum(((b[i]>>shift)&15)==2 and ((a[i]>>shift)&15)!=2 for i in range(128) for shift in [0,4])
        if EXPECT_FIXED:
            visible=before['regions'][owner][:128]==expected[:128]
            animated=animation['regions'][owner][:128]==clean[:128]
            owner_pass=visible and a==clean[:128] and b==clean[:128] and animated and not offsets and pixels==0
            writer.append(dict(owner=owner,live_fixture_visible=visible,clean_matches_oracle=a==clean[:128],replay_matches_clean=b==clean[:128],animation_matches_clean=animated,offsets=offsets,yellow_pixels=pixels,passed=owner_pass))
        else:
            writer.append(dict(owner=owner,clean_matches_oracle=a==clean[:128],replay_matches_oracle=b==expected[:128],offsets=offsets,yellow_pixels=pixels,passed=a==clean[:128] and b==expected[:128] and offsets==oracle['upper_changed_offsets'] and pixels==45))
    passed=before['record'][2]==2 and picked['record'][2]==0 and replay['record'][2]==0 and before['bg']==picked['bg'] and all(w['passed'] for w in writer)
    if EXPECT_FIXED:
        passed=passed and before['bg']==clean_underlay and second_award is False
    result['controlled_writer']=dict(marker='bug040_pickup_replay_pass' if EXPECT_FIXED else 'rsch011_stale_nest_writer_verified',deadline_seconds=60,duration_seconds=time.monotonic()-phase_start,passed=passed,owners=writer,record_types=[before['record'][2],picked['record'][2],replay['record'][2]],bg_unchanged=before['bg']==picked['bg'],second_award=second_award)
    if not passed: raise AssertionError('controlled writer acceptance signature not established')
    if EXPECT_FIXED:
        phase_start=time.monotonic()
        reach(syms['mainloop'])
        cmd('colour-fixture',['set {unsigned char}0x9=12','set {unsigned char}0xa=22',
            'set {unsigned char}0x32=2','set {unsigned char}0xa382=2',
            'set {unsigned char}0xa384=12','set {unsigned char}0xa385=14',
            'set {unsigned char}0xa386=2','set {unsigned char}0xa387=1',
            'set {unsigned char}0xa15c=(*(unsigned char*)0xa15c)&127',
            'set {unsigned char}0x2f=2','set {unsigned short}0x30=150',
            'set {unsigned char}0x7f=(*(unsigned char*)0x7f)|8'])
        reach(syms['mainloop']);reach(syms['main_render']);reach(syms['mainloop'])
        yellow=capture('colour-yellow')
        reach(syms['bonus_color_tick'])
        cmd('colour-expiry',['set {unsigned short}0x30=1'])
        reach(syms['bct_done'])
        colour=dump('current-colour',0x2f,1)[0]
        reach(syms['mainloop']);reach(syms['main_render']);reach(syms['mainloop'])
        blue=capture('colour-blue')
        cmd('colour-animation',['set {unsigned char}0x87=(*(unsigned char*)0x87)|16'])
        reach(ens['compose_enemy_animation'])
        reach(syms['mainloop']);reach(syms['main_render']);reach(syms['mainloop'])
        blue_animation=capture('colour-blue-animation')
        mask=art('object_masks')[64:128]
        module=(BUILD/'ladybug-enemy-runtime.rom').read_bytes()
        palette=module[0x17d0-0x800:0x17e0-0x800]
        preserve=module[0x17a0-0x800:0x17b0-0x800]
        model=bytearray(clean_underlay)
        for row in range(15):
            for col in range(4):
                value=mask[(row+1)*4+col]
                for half,nibble in enumerate((value>>4,value&15)):
                    i=row*8+col*2+half
                    model[i]=(model[i]&preserve[nibble])|palette[nibble]
        owners=[]
        for owner in ('A','B'):
            ok=yellow['regions'][owner][:128]==expected[:128] and blue['regions'][owner][:128]==model[:128] and blue_animation['regions'][owner][:128]==model[:128] and yellow['canaries'][owner]==blue['canaries'][owner]==blue_animation['canaries'][owner] and blue['regions'][owner][248:256]==bytes([0x44]*8)
            owners.append(dict(owner=owner,passed=ok))
        passed=colour==3 and all(item['passed'] for item in owners)
        result['colour_clipping']=dict(marker='bug040_colour_clip_pass',deadline_seconds=60,duration_seconds=time.monotonic()-phase_start,passed=passed,colour=colour,owners=owners,lower_boundary='live heart at12,14; all34 valid combinations additionally source-guarded')
        if not passed: raise AssertionError('colour/clipping acceptance signature not established')
except Exception as exc: result['error']=str(exc)
finally:
    for child in reversed(children):
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try: child.wait(timeout=.4)
            except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=.4)
    result.update(duration_seconds=time.monotonic()-start,checks=checks,rom_sha256=hashlib.sha256((BUILD/'ladybug.rom').read_bytes()).hexdigest())
    result.setdefault('controlled_writer','not_completed')
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if result.get('error') or not result.get('passed'):
    sys.exit(1)
