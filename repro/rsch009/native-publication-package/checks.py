"""Prepared comparator-only checks. Never executed during static construction."""
import argparse
import builtins
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = {'build/ladybug-presentation-cold.bin': 13817, 'build/ladybug-runtime.rom': 16384,
          'build/ladybug-highscore-runtime.bin': 821, 'build/ladybug-player-sparse.bin': 2294}

def require(value, message):
    if not value:
        raise AssertionError(message)

def raises(kind, function):
    try:
        function()
    except kind:
        return
    raise AssertionError('expected ' + kind.__name__)

def install_guards(read_paths, output):
    allowed = {str(Path(p).resolve()) for p in read_paths}
    output = output.resolve()
    original = builtins.__import__
    blocked = {'subprocess','socket','signal','select','ctypes','serial','supervisor','xroar','gdb'}
    def restricted_import(name, *args, **kwargs):
        if name.split('.')[0] in blocked or 'fixture' in name or 'probe' in name:
            raise PermissionError('offline import denied: ' + name)
        return original(name, *args, **kwargs)
    def audit(event, args):
        if event.startswith(('subprocess.', 'socket.', 'ctypes.')) or event in {
            'os.system','os.exec','os.posix_spawn','os.spawn','os.fork','os.forkpty','os.kill','os.killpg'}:
            raise PermissionError('offline API denied: ' + event)
        if event == 'open':
            path, mode, flags = args
            if not isinstance(path, (str, bytes, os.PathLike)):
                raise PermissionError('unscoped file descriptor')
            resolved = Path(os.fsdecode(path)).resolve()
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            within = resolved == output or output in resolved.parents
            if (write and not within) or (not write and str(resolved) not in allowed and not within):
                raise PermissionError('offline file access denied')
        if event in {'os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chdir','os.chmod','os.chown','os.truncate','os.utime','os.startfile','os.startfile/2'}:
            raise PermissionError('offline filesystem mutation denied')
        if event == 'os.mkdir':
            resolved = Path(args[0]).resolve()
            if resolved != output and output not in resolved.parents:
                raise PermissionError('unscoped directory creation')
    builtins.__import__ = restricted_import
    sys.addaudithook(audit)

def unit_cases(m, checkpoint):
    def budget():
        return m.Budget(100, lambda: 0)
    def ops(data):
        checkpoint()
        return list(m.sprite_operations(bytes(data), 0, budget()))
    require(ops((255,0,0)) == [], 'termination')
    require(ops((0,1,7,255,0,0)) == [(0,0,7)], 'ordinary zero')
    require(ops((255,0,2,99,1,7,255,0,0)) == [(2,0,7)], 'extended stage skip')
    require(ops((0,129,240,3,0,1,4,255,0,0)) == [(0,240,3),(1,0,4)], 'mask ordering and advancement')
    for data in ((255,), (255,0), (255,0,1), (0,), (0,129,240), (0,0), (0,1,3)):
        raises(ValueError, lambda data=data: ops(data))
    raises(ValueError, lambda: list(m.sprite_operations(bytes((0,1,1,255,0,0)),30720,budget())))
    r=m.compare_bytes(bytes(100),bytes([255])*100,budget())
    require(r['mismatches']==100 and r['pixel_mismatches']==200 and len(r['samples'])==64,'counts/sample cap')
    r=m.compare_bytes(bytes(128),bytes([1])+bytes(127),budget(),saved=True)
    require(r['samples'][0]['frame_xy']==[152,168] and r['samples'][0]['changed_halves']==[1],'saved coordinates')
    raises(ValueError,lambda:m.compare_bytes(b'',b'x',budget()))
    raises(TimeoutError,lambda:m.Budget(1,lambda:1))
    now=[0]; gate=m.Budget(1,lambda:now[0]);gate.tick(255);now[0]=1
    raises(TimeoutError,lambda:gate.tick())
    checkpoint()

def image_cases(m, data, checkpoint, deadline):
    gate=m.Budget(deadline)
    cold,runtime,highscore,player=[data[name] for name in INPUTS]
    expected=m.expected_images(cold,runtime,highscore,player,gate)
    require(m.digest(m.compose_static(cold,runtime,gate),gate)==m.STATIC_SHA,'actual static hash')
    require(len(expected['saved'])==128 and expected['frame']!=expected['background'],'dynamic/cursor composition')
    saved=bytearray()
    for row in range(16):
        saved.extend(expected['background'][0x694c+row*160:0x694c+row*160+8])
    require(bytes(saved)==expected['saved'],'saved extraction')
    require(m.compare_publications(expected,[expected['frame']]*2,[expected['saved']]*4,gate)['passed'],'exact pair')
    bad=bytearray(expected['frame']);bad[0]^=1
    require(not m.compare_publications(expected,[bytes(bad),expected['frame']],[expected['saved']]*4,gate)['passed'],'frame mismatch')
    bad_save=bytearray(expected['saved']);bad_save[0]^=1
    require(not m.compare_publications(expected,[expected['frame']]*2,[bytes(bad_save)]+[expected['saved']]*3,gate)['passed'],'saved mismatch')
    raises(ValueError,lambda:m.expected_images(cold[:-1],runtime,highscore,player,gate))
    raises(ValueError,lambda:m.expected_images(cold,runtime[:-1],highscore,player,gate))
    raises(ValueError,lambda:m.expected_images(cold,runtime,highscore[:-1],player,gate))
    raises(ValueError,lambda:m.expected_images(cold,runtime,highscore,player[:-1],gate))
    invalid=bytearray(cold);invalid[0x1e26]=0
    raises(ValueError,lambda:m.compose_static(invalid,runtime,gate))
    invalid=bytearray(player);invalid[0]=0x38
    raises(ValueError,lambda:m.expected_images(cold,runtime,highscore,invalid,gate))
    raises(ValueError,lambda:m.dynamic_tile(cold,runtime,219,gate))
    raises(ValueError,lambda:m.compare_publications(expected,[expected['frame']],[expected['saved']]*4,gate))
    # Independently check a dynamic digit's packed row against its typed descriptor.
    tile_id=highscore[0x324];descriptor=0x39a2+tile_id*2
    glyph,colour=runtime[descriptor:descriptor+2]
    if colour:
        row=runtime[0x35c8+glyph*8]
        packed=((colour if row&128 else 0)<<4)|(colour if row&64 else 0)
    else:
        packed=cold[glyph*32]
    require(expected['background'][0x2a84-0x2000]==packed,'dynamic score digit')
    checkpoint()

def fit_cases(m, checkpoint, deadline):
    gate=m.Budget(deadline)
    empty=bytes(30720); actual=bytearray(empty);actual[0]=0x10
    pattern={(0,0):(0,1)}
    one=m.fit_locations(empty,bytes(actual),pattern,gate)
    require(one['unique'] and one['origins']==[[0,0]],'unique origin')
    actual[100]=1
    require(m.fit_locations(empty,bytes(actual),pattern,gate)['count']==0,'outside support residual')
    require(m.fit_locations(empty,empty,{},gate)['count']==0,'no distinguishing pixel')
    # An erased dark pixel can be explained by two distinct partially transparent origins.
    bg=bytearray(empty);bg[1]=0x10
    ambiguous=m.fit_locations(bytes(bg),empty,{(0,0):(0,0),(1,0):(0,0)},gate)
    require(ambiguous['count']==2,'ambiguous origins')
    odd=bytearray(empty);odd[0]=1
    require(m.fit_locations(empty,bytes(odd),pattern,gate)['origins']==[[1,0]],'odd pixel origin')
    require(m.fit_locations(empty,bytes(odd),pattern,gate,exclude=(1,0))['count']==0,'excluded origin')
    expired=[0];interrupt=m.Budget(1,lambda:expired[0]);expired[0]=1
    raises(TimeoutError,lambda:m.fit_locations(empty,empty,pattern,interrupt))
    stream=bytes((0,1,16,255,0,0))
    front=bytearray(empty);front[0x694c]=16
    reference={'background':empty,'frame':bytes(front),'saved':bytes(128)}
    duplicate=bytearray(front);duplicate[0]=16
    report=m.compare_publications(reference,[bytes(duplicate),bytes(front)],[bytes(128)]*4,gate,stream)
    require(report['classification']=='duplicate-confirmed','duplicate classification')
    first=bytearray(empty);first[0]=16
    second=bytearray(empty);second[1]=16
    report=m.compare_publications(reference,[bytes(first),bytes(second)],[bytes(128)]*4,gate,stream)
    require(report['classification']=='alternating-location','alternate origins')
    checkpoint()

def pinned_read(path, size, deadline):
    if time.monotonic()>=deadline:raise TimeoutError('offline check deadline')
    path=Path(path)
    require(path.stat().st_size==size,'input size changed')
    data=bytearray()
    with path.open('rb') as f:
        while len(data)<size:
            if time.monotonic()>=deadline:raise TimeoutError('offline read deadline')
            part=f.read(min(65536,size-len(data)))
            require(bool(part),'truncated input');data.extend(part)
    if time.monotonic()>=deadline:raise TimeoutError('offline read deadline')
    return bytes(data)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--approval',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(args.approval.stat().st_size<=65536,'approval too large')
    approval=json.loads(args.approval.read_text(encoding='utf-8'))
    require(approval.get('offline_approved') is True and approval.get('scope')=='rsch009-comparator-only','offline approval required')
    require(approval.get('execution_approved') is not True,'runtime approval is not offline permission')
    require(approval.get('approved_by') and approval.get('approved_at'),'approval provenance missing')
    duration=approval.get('work_seconds')
    require(type(duration) is int and 0<duration<=420,'offline work limit')
    deadline=time.monotonic()+duration
    def checkpoint():
        if time.monotonic()>=deadline:raise TimeoutError('offline deadline')
    out=args.output.resolve();base=ROOT/'repro/rsch009/offline-checks'
    require(base.is_dir() and out.parent==base.resolve() and not out.exists(),'pre-existing offline root and new direct child required')
    require(str(out)==approval.get('output_path'),'output not approved')
    paths=[HERE/'checks.py',HERE/'compare_pixels.py']+[ROOT/name for name in INPUTS]
    expected=approval.get('sha256',{})
    require(set(expected)=={str(path.relative_to(ROOT)).replace(chr(92),'/') for path in paths},'exact approved hash set required')
    data={}
    for path in paths:
        checkpoint();name=str(path.relative_to(ROOT)).replace(chr(92),'/')
        size=INPUTS.get(name,path.stat().st_size)
        require(size<=1048576,'file size cap')
        raw=pinned_read(path,size,deadline)
        require(hashlib.sha256(raw).hexdigest()==expected[name],'approved hash mismatch')
        data[name]=raw
    comparator_source=data[str((HERE/'compare_pixels.py').relative_to(ROOT)).replace(chr(92),'/')]
    install_guards(paths,out)
    # Compile already pinned source in memory: no alternate path or stale bytecode import.
    namespace={'__name__':'rsch009_local_comparator','__file__':str(HERE/'compare_pixels.py')}
    exec(compile(comparator_source,str(HERE/'compare_pixels.py'),'exec'),namespace)
    # Exercise audit denial without making real process/network calls.
    for event,args in [('os.kill',(0,0)),('os.system',('unused',)),('socket.__new__',())]:
        raises(PermissionError,lambda event=event,args=args:sys.audit(event,*args))
    raises(PermissionError,lambda:__import__('supervisor'))
    class Module:pass
    module=Module()
    for name,value in namespace.items():setattr(module,name,value)
    out.mkdir()
    results=[]
    try:
        for name,case in [('unit',lambda:unit_cases(module,checkpoint)),
                          ('pinned_images',lambda:image_cases(module,data,checkpoint,deadline)),
                          ('location_fits',lambda:fit_cases(module,checkpoint,deadline))]:
            checkpoint();case();checkpoint();results.append({'case':name,'passed':True})
        status='pass'
    except Exception as error:
        status='fail';results.append({'error':str(error)})
    report={'status':status,'scope':'comparator-only','cases':results,'runtime_executed':False}
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    checkpoint()
    return 0 if status=='pass' else 1

if __name__=='__main__':
    raise SystemExit(main())
