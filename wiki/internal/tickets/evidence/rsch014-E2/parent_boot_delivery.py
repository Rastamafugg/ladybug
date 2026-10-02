"""Bounded cold-loader proof; no gameplay or helper-execution acceptance."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,'/mnt/e/projects/ladybug/scripts')
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
w=Path('/mnt/e/projects/ladybug/worktrees/bug086-page34-preparation')
dest=Path('/mnt/e/projects/ladybug/repro/bug086-parent-boot.json')
results=json.loads(dest.read_text())['cases'] if dest.exists() else []
for profile,folder in [('AD1','build')]:
    b=w/folder;ms=r.symbols(b/'ladybug.map')
    fit=json.loads((w/f'wiki/internal/tickets/evidence/rsch014-E2/{profile.lower()}-fit.json').read_text())
    helper=(b/'ladybug-enemy-helper-page34.bin').read_bytes()
    rom=(b/'ladybug.rom').read_bytes();runtime=(b/'ladybug-runtime.rom').read_bytes()
    assert r.digest(rom)==fit['sparse_delivery']['rom_sha256'],'profile artifact identity'
    seg=fit['sparse_delivery']['target_segment'];offset=seg['source_offset']
    staged=(b/'ladybug-gmc-bank0-overflow.bin').read_bytes()
    assert staged[offset:offset+len(helper)]==helper,'authored/staged segment identity'
    cartridge_offset=rom.find(helper)
    assert cartridge_offset>=0 and rom.find(helper,cartridge_offset+1)==-1,'unique staged cartridge helper identity'
    e={'profile':profile,'phase':'cold loader to resident mainloop','deadline_seconds':45,
       'success_marker':hex(ms['mainloop']),'timeout_meaning':'marker/delivery proof absent, not code slowness',
       'rom_sha256':r.digest(rom),'helper_sha256':r.digest(helper),'source_staged_equal':True,
       'cartridge_helper_offset':cartridge_offset,'status':'incomplete'}
    results.append(e);p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),b/'ladybug.rom')
    started=time.monotonic()
    try:
        ids=m.setup(c,[ms['mainloop']])
        c.call('run');hit=c.call('wait_for_stop',{'timeout_ms':45000},timeout=46)
        m.clear(c,ids);assert hit.get('pc')==ms['mainloop'],hit
        a=ms['mainloop'];assert r.read_bytes(c,a,16)==runtime[a-0xC000:a-0xC000+16],'resident/live bytes'
        par5=r.read_bytes(c,0xFFA5,1);par6=r.read_bytes(c,0xFFA6,1)
        physical=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x34*8192+0x8A0,'length':len(helper)})['data'])
        assert physical==helper,'cold loader physical destination'
        c.call('write_memory',{'addr':0xFFA5,'data':'34'})
        try:assert r.read_bytes(c,0xA8A0,len(helper))==helper,'mapped destination'
        finally:c.call('write_memory',{'addr':0xFFA5,'data':par5.hex()})
        e.update(status='scoped-pass',resident_live_equal=True,destination_physical_equal=True,
                 destination_mapped_equal=True,par5=par5.hex(),par6=par6.hex(),wall_seconds=time.monotonic()-started)
    except Exception as exc:e['failure']=repr(exc);raise
    finally:
        r.stop(p);dest.write_text(json.dumps({'cases':results,'limitation':'Loader delivery only; no natural helper calls, death/replacement or pixel proof.'},indent=2)+'\n')
