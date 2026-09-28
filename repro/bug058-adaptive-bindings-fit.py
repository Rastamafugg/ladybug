"""Assemble isolated real-call bindings against exact committed reference maps."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
ref,fit,out=map(Path,sys.argv[1:4]);b=ref/'build';d=fit/'build/adaptive-fit/bindings';d.mkdir(parents=True,exist_ok=True)
def symbols(path):
    return {k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',path.read_text(),re.M)}
syms=symbols(b/'ladybug.map');syms.update(symbols(b/'ladybug-enemy-runtime.map'))
source=(fit/'src/adaptive_bindings.s').read_text()
names=set(re.findall(r'\b(?:jsr|jmp|lda|ldb|ldd|sta|stb|std|tst|clr|ora|anda)\s+([A-Za-z_]\w*)',source))
names={n for n in names if n in syms}
(d/'adaptive_reference.inc').write_text(''.join(f'{n} equ ${syms[n]:04X}\n' for n in sorted(names)))
prefix=source[:source.index('        org $05DE')]
segments=[('tick',source[source.index('        org $05DE'):source.index('; Old resident mainloop')],0x05DE,186,'adaptive_copied_bindings_end'),('resident',source[source.index('        org $C0FF'):source.index('; Existing resident tail')],0xC0FF,145,'adaptive_resident_bindings_end'),('installer',source[source.index('        org $DFE8'):],0xDFE8,24,'adaptive_install_copy_end')]
result={'phase':'host real-call assembly only','reference_rom_sha256':hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((fit/'src/adaptive_bindings.s').read_bytes()).hexdigest(),'placements':[],'limitations':['Installer phase hooks, adaptive main driver, removal of duplicate demo calls and elapsed audio >1 remain unbound.','Resident placement displaces the old main loop; copied tail needs natural phase lifetime proof.','This assembly receipt alone proves no runtime, pixel, input, audio or complete ROM acceptance.']}
for name,body,address,limit,end in segments:
    p=d/(name+'.s');p.write_text(prefix+body)
    subprocess.run(['lwasm','-9','--format=raw','-I',str(d),'--output='+str(d/(name+'.bin')),'--map='+str(d/(name+'.map')),'--list='+str(d/(name+'.lst')),str(p)],check=True)
    data=(d/(name+'.bin')).read_bytes();ms=symbols(d/(name+'.map'));assert len(data)==ms[end]-address
    result['placements'].append({'name':name,'address':address,'bytes':len(data),'limit':limit,'free':limit-len(data),'sha256':hashlib.sha256(data).hexdigest(),'fits':len(data)<=limit})
audio_source=(fit/'src/adaptive_audio_bindings.s').read_text();audio_syms=symbols(b/'ladybug-audio-runtime.map')
needed={n for n in re.findall(r'\b(?:jsr|lda|ldb|sta|clr)\s+([A-Za-z_]\w*)',audio_source) if n in audio_syms}
(d/'adaptive_audio_reference.inc').write_text(''.join(f'{n} equ ${audio_syms[n]:04X}\n' for n in sorted(needed)))
p=fit/'src/adaptive_audio_bindings.s'
subprocess.run(['lwasm','-9','--format=raw','-I',str(d),'--output='+str(d/'audio.bin'),'--map='+str(d/'audio.map'),'--list='+str(d/'audio.lst'),str(p)],check=True)
data=(d/'audio.bin').read_bytes();assert 0xB62B+len(data)<=0xC000
result['placements'].append({'name':'audio safe-subset API','address':0xB62B,'bytes':len(data),'limit':0xC000-0xB62B,'free':0xC000-0xB62B-len(data),'sha256':hashlib.sha256(data).hexdigest(),'fits':True})
result['audio_source_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
assert len((d/'tick.bin').read_bytes())==134 and len(data)==140,'installer stage/count constants must match actual assembly'
result['limitations'].append('Audio elapsed >1 is explicitly rejected; no multi-refresh audio success claimed.')
result['status']='pass' if all(v['fits'] for v in result['placements']) else 'rejected'
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
