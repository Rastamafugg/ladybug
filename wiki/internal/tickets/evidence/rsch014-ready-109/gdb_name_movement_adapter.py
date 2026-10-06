"""Current joint HUD observer plus real remapped name movement callsites."""
from pathlib import Path
base=Path(__file__).with_name('gdb_name_hud_adapter.py')
exec(compile(base.read_text().split('extra=r"""')[0],str(base)+'[movement-preparation]','exec'))
branch=r"""  phase('name-controls-legal-remapping')
  gdb([f'set {{unsigned char}}0x{0x287+i:x}={v}' for i,v in enumerate((58,26,8,32,59))])
  lm=symbols(B/'ladybug-highscore-runtime.map');cold=(B/'ladybug-presentation-cold.bin').read_bytes();edge_base=hm['PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE'];masks=cold[edge_base:edge_base+576]
  helper_path=Path(__file__).with_name('x11_probe_key_edge.py')
  def edge(keyname,pressed):return f'shell python3 {helper_path} {window} {keyname} {pressed}'
  def legal_cell(direction,allowed=True,other=None):
   for i,mask in enumerate(masks):
    if mask and bool(mask&(1<<direction))==allowed and (other is None or mask&(1<<other)):
     y,x=divmod(i,24)
     if 3<=y<=18 and 1<=x<=22:return x+8,y,mask
   raise AssertionError('required legal mask predecessor missing')
  def fixture(x,y,old=255,steps=0):
   ptr=0x2000+y*1280+x*4
   if steps:ptr+=(-320,1,320,-1)[old]*(4-steps)
   return [f'break *0x{lm["name_tick"]:x}','condition $bpnum *(unsigned char*)0xa5==8 && (*(unsigned char*)0x3&1)==0','continue','printf "MOVE TICK BOUNDARY\\n"']+live_pc_guard(lm['name_tick'],low,0x300)+['delete breakpoints',f'dump binary memory {O}/movement-fixture-dp.bin 0 0x300',f'dump binary memory {O}/movement-live-low.bin 0x300 0x{0x300+len(low):x}',f'set {{unsigned char}}0x9={x}',f'set {{unsigned char}}0xa={y}',f'set {{unsigned short}}0xb={ptr}',f'set {{unsigned char}}0xe0={x}',f'set {{unsigned char}}0xdf={y}',f'set {{unsigned char}}0xde={steps}','set {unsigned char}0x56=0',f'set {{unsigned char}}0x6={old}',f'set {{unsigned char}}0x7={0 if old==255 else old}','set {unsigned char}0xf=255']
  original_gdb=gdb
  def gdb(commands):
   try:return original_gdb(commands)
   except subprocess.TimeoutExpired as error:
    raw=error.stdout or b''
    if isinstance(raw,str):raw=raw.encode()
    (O/'movement-timeout-stdout.log').write_bytes(raw)
    report['phases'][-1]['gdb_timeout_stdout']=raw.decode(errors='replace')
    raise
  samples=[];keys=('w','d','s','a')
  for allowed in (True,False):
   for direction,keyname in enumerate(keys):
    phase(('allowed' if allowed else 'blocked')+'-remapped-cardinal-'+str(direction));x,y,mask=legal_cell(direction,allowed)
    report['phases'][-1]['fixture']='Legal authored nonzero-mask cursor predecessor; neutral heading/progress, real remapped key; no edge table, score/name, frame, owner, PC or stack writes.'
    commands=fixture(x,y)+[f'break *0x{lm["name_can_move"]:x}',edge(keyname,1),'continue','printf "MOVE FUNCTION BOUNDARY\\n"']+live_pc_guard(lm['name_can_move'],low,0x300)+['set $call_s=$s','set $caller=*(unsigned short*)$s','printf "MOVE-DIRECTION=%u\\n",$a','tbreak *$caller','continue',edge(keyname,0),'if $s!=$call_s+2','printf "MOVE STACK IMBALANCE\\n"','quit 1','end','printf "MOVE-RESULT=%u,%u\\n",$a,($cc&4)!=0','delete breakpoints']
    raw=gdb(commands);check('complete movement low-owner identity',(O/'movement-live-low.bin').read_bytes()==low)
    requested=int(re.search(r'MOVE-DIRECTION=(\d+)',raw).group(1));result,z=map(int,re.search(r'MOVE-RESULT=(\d+),(\d+)',raw).groups())
    check('real remapped direction reaches actual move caller',requested==direction)
    check('compiled move boolean and Z match authored edge',bool(result)==allowed and bool(z)==(not allowed))
    samples.append({'direction':direction,'cell':[x,y],'mask':mask,'allowed':allowed,'result':result,'Z':z,'stack':'natural RTS restored caller stack','trace_sha256':hashlib.sha256(raw.encode()).hexdigest()})
  report['cardinal_samples']=samples
  phase('active-name-reversal')
  x,y,mask=legal_cell(1,True);ptr=0x2000+y*1280+x*4+2
  commands=fixture(x,y,1,2)+[f'break *0x{lm["name_move_active"]:x}',edge('a',1),'continue']+live_pc_guard(lm['name_move_active'],low,0x300)+[f'dump binary memory {O}/movement-reverse-dp.bin 0 0x300',edge('a',0),'delete breakpoints']
  raw=gdb(commands);movement_state=(O/'movement-reverse-dp.bin').read_bytes();check('active reversal preserves physical point and changes target heading',movement_state[6]==3 and movement_state[7]==3 and movement_state[9]==x+1 and movement_state[10]==y and int.from_bytes(movement_state[11:13],'big')==ptr and movement_state[0xde]==2)
  phase('active-name-perpendicular-late-turn')
  x,y,mask=legal_cell(0,True,1);commands=fixture(x,y,1,2)+[f'break *0x{main["nlt_yes"]:x}',edge('w',1),'continue']+live_pc_guard(main['nlt_yes'],resident,0xc000)+[f'dump binary memory {O}/movement-late-dp.bin 0 0x300',edge('w',0),'delete breakpoints']
  raw=gdb(commands);movement_state=(O/'movement-late-dp.bin').read_bytes();check('late-turn caller accepts nonzero without normalization',movement_state[6]==0 and movement_state[7]==0 and movement_state[0xde]==4 and movement_state[0x56]==2 and movement_state[0x57]==1)
  report['movement']={'cardinal_samples':samples,'reversal':'actual caller updates target/heading while keeping physical point','late_turn':'actual resident caller admits perpendicular turn with compiled boolean mask','bindings':'disclosed previously UI-tested W/S/A/D/Space mapping; actual remapped host edges','limits':'Legal cursor/progress predecessors are fixtures. No natural traversal of every name route claimed.'}
  report['status']='PASS-CURRENT-NAME-CARDINAL-STACK-REVERSAL-LATE-TURN';raise SystemExit(0)
"""
assert source.count(marker)==1
source=source.replace(marker,branch,1)
exec(compile(source,str(base)+'[movement-regression]','exec'))
