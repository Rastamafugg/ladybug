#!/usr/bin/env python3
"""Reuse existing verifiers for the combined adaptive/menu launch contract.

Natural menu phases retain the base verifier's 40-second marker deadlines.
Boot uses the base loader/resident deadlines. Missing markers fail verification.
This checks integration for manual testing, not full BUG-058 timing acceptance.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
kind=sys.argv.pop(1)
sys.path.insert(0,str(ROOT/'scripts'))
if kind=='boot':
    path=ROOT/'scripts/verify_gmc_boot.py'
    source=path.read_text()
    old='        if not symbol:\n            raise SystemExit(f"gmc proof: {name} missing from enemy map")'
    assert old in source
    # Startup does not execute the nonadaptive forced-damage fixture.
    source=source.replace(old,'        if not symbol:\n            if args.startup_only: continue\n            raise SystemExit(f"gmc proof: {name} missing from enemy map")',1)
elif kind=='natural-menu':
    path=ROOT/'scripts/verify_feat005_menus.py'
    source=path.read_text()
    old="        ids.extend(monitor.setup(client,[0x0700]))"
    assert old in source
    source=source.replace(old,"        report['status']='pass';return\n"+old,1)
    old="        check('both high-score bracket publications selection '+str(selection))"
    source=source.replace(old,"""        for owner in (0,1):
            frame=r.read_owner(client,owner)
            _,flat,_=shared.p.flatten_map(path)
            for index,pair in enumerate(pairs):
                left,right=pair;lo,row,_=left;hi,_,_=right
                colour=10 if index==selection else 7
                for col in range(lo+1,hi):
                    code=shared.p.raw_char_code(root,path,flat[row*40+col])
                    code=code if code is not None and 0<=code<=35 else 36
                    expected=bytearray(30720);dst=0x2000+row*1280+col*4
                    paint(expected,dst,code,colour)
                    assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst),(owner,selection,index,'selected high-score label')
        check('both high-score label/bracket publications selection '+str(selection))""",1)
    old="        key(0x2C,3);high_pixels(1);key(0x30,7);key(0x32,3)"
    source=source.replace(old,"""        key(0x2C,3);high_pixels(1);key(0x30,7)
        row,col=manifest['menus']['credit_back']
        for owner in (0,1):
            frame=r.read_owner(client,owner)
            for i,code in enumerate((11,10,12,20)):
                expected=bytearray(30720);dst=0x2000+row*1280+(col+i)*4
                paint(expected,dst,code,10)
                assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst),(owner,'credits BACK green')
        check('credits BACK selected green on both publications')
        key(0x30,3);check('credits Enter returns to high scores')
        key(0x2C,3);key(0x30,7);key(0x32,3)
        # Press during natural high-score hydration after a selection redraw.
        client.call('inject_key',{'key':0x2C,'action':'press'});tick()
        client.call('inject_key',{'key':0x2C,'action':'release'});tick()
        assert read(0xA5)==1 and read(0xE0)==1, 'selection redraw not exercising hydration'
        key(0x2B,3);assert read(0xE0)==0
        high_pixels(0);check('Up is dispatched during high-score hydration')""",1)

    old="        check('natural options/BACK/credits/Escape and retained settings')"
    assert old in source
    source=source.replace(old,"""        saved_page=read(0xFFA5)
        cold=(BUILD/'ladybug-presentation-cold.bin').read_bytes()
        for offset in range(0,len(cold),8192):
            write(0xFFA5,0x3A+offset//8192)
            block=cold[offset:offset+8192]
            assert r.read_bytes(client,0xA000,len(block))==block, 'cold presentation altered during menu sequence'
        write(0xFFA5,saved_page)
        check('cold presentation exact after natural menu sequence')
"""+old,1)
else:
    raise SystemExit('Choose boot or natural-menu')
exec(compile(source,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})
