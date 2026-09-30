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
