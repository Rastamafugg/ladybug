#!/usr/bin/env python3
"""Reuse live-session verification for the menu/name-entry phase alias.

Exclude the displaced pre-adaptive timing fixture and unchanged vegetable HUD.
Retain natural start priority, both terminal paths, and name timeout within the
base verifier's 40-second marker deadlines. Missing transitions fail.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'repro/feat005/verify_live_session.py'
source = path.read_text()
first = source.index("    monitor.clear(client,ids)\n    assert r.read_bytes(client,main['mainloop'],1)")
last = source.index('    # Force only the rare last-life boundary', first)
source = source[:first] + '    monitor.clear(client,ids)\n' + source[last:]
first = source.index('    # Isolated CPU calls follow all natural sequence checks.')
last = source.index('except Exception as error:', first)
source = source[:first] + "    report['status']='pass'\n" + source[last:]
source = source.replace("    keys([1,0x30],'press')",
    "    write(0xE1,3)  # pending menu edit must retire on credited start\n    keys([1,0x30],'press')", 1)
source = source.replace("    wait('returned high scores published',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)",
    "    wait('returned high scores published',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)\n    assert read(0xE1)==0", 1)
source = source.replace("    check('qualified score naturally completes name timeout and preserves session settings',qualified)",
    "    check('qualified score naturally completes name timeout and preserves session settings',qualified)\n"
    "    monitor.clear(client,ids);ids=monitor.setup(client,[0x1900])\n"
    "    wait('post-name menu publication',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)\n"
    "    assert read(0xE1)==0\n"
    "    check('name-repeat alias retires before high-score menu')", 1)
source = source.replace('feat005-live-session-20260930.json', 'feat005-menu-redraw-phase-exit-20260930.json')
exec(compile(source, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
