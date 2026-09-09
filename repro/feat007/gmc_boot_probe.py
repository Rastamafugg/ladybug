"""Cold boot the actual checkpoint GMC and validate delivered destinations."""
from pathlib import Path
import sys,json,hashlib,inspect
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent/'dynamic';sys.path.insert(0,str(ROOT/'scripts'))
if '--production' in sys.argv:
    from production_runtime_fixture import prepare
    OUT=prepare(ROOT)
import benchmark_6309 as b
namespace=dict(b.__dict__);exec(inspect.getsource(b.launch).replace('"romcart"','"gmc"'),namespace)
main=b.symbols(OUT/'main.map');pres=b.symbols(OUT/'presentation.map');enemy=b.symbols(OUT/'enemy.map')
process,client=namespace['launch'](b.load_monitor(),b.DEFAULT_XROAR,OUT/'ladybug-checkpoint.rom','6809')
checks=[]
try:
    print('phase=GMC-cold-boot marker=mainloop deadline=10s; timeout=boot boundary not reached',flush=True)
    bp=b.set_breakpoint(client,main['mainloop'])
    try:hit=b.run_to_breakpoint(client,10);assert hit['pc']==main['mainloop']
    finally:
        client.call('pause');b.clear_breakpoint(client,bp)
    def identity(label,address,data):
        actual=b.read_bytes(client,address,len(data));diff=[i for i,(a,v) in enumerate(zip(actual,data)) if a!=v]
        checks.append(dict(label=label,exact=not diff,differences=len(diff),sample=diff[:8]))
    identity('resident/assets',0xC000,(OUT/'main.bin').read_bytes())
    identity('presentation',0x1900,(OUT/'presentation.bin').read_bytes())
    identity('enemy',0x800,(OUT/'enemy.bin').read_bytes())
    saved=b.read_bytes(client,0xFFA5,1)
    for page,offset,length in [(0x3A,0,8192),(0x3B,8192,len((OUT/'cold.bin').read_bytes())-8192)]:
        client.call('write_memory',dict(addr=0xFFA5,data=bytes([page]).hex()));identity(f'cold page {page:02X}',0xA000,(OUT/'cold.bin').read_bytes()[offset:offset+length])
    client.call('write_memory',dict(addr=0xFFA5,data='23'))
    identity('instruction staged',0xA422,(OUT/'instruction.bin').read_bytes());identity('demo staged',0xA7CC,(OUT/'demo.bin').read_bytes());identity('ranking staged',0xA880,(OUT/'highscore.bin').read_bytes());identity('page23 helper',0xAC40,(OUT/'highscore-helper.bin').read_bytes())
    client.call('write_memory',dict(addr=0xFFA5,data=saved.hex()))
    def reach(label,address):
        print(f'phase={label} marker=${address:04X} deadline=10s; timeout=phase boundary not reached',flush=True)
        bp=b.set_breakpoint(client,address)
        try:assert b.run_to_breakpoint(client,10)['pc']==address
        finally:client.call('pause');b.clear_breakpoint(client,bp)
    if '--handoffs' in sys.argv:
        reach('natural-demo-install',pres['install_demo_runtime'])
        identity('resident still exact before demo',0xC000,(OUT/'main.bin').read_bytes())
        reach('natural-demo-execution',0x300)
        identity('live demo module',0x300,(OUT/'demo.bin').read_bytes())
        checks.append(dict(label='natural demo mode',exact=b.read_bytes(client,0xA5,1)==bytes([4])))
        client.call('inject_key',dict(key=5,action='press'))
        reach('credit-preempts-demo',pres['start_screen'])
        state=client.call('read_registers');checks.append(dict(label='credit requests ranking',exact=state['a']==3))
        identity('ranking owner installed on credit',0x300,(OUT/'highscore.bin').read_bytes())
        client.call('inject_key',dict(key=5,action='release'))
        reach('ranking-load-started',main['mainloop'])
        client.call('inject_key',dict(key=1,action='press'))
        reach('start-preempts-ranking-load',pres['start_screen'])
        checks.append(dict(label='start requests level',exact=client.call('read_registers')['a']==2))
        client.call('inject_key',dict(key=1,action='release'))
        reach('live-gameplay-init',pres['live_begin'])
        reach('live-mainloop',main['mainloop'])
        checks.append(dict(label='live mode and initialized framebuffer',exact=b.read_bytes(client,0xA5,1)==bytes([0]) and b.read_bytes(client,0x9A,1)!=bytes([0])))
        for frame in range(100):
            bp=b.set_breakpoint(client,main['mainloop'])
            try:assert b.run_to_breakpoint(client,10)['pc']==main['mainloop']
            finally:client.call('pause');b.clear_breakpoint(client,bp)
            if frame>=60 and b.read_bytes(client,0x7F,1)==bytes([0]):break
        assert frame<99,'live replacement work did not settle'
        mapping=b.read_bytes(client,0xFFA1,5)
        font=(OUT.parent/'fit/asset-text-data.bin').read_bytes()[:328]
        descriptors=(OUT.parent/'fit/asset-text-data.bin').read_bytes()[904:]
        tilemap=(OUT.parent/'fit/gameplay-map.bin').read_bytes()
        for owner in (0,1):
            first=0x30-owner*4;client.call('write_memory',dict(addr=0xFFA1,data=bytes(range(first,first+4)).hex()))
            pixels=b.read_bytes(client,0x2000,30720);tested=[];diff=[]
            for cell,ident in enumerate(tilemap):
                if ident<58:continue
                glyph,colour=descriptors[(ident-58)*2:(ident-58)*2+2]
                # Only static nonnumeric HUD labels here; dynamic digits and
                # gameplay letter collectibles need event-specific expectations.
                if glyph<10 or cell//40>2:continue
                base=(cell//40)*1280+(cell%40)*4
                expected=bytes((colour if font[glyph*8+r]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+r]&(64>>(j*2)) else 0) for r in range(8) for j in range(4))
                actual=b''.join(pixels[base+r*160:base+r*160+4] for r in range(8));tested.append(cell)
                if actual!=expected:diff.append(cell)
            checks.append(dict(label=f'live static HUD labels owner {owner}',exact=bool(tested) and not diff,cells=tested,differing_cells=diff))
        client.call('write_memory',dict(addr=0xFFA1,data=mapping.hex()))
    if '--events' in sys.argv:
        assert '--handoffs' in sys.argv
        exec((OUT.parent/'gmc_event_checks.py').read_text())
    if '--focused' in sys.argv:
        assert '--handoffs' in sys.argv
        exec((OUT.parent/'gmc_event_checks.py').read_text().split("print('phase=live-HUD-boundaries")[0])
        exec((OUT.parent/'focused_final_checks.py').read_text())
    report=dict(status='pass' if all(c['exact'] for c in checks) else 'FAIL',checks=checks,dp=b.read_bytes(client,0,256).hex(),production_ready=False,rom_sha256=hashlib.sha256((OUT/'ladybug-checkpoint.rom').read_bytes()).hexdigest())
    (OUT/('focused-final-verification.json' if '--focused' in sys.argv else 'gmc-event-verification.json' if '--events' in sys.argv else 'gmc-handoff-verification.json' if '--handoffs' in sys.argv else 'gmc-boot-verification.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
finally:client.close();b.stop(process)
sys.exit(0 if report['status']=='pass' else 2)
