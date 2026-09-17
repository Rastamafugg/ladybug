"""30-second current-artifact identity gate, reusing native GDB framing."""
import sys, os, re, json, time, signal, subprocess, importlib.util, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
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
    if par[0]!=0x38 or par[5:8]!=bytes([0x34,0x3e,0x3f]): raise AssertionError('unexpected runtime PAR mapping')
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
    presentation=(BUILD/'ladybug-presentation-runtime.bin').read_bytes()
    exact('presentation destination',dump('presentation-live',0x1900,len(presentation)),presentation)
    pres={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-presentation-runtime.map').read_text(),re.M)}
    ens={k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',(BUILD/'ladybug-enemy-runtime.map').read_text(),re.M)}
    def reach(addr,condition=''):
        cmd('continue',[f'break *0x{addr:x}'+(' if '+condition if condition else ''),'continue','delete breakpoints'])
    reach(pres['pft_ready']);cmd('credit',['set {unsigned char}0xa9=2'])
    reach(pres['pft_ready']);cmd('start',['set {unsigned char}0xa9=1'])
    reach(ens['fri_stage_background'])
    par=dump('renderer-par',0xffa0,8);dp=dump('renderer-dp',0,256)
    if dp[0x8f]==dp[0x90] or list(par[1:5])!=list(range(0x30 if dp[0x90]==0 else 0x2c,(0x30 if dp[0x90]==0 else 0x2c)+4)):
        raise AssertionError('BACK owner mapping mismatch after prepare')
    result['renderer_par_hex']=par.hex();result['renderer_front_id']=dp[0x8f];result['renderer_back_id']=dp[0x90]
    result['passed']=True
    result['identity_duration_seconds']=time.monotonic()-start
    print('artifact_identity_verified',flush=True)
    (OUT/'identity-result.json').write_text(json.dumps(result,indent=2)+'\n')
except Exception as exc: result['error']=str(exc)
finally:
    for child in reversed(children):
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try: child.wait(timeout=.4)
            except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=.4)
    result.update(duration_seconds=time.monotonic()-start,checks=checks,rom_sha256=hashlib.sha256((BUILD/'ladybug.rom').read_bytes()).hexdigest())
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
