#!/usr/bin/env python3
"""Extend the shared menu/cold-image oracle; every runtime phase is bounded to 40s."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'scripts'))
p=R/'scripts/verify_feat005_menus.py';s=p.read_text()
s=s.replace('import argparse\n','import argparse\nimport functools\n',1).replace('ROOT = r.ROOT','shared.p.tileset_ranges=functools.lru_cache(None)(shared.p.tileset_ranges)\nROOT = r.ROOT',1)
s=s.replace('and read(0xD4)==0 and read(0x91)==0)', 'and read(0xD4)==0 and read(0x91)==0 and read(0xE1)==0)',1)
s=s.replace("assert r.read_bytes(client,0xB880,len(title))==title", "write(0xFFA5,0x3B)\n        address=0xA000+len((BUILD/'ladybug-presentation-cold.bin').read_bytes())-8192\n        assert r.read_bytes(client,address,len(title))==title")
start=s.index('        key(0x30,6);options_pixels(0)');end=s.index('    finally:',start)
sequence=(R/'repro/keybindings/sequence.py').read_text()
s=s[:start]+sequence+s[end:]
s=s.replace("    check('both high-score bracket publications", "    _,flat,_=shared.p.flatten_map(path)\n        for owner in (0,1):\n            frame=r.read_owner(client,owner)\n            for index,pair in enumerate(pairs):\n                left,row,_=pair[0];right=pair[1][0]\n                for col in range(left+1,right):\n                    raw=shared.p.raw_char_code(root,path,flat[row*40+col]);glyph=raw if raw is not None and raw<=35 else 36\n                    expected=bytearray(30720);dst=0x2000+row*1280+col*4\n                    paint(expected,dst,glyph,10 if index==selection else 7)\n                    assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst),('high-score label colour',owner,index,col)\n        "+"check('both high-score bracket publications")
exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
