"""Current joint HUD observer plus real remapped name movement callsites."""
from pathlib import Path
base=Path(__file__).with_name('gdb_name_hud_adapter.py')
exec(compile(base.read_text().split('extra=r"""')[0],str(base)+'[movement-preparation]','exec'))
branch=r"""  phase('held-remapped-input-before-movement')
  gdb([f'set {{unsigned char}}0x{0x287+i:x}={v}' for i,v in enumerate((58,26,8,32,59))])
  helper_path=Path(__file__).with_name('x11_probe_key_edge.py');pc=main['mainloop']+5
  commands=[f'shell python3 {helper_path} {window} w 1','set $input_start=*(unsigned short*)0x2',f'break *0x{pc:x}','condition $bpnum *(unsigned char*)0xa5==8 && (((*(unsigned short*)0x2)-$input_start)&65535)>=6','continue']+live_pc_guard(pc,resident,0xc000)+[f'dump binary memory {O}/held-remapped-input-dp.bin 0 0x300',f'shell python3 {helper_path} {window} w 0','delete breakpoints']
  raw=gdb(commands);movement_state=(O/'held-remapped-input-dp.bin').read_bytes();report['input_boundary']={'mode':movement_state[0xa5],'bindings':list(movement_state[0x287:0x28c]),'mapped_down':movement_state[0x296],'JOY_DIR':movement_state[5],'PLAYER_WANT':movement_state[15],'player_cell':list(movement_state[9:11]),'direction':movement_state[6],'face':movement_state[7]}
  check('held host remapped W reaches name movement input',movement_state[0xa5]==8 and movement_state[0x296]==1 and movement_state[5]==0)
  report['status']='PASS-HELD-REMAPPED-NAME-INPUT-BOUNDARY';raise SystemExit(0)
"""
source=source.replace(marker,branch,1)
exec(compile(source,str(base)+'[held-input-boundary]','exec'))
