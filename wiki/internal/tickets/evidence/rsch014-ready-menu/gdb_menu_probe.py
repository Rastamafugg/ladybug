import ctypes as c,subprocess,time,json,os,hashlib,re,sys
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--worktree',type=Path,required=True);p.add_argument('--rom-sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prompt-only',action='store_true');p.add_argument('--bindings',action='store_true');p.add_argument('--name-only',action='store_true');p.add_argument('--entry-edges-only',action='store_true');p.add_argument('--hud-parts',action='store_true');p.add_argument('--hud-lives',action='store_true');p.add_argument("--level-part",type=int,choices=range(1,256));p.add_argument("--next-part",type=int,choices=range(1,256));p.add_argument('--stage-score',type=str);p.add_argument('--trademark',choices=('baseline','red'));p.add_argument('--instructions-static',action='store_true');p.add_argument('--hud-equals',choices=('baseline','green'));p.add_argument('--instructions-multipliers',choices=('baseline','blue'));a=p.parse_args()
if a.stage_score is not None:
 assert len(a.stage_score)==6 and a.stage_score.isdigit(),'six BCD decimal score digits required'
 assert a.level_part or a.next_part,'stage-score requires a level-part or next-part scenario'
if a.hud_equals:assert a.instructions_static or a.level_part or a.next_part,'equals requires instructions or level-start scenario'
ROOT=a.worktree.resolve();B=ROOT/'build';O=ROOT/'repro/ready-menu-gdb';O.mkdir(parents=True,exist_ok=True)
assert not a.output.exists(),'output exists'
assert hashlib.sha256((B/'ladybug.rom').read_bytes()).hexdigest()==a.rom_sha256,'ROM identity mismatch'
xlib=c.CDLL('libX11.so.6');xlib.XOpenDisplay.restype=c.c_void_p;xlib.XDefaultRootWindow.argtypes=[c.c_void_p];xlib.XDefaultRootWindow.restype=c.c_ulong
xlib.XQueryTree.argtypes=[c.c_void_p,c.c_ulong,c.POINTER(c.c_ulong),c.POINTER(c.c_ulong),c.POINTER(c.POINTER(c.c_ulong)),c.POINTER(c.c_uint)]
xlib.XFetchName.argtypes=[c.c_void_p,c.c_ulong,c.POINTER(c.c_char_p)];xlib.XFree.argtypes=[c.c_void_p]
xlib.XStringToKeysym.argtypes=[c.c_char_p];xlib.XStringToKeysym.restype=c.c_ulong;xlib.XKeysymToKeycode.argtypes=[c.c_void_p,c.c_ulong];xlib.XKeysymToKeycode.restype=c.c_uint
class Key(c.Structure):_fields_=[('type',c.c_int),('serial',c.c_ulong),('send_event',c.c_int),('display',c.c_void_p),('window',c.c_ulong),('root',c.c_ulong),('subwindow',c.c_ulong),('time',c.c_ulong),('x',c.c_int),('y',c.c_int),('x_root',c.c_int),('y_root',c.c_int),('state',c.c_uint),('keycode',c.c_uint),('same_screen',c.c_int)]
class Event(c.Union):_fields_=[('key',Key),('pad',c.c_long*24)]
xlib.XSendEvent.argtypes=[c.c_void_p,c.c_ulong,c.c_int,c.c_long,c.POINTER(Event)];xlib.XFlush.argtypes=[c.c_void_p]
d=xlib.XOpenDisplay(None);assert d;root=xlib.XDefaultRootWindow(d)
def windows(w):
 name=c.c_char_p();xlib.XFetchName(d,w,c.byref(name));title=name.value.decode(errors='replace') if name.value else '';xlib.XFree(name)
 yield w,title
 rr=c.c_ulong();pp=c.c_ulong();children=c.POINTER(c.c_ulong)();n=c.c_uint()
 if xlib.XQueryTree(d,w,c.byref(rr),c.byref(pp),c.byref(children),c.byref(n)):
  ids=[children[i] for i in range(n.value)];xlib.XFree(children)
  for ch in ids:yield from windows(ch)
xtest=c.CDLL('libXtst.so.6');xtest.XTestFakeKeyEvent.argtypes=[c.c_void_p,c.c_uint,c.c_int,c.c_ulong]
xlib.XSetInputFocus.argtypes=[c.c_void_p,c.c_ulong,c.c_int,c.c_ulong]
xlib.XInternAtom.argtypes=[c.c_void_p,c.c_char_p,c.c_int];xlib.XInternAtom.restype=c.c_ulong
xlib.XGetWindowProperty.argtypes=[c.c_void_p,c.c_ulong,c.c_ulong,c.c_long,c.c_long,c.c_int,c.c_ulong,c.POINTER(c.c_ulong),c.POINTER(c.c_int),c.POINTER(c.c_ulong),c.POINTER(c.c_ulong),c.POINTER(c.POINTER(c.c_ubyte))]
def window_pid(w):
 atom=xlib.XInternAtom(d,b'_NET_WM_PID',1)
 actual=c.c_ulong();fmt=c.c_int();count=c.c_ulong();remaining=c.c_ulong();data=c.POINTER(c.c_ubyte)()
 if not atom:return None
 status=xlib.XGetWindowProperty(d,w,atom,0,1,0,0,c.byref(actual),c.byref(fmt),c.byref(count),c.byref(remaining),c.byref(data))
 try:
  return c.cast(data,c.POINTER(c.c_ulong))[0] if status==0 and fmt.value==32 and count.value==1 else None
 finally:
  if data:xlib.XFree(data)
class WindowAttributes(c.Structure):
 _fields_=[('x',c.c_int),('y',c.c_int),('width',c.c_int),('height',c.c_int),('border',c.c_int),('depth',c.c_int),('visual',c.c_void_p),('root',c.c_ulong),('kind',c.c_int),('bit_gravity',c.c_int),('win_gravity',c.c_int),('backing_store',c.c_int),('backing_planes',c.c_ulong),('backing_pixel',c.c_ulong),('save_under',c.c_int),('colormap',c.c_ulong),('map_installed',c.c_int),('map_state',c.c_int),('all_event_masks',c.c_long),('your_event_mask',c.c_long),('do_not_propagate_mask',c.c_long),('override_redirect',c.c_int),('screen',c.c_void_p)]
xlib.XGetWindowAttributes.argtypes=[c.c_void_p,c.c_ulong,c.POINTER(WindowAttributes)]
def visible_window(w):
 attrs=WindowAttributes()
 return bool(xlib.XGetWindowAttributes(d,w,c.byref(attrs))) and attrs.map_state==2 and attrs.width>1 and attrs.height>1
held_keys=set()
def key(name,states=(1,0)):
 code=xlib.XKeysymToKeycode(d,xlib.XStringToKeysym(name.encode()));assert code
 xlib.XSetInputFocus(d,window,1,0)
 for pressed in states:
  assert xtest.XTestFakeKeyEvent(d,code,pressed,0);xlib.XFlush(d);time.sleep(.2)
  if pressed:held_keys.add(code)
  else:held_keys.discard(code)
 time.sleep(1)
def gdb(lines):
 p=O/'probe.gdb';p.write_text('\n'.join(['set pagination off','set confirm off','set remotetimeout 3','set architecture m6809','target remote 127.0.0.1:65522',*lines,'detach','quit'])+'\n')
 r=subprocess.run(['m6809-gdb','-q','-nx','-batch','-x',str(p)],capture_output=True,text=True,timeout=min(40,max(.1,deadline-time.monotonic())));assert r.returncode==0,r.stdout+r.stderr
 return r.stdout+r.stderr

def symbols(path):
 return {k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',path.read_text(),re.M)}
main=symbols(B/'ladybug.map');pres=symbols(B/'ladybug-presentation-runtime.map')
assert 'mainloop' in main and 'attract_tick' in pres,'current markers absent'
rom=(B/'ladybug.rom').read_bytes();resident=(B/'ladybug-runtime.rom').read_bytes()[:0x3e00]
report={'status':'FAIL','rom_sha256':a.rom_sha256,'scope':'Existing X11 host-key/GDB probe adapted for current menu; no monitor protocol extension','phases':[]}
def phase(name):
 global deadline,phase_started
 if report['phases']:report['phases'][-1]['elapsed_seconds']=round(time.monotonic()-phase_started,3)
 phase_started=time.monotonic()
 deadline=time.monotonic()+40
 report['phases'].append({'name':name,'deadline_seconds':40,'timeout_meaning':'named publication/input boundary not observed; not target speed evidence'})
def snapshot():
 gdb(['dump binary memory '+str(O/'dp.bin')+' 0 0x300'])
 dp=(O/'dp.bin').read_bytes();row={'mode':dp[0xa5],'screen':dp[0xa6],'credits':dp[0xa8],'pending':dp[0x91],'transaction':dp[0xd4],'selection':dp[0xe0],'live':dp[0xa7],'bindings':list(dp[0x287:0x28c]),'binding_state':dp[0x298],'mapped_down':dp[0x296],'player_cell':list(dp[9:11]),'player_want':dp[5],'entry':dp[0xa0],'front':dp[0x8f]}
 report['phases'][-1].setdefault('snapshots',[]).append(row);return row
def settled(screen):
 while True:
  assert time.monotonic()<deadline,'publication deadline'
  q=snapshot()
  if q['screen']==screen and q['mode']==5 and q['pending']==0 and q['transaction']==0:return q
  time.sleep(.05)
def check(name,predicate):
 assert predicate,name
 report['phases'][-1].setdefault('checks',[]).append(name)
def front_frame(owner=None):
 commands=['set $owner=*(unsigned char*)0x8f' if owner is None else 'set $owner='+str(owner)]
 for i in range(4):
  commands += [f'set $p{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}=($owner==0 ? {0x30+i} : {0x2c+i})']
 commands += [f'dump binary memory {O}/front.bin 0x2000 0x9800']
 commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$p{i}' for i in range(4)]
 gdb(commands);return (O/'front.bin').read_bytes()
def prompt_pixels():
 sys.path.insert(0,str(ROOT/'scripts'));import build_presentation as palette
 frame=front_frame();chars=palette.load_chars(ROOT/'assets/arcade/chars.json')
 for lo,row,value,colour in ((13,15,'PRESS 5 OR 6 TO',9),(13,19,'1',None),(15,19,'COIN',None),(21,19,'1',None),(23,19,'PLAY',None)):
  for col,char in enumerate(value,lo):
   code=255 if char==' ' else int(char) if char.isdigit() else ord(char)-55
   pixels=palette.rotate_ccw(chars[code])
   pens=(0,1,2,3) if colour is None else (0,colour,colour,colour)
   expected=bytes(pens[pixels[y][j*2]]*16+pens[pixels[y][j*2+1]] for y in range(8) for j in range(4))
   actual=b''.join(frame[(row*8+y)*160+col*4:(row*8+y)*160+col*4+4] for y in range(8))
   check('natural prompt row '+str(row)+' col '+str(col),actual==expected)
 report['phases'][-1]['front_frame_sha256']=hashlib.sha256(frame).hexdigest()
def label_pixels(value):
 sys.path.insert(0,str(ROOT/'scripts'))
 import verify_shared_text as shared
 font=shared.values((B/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
 translation=shared.values((B/'ladybug_stage_glyphs.inc').read_text(),'stage_source_glyphs','no_end')
 frame=front_frame()
 # Approved START GAME occupies columns17..26; ADD CREDITS also uses the existing blank column16.
 row,lo,hi=20,16,26
 value=(' '+value if value=='START GAME' else value).ljust(hi-lo+1)
 for col,char in enumerate(value,lo):
  code=36 if char==' ' else int(char) if char.isdigit() else ord(char)-55
  mask=font[translation[code]*8:translation[code]*8+8]
  expected=bytes((10 if mask[y]&(128>>(j*2)) else 0)*16+(10 if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
  actual=b''.join(frame[(row*8+y)*160+col*4:(row*8+y)*160+col*4+4] for y in range(8))
  check('visible '+value.strip()+' cell '+str(col),actual==expected)
 report['phases'][-1]['front_frame_sha256']=hashlib.sha256(frame).hexdigest()
def await_state(label,predicate):
 while True:
  assert time.monotonic()<deadline,label+' deadline'
  q=snapshot()
  if predicate(q):return q
  time.sleep(.05)
def hud_probe(lives=False):
 sys.path.insert(0,str(ROOT/'scripts'));import verify_shared_text as shared
 inc=(B/'ladybug_screen.inc').read_text();mapping=shared.values(inc,'screen_map','screen_tiles');tiles=shared.values(inc,'screen_tiles','gate_state_tiles')
 font=shared.values((B/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
 manifest=json.loads((B/'ladybug-presentation.json').read_text());part_colour=manifest['shared_text']['colour_configuration']['fields']['part']
 def crop(frame,x,y):return b''.join(frame[(y*8+r)*160+x*4:(y*8+r)*160+x*4+4] for r in range(8))
 def publish_intent(value):
  commands=[f'break *0x{main["mainloop"]:x}','continue','delete breakpoints','set {unsigned char}0x'+('23' if lives else '24')+'='+str(value),'set $saved5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34']
  for address,count in ((0xbc04,0xbd38),(0xbc94,0xbd39)):
   commands += [f'if *(unsigned char*)0x{count:x}==0']+[f'set {{unsigned char}}0x{address+i:x}=0' for i in range(18)]+[f'set {{unsigned char}}0x{count:x}=1','end',f'set {{unsigned char}}0x{address:x}=*(unsigned char*)0x{address:x}|{4 if lives else 2}']
  commands += ['set {unsigned char}0xffa5=$saved5'];gdb(commands)
 for value in ((12,11,10,9,7,6,4,3,1,0) if lives else (1,9,10,99,100,199,200,255,1)):
  phase(('reserve-grid-' if lives else 'part-field-')+str(value));report['phases'][-1]['forced_state']='Stop at exact verified resident mainloop boundary; set '+('reserve LIVES' if lives else 'STAGE')+' and merge HUD-only intent into both existing owner histories using the delivered adaptive_credit_history layout; normal callback renders/publishes, no forced PC.'
  publish_intent(value);expected={}
  if lives:
   for slot in range(12):
    x,y=33+2*(slot%3),21-2*(slot//3)
    for dy in range(2):
     for dx in range(2):
      index=mapping[(y+dy)*40+x+dx];tile=tiles[index*32:(index+1)*32]
      expected[x+dx,y+dy]=tile if slot<value else bytes(32)
  else:
   for offset,char in enumerate((' ' if value<100 else str(value//100))+f'{value%100:02d}'):
    mask=bytes(8) if char==' ' else font[int(char)*8:int(char)*8+8]
    expected[37+offset,11]=bytes((part_colour if mask[y]&(128>>(j*2)) else 0)*16+(part_colour if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
  while True:
   assert time.monotonic()<deadline,'both-owner HUD pixel deadline'
   actual={owner:front_frame(owner) for owner in (0,1)}
   if 'first_observation' not in report['phases'][-1]:
    report['phases'][-1]['first_observation']={'state':snapshot(),'wrong_cells':{str(owner):[[x,y] for (x,y),tile in expected.items() if crop(frame,x,y)!=tile] for owner,frame in actual.items()}}
   if all(crop(frame,x,y)==tile for frame in actual.values() for (x,y),tile in expected.items()):break
   time.sleep(.05)
  check('both natural owner replays equal exact authored cells',True)
  report['phases'][-1]['owner_frame_sha256']={str(owner):hashlib.sha256(frame).hexdigest() for owner,frame in actual.items()}
 report['qualification']='Controlled reserve/part HUD callback test, not initial-life/death accounting or natural level-start acceptance; journal mutation disclosed per phase.'
def hud_equals_pixels(frame):
 sys.path.insert(0,str(ROOT/'scripts'));import build_presentation as palette
 rows=palette.rotate_ccw(palette.load_chars(ROOT/'assets/arcade/chars.json')[42])
 pen=6 if a.hud_equals=='baseline' else 5
 expected=bytes((pen if rows[y][j*2] else 0)*16+(pen if rows[y][j*2+1] else 0) for y in range(8) for j in range(4))
 actual=b''.join(frame[(104+y)*160+136:(104+y)*160+140] for y in range(8))
 check('side-HUD equals independent raw42 mask pen '+str(pen),actual==expected)
 check('equals mask has foreground',any(expected))
 for col in range(35,39):
  cell=b''.join(frame[(104+y)*160+col*4:(104+y)*160+col*4+4] for y in range(8))
  foreground=[pixel for byte in cell for pixel in (byte>>4,byte&15) if pixel]
  check('adjacent vegetable value digit '+str(col)+' green5',bool(foreground) and set(foreground)=={5})
 report['phases'][-1]['equals_oracle']='Independent rotated raw character42; baseline white6 or target green5; four adjacent nonblank digit cells green5.'

def instruction_static_probe():
 phase('natural-instructions-hidden-hydration')
 # Stop before the first instruction timer/actor tick, after both owner hydrations.
 # One attached GDB batch retains the boundary while capturing delivery and pixels.
 address=pres['instructions_tick_ready']
 staged=pres['PRESENTATION_INSTRUCTION_RUNTIME_ADDRESS']
 authored=(B/'ladybug-instruction-runtime.bin').read_bytes()
 commands=[f'break *0x{address:x}','continue','delete breakpoints',
  f'dump binary memory {O}/instruction-destination.bin 0x300 0x{0x300+len(authored):x}',
  'set $saved5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x23',
  f'dump binary memory {O}/instruction-staged.bin 0x{staged:x} 0x{staged+len(authored):x}',
  'set {unsigned char}0xffa5=$saved5',
  f'dump binary memory {O}/instruction-boundary.bin 0x8f 0xda']
 for owner in (0,1):
  for i in range(4):
   commands += [f'set $p{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}={0x30+i if owner==0 else 0x2c+i}']
  commands += [f'dump binary memory {O}/instruction-owner-{owner}.bin 0x2000 0x9800']
  commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$p{i}' for i in range(4)]
 gdb(commands)
 check('instruction authored/staged/destination bytes identical',all((O/f'instruction-{label}.bin').read_bytes()==authored for label in ('destination','staged')))
 boundary=(O/'instruction-boundary.bin').read_bytes()
 check('first instruction boundary is published screen1 with no pending frame',boundary[0x91-0x8f]==0 and boundary[0xa6-0x8f]==1)
 import importlib.util
 decoder_path=ROOT/'wiki/internal/tickets/evidence/rsch014-A3/bug100_logo_r_composition_probe.py'
 spec=importlib.util.spec_from_file_location('static_decoder',decoder_path);decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
 manifest=json.loads((B/'ladybug-presentation.json').read_text());cold=(B/'ladybug-presentation-cold.bin').read_bytes()
 check('current cold payload identity',hashlib.sha256(cold).hexdigest()==manifest['cold_payload']['sha256'])
 font=decoder.include_bytes((B/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
 index=next(i for i,item in enumerate(manifest['maps']) if item['name']=='instructions')
 expected=bytes(decoder.decode_static_frame(cold,manifest,font,index))
 check('expected static frame equals manifest',hashlib.sha256(expected).hexdigest()==manifest['shared_static_frame_sha256'][index])
 # Cold hydration already draws the committed TOP score and cucumber before
 # the first actor tick. These are existing hidden-load outputs, not static TMX.
 sys.path.insert(0,str(ROOT/'scripts'));import build_presentation as palette
 chars=palette.load_chars(ROOT/'assets/arcade/chars.json')
 expected=bytearray(expected)
 for col,char in enumerate('090000',33):
  rows=palette.rotate_ccw(chars[int(char)])
  for y in range(8):
   for j in range(4):expected[(48+y)*160+col*4+j]=rows[y][j*2]*16+rows[y][j*2+1]
 import xml.etree.ElementTree as ET
 map_path=ROOT/'tiled'/palette.MAP_FILES['instructions'];map_root=ET.parse(map_path).getroot()
 layer=next(item for item in map_root.findall('layer') if item.get('name')=='Sprite Locations')
 gid=palette.layer_records(layer)[palette.INSTRUCTION_CUCUMBER_MARKER]
 sprite_rows,code=palette.instruction_sprite(map_root,map_path,gid,json.loads((ROOT/'assets/arcade/sprites.json').read_text()))
 check('cucumber authored code equals current generated source',code==manifest['instruction_choreography']['cucumber_source_code'])
 pens=(0,4,5,2);surface=bytes(pens[sprite_rows[y][j*2]]*16+pens[sprite_rows[y][j*2+1]] for y in range(16) for j in range(8))
 palette.blend_native_surface(expected,manifest['instruction_choreography']['cucumber_destination'],surface)
 report['phases'][-1]['expected_hidden_load_overlays']=['boot committed TOP090000 at33..38,row6, red1','authored cucumber at generated instruction destination']
 hashes={}
 for owner in (0,1):
  actual=(O/f'instruction-owner-{owner}.bin').read_bytes()
  check('complete instructions static pixels owner '+str(owner),actual==expected)
  if a.hud_equals:hud_equals_pixels(actual)
  hashes[str(owner)]=hashlib.sha256(actual).hexdigest()
 report['phases'][-1]['owner_frame_sha256']=hashes
 report['qualification']='Natural attract-to-instructions, first static publication before any instruction actor tick. This does not claim choreography, multiplier replay or next-stage acceptance.'

def instruction_multiplier_probe():
 instruction_static_probe()
 sys.path.insert(0,str(ROOT/'scripts'));import build_presentation as palette
 import xml.etree.ElementTree as ET
 manifest=json.loads((B/'ladybug-presentation.json').read_text())
 contract=manifest['instruction_choreography']
 chars=palette.load_chars(ROOT/'assets/arcade/chars.json')
 map_path=ROOT/'tiled'/palette.MAP_FILES['instructions'];map_root=ET.parse(map_path).getroot()
 layer=next(item for item in map_root.findall('layer') if item.get('name')=='CoCo Side HUD')
 cells=palette.layer_records(layer)
 def cell(frame,destination):
  offset=destination-0x2000
  return b''.join(frame[offset+y*160:offset+y*160+4] for y in range(8))
 static_pen=7 if a.instructions_multipliers=='baseline' else 3
 for owner in (0,1):
  frame=(O/f'instruction-owner-{owner}.bin').read_bytes()
  for col in range(1,7):
   expected=palette.instruction_char_tile(map_root,map_path,cells[(col,7)],(col,7),chars,(0,static_pen,static_pen,static_pen))
   check(f'independent template multiplier col{col} owner{owner}',cell(frame,palette.framebuffer_destination((col,7)))==expected)
 for event in (5,8,12):
  phase(f'natural-instruction-row-completion-{event}')
  gdb([f'break *0x{pres["instructions_tick_ready"]:x}',
   f'condition 1 *(unsigned char*)0xca=={event} && *(unsigned char*)0x91==0',
   'continue','delete breakpoints',f'dump binary memory {O}/multiplier-row-boundary.bin 0x8f 0xda'])
  boundary=(O/'multiplier-row-boundary.bin').read_bytes()
  check(f'natural published row-completion {event}',boundary[0x91-0x8f]==0 and boundary[0xa6-0x8f]==1 and boundary[0xca-0x8f]==event)
 digit_pen=6 if a.instructions_multipliers=='baseline' else 3
 for event,value in ((13,2),(14,3),(15,5)):
  phase(f'natural-instruction-X{value}-both-publications')
  # The ready boundary precedes a new instruction tick, after the previous
  # framebuffer publication. Conditions never mutate clocks or actor state.
  for owner in (0,1):
   commands=[f'break *0x{pres["instructions_tick_ready"]:x}',
    f'condition 1 *(unsigned char*)0xca=={event} && *(unsigned char*)0x8f=={owner} && *(unsigned char*)0x91==0',
    'continue','delete breakpoints',f'dump binary memory {O}/multiplier-boundary.bin 0x8f 0xda']
   for i in range(4):
    commands += [f'set $p{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}={0x30+i if owner==0 else 0x2c+i}']
   commands += [f'dump binary memory {O}/multiplier-front.bin 0x2000 0x9800']
   commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$p{i}' for i in range(4)]
   gdb(commands)
   boundary=(O/'multiplier-boundary.bin').read_bytes()
   check(f'published X{value} owner{owner} boundary',boundary[0]==owner and boundary[0x91-0x8f]==0 and boundary[0xa6-0x8f]==1 and boundary[0xca-0x8f]==event)
   frame=(O/'multiplier-front.bin').read_bytes()
   x_tile=palette.instruction_char_tile(map_root,map_path,cells[(1,7)],(1,7),chars,(0,3,3,3))
   rows=palette.rotate_ccw(chars[value])
   digit_tile=palette.pack_tile(palette.recolor(rows,(0,digit_pen,digit_pen,digit_pen)))
   for row,destination in enumerate(contract['multiplier_destinations']):
    check(f'natural X{value} row{row} owner{owner} X blue',cell(frame,destination)==x_tile)
    check(f'natural X{value} row{row} owner{owner} numeral pen{digit_pen}',cell(frame,destination+4)==digit_tile)
   report['phases'][-1].setdefault('published_frame_sha256',{})[str(owner)]=hashlib.sha256(frame).hexdigest()
 report['qualification']='Natural instruction X2/X3/X5 publications on both owners, independent authored-glyph masks and pens. No timer, phase, PC or framebuffer fixture. Ordinary point/scoring/choreography acceptance remains separate.'

def stage_helper_identity():
 helper=(B/'ladybug-highscore-helper.bin').read_bytes()
 gdb(['set $saved5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x23',f'dump binary memory {O}/stage-helper.bin 0xac40 0x{0xac40+len(helper):x}','set {unsigned char}0xffa5=$saved5'])
 check('live stage mapped helper equals current authored artifact',(O/'stage-helper.bin').read_bytes()==helper)

def active_gameplay_identity():
 active=(B/'ladybug-adaptive-active.bin').read_bytes()
 gdb([f'dump binary memory {O}/active.bin 0x38f 0x{0x38f+len(active):x}'])
 check('ordinary gameplay adaptive vectors and copied active image equal current artifact',(O/'active.bin').read_bytes()==active)

def level_part_probe(value,next_stage=False):
 sys.path.insert(0,str(ROOT/'scripts'));import verify_shared_text as shared
 phase('selected-part-natural-level-start-'+str(value));key('5');settled(3)
 report['phases'][-1]['forced_state']='Seed next-game part setting EB directly, including 100..255 outside menu-selectable1..99; real Enter and natural level-start hydration. Menu setting range unchanged.'
 commands=['set {unsigned char}0xeb='+str(value)]
 if a.stage_score:
  commands += [f'set {{unsigned char}}0x{0x1d+i:x}=0x{a.stage_score[2*i:2*i+2]}' for i in range(3)]
  report['phases'][-1]['forced_prior_score']=a.stage_score
 gdb(commands);key('Return')
 if next_stage:
  await_state('ordinary credited entry before stage-clear fixture',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  phase('natural-stage-transition-from-'+str(value));report['phases'][-1]['forced_state']='Set STAGE to requested predecessor and STAGE_PENDING=1 at ordinary credited gameplay; actual presentation normal_stage calls next_stage and hydrates level-start. Preceding maze completion is not claimed.'
  commands=[f'set {{unsigned char}}0x24={value}']
  if a.stage_score:
   commands += [f'set {{unsigned char}}0x{0x1d+i:x}=0x{a.stage_score[2*i:2*i+2]}' for i in range(3)]
   report['phases'][-1]['forced_current_score']=a.stage_score
  commands += ['set {unsigned char}0x26=1'];gdb(commands);value=1 if value==255 else value+1
 await_state('natural level-start publication',lambda q:q['mode']==6 and q['screen']==2 and q['pending']==0)
 stage_helper_identity()
 font=shared.values((B/'ladybug_shared_text.inc').read_text(),'font','colour_lut');translation=shared.values((B/'ladybug_stage_glyphs.inc').read_text(),'stage_source_glyphs','no_end')
 colour=json.loads((B/'ladybug-presentation.json').read_text())['shared_text']['colour_configuration']['fields']['stage_part']
 owner=snapshot()['front'];report['phases'][-1]['published_front_owner']=owner
 report['phases'][-1]['owner_qualification']='Level-start bypasses start_screen_hold and publishes one hydrated BACK as FRONT; previous hidden screen is excluded. Ordinary HUD probe separately verifies both persistent owners.'
 for owner in (owner,):
  frame=front_frame(owner)
  if a.hud_equals:hud_equals_pixels(frame)
  for x,row in ((20,4),(37,11)):
   for col,char in enumerate((' ' if value<100 else str(value//100))+f'{value%100:02d}',x):
    code=36 if char==' ' else int(char);mask=font[translation[code]*8:translation[code]*8+8]
    expected=bytes((colour if mask[y]&(128>>(j*2)) else 0)*16+(colour if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
    actual=b''.join(frame[(row*8+y)*160+col*4:(row*8+y)*160+col*4+4] for y in range(8))
    check('level-start owner '+str(owner)+' row '+str(row)+' cell '+str(col),actual==expected)
 if a.stage_score:
  expected_score=a.stage_score if next_stage else '000000'
  for col,char in enumerate(expected_score,33):
   mask=font[translation[int(char)]*8:translation[int(char)]*8+8]
   expected=bytes((8 if mask[y]&(128>>(j*2)) else 0)*16+(8 if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
   actual=b''.join(frame[(16+y)*160+col*4:(16+y)*160+col*4+4] for y in range(8))
   check('level-start light-green score cell '+str(col),actual==expected)
  report['phases'][-1]['expected_display_score']=expected_score

def trademark_pixels():
 oracle=json.loads((Path(__file__).resolve().parents[1]/'rsch014-ready-100/current-mark-oracle.json').read_text())
 frame=front_frame()
 crop=b''.join(frame[(104+y)*160+120:(104+y)*160+128] for y in range(16))
 expected=bytes.fromhex(oracle['baseline_crop_hex'] if a.trademark=='baseline' else oracle['target_crop_hex'])
 check('complete16x16 trademark equals frozen '+a.trademark+' glyph/palette',crop==expected)
 report['phases'][-1]['trademark_crop_sha256']=hashlib.sha256(crop).hexdigest()
 report['phases'][-1]['trademark_foreground']={'red':sum((v>>4==1)+(v&15==1) for v in crop),'white':sum((v>>4==6)+(v&15==6) for v in crop)}

def name_controls():
 phase('forced-final-death-natural-name-handoff')
 report['phases'][-1]['forced_state']='Replace five bindings with previously UI-tested W/S/A/D/Space; set packed-BCD SCORE=095000 and DEATH_STATE=4 at ordinary credited gameplay. Natural qualification/phase owner installs and publishes game-over then name entry.'
 gdb([f'set {{unsigned char}}0x{0x287+i:x}={v}' for i,v in enumerate((58,26,8,32,59))]+['set {unsigned char}0x1d=9','set {unsigned char}0x1e=0x50','set {unsigned char}0x1f=0','set {unsigned char}0x4d=4'])
 await_state('name publication',lambda q:q['mode']==8 and q['screen']==5 and q['pending']==0)
 low=(B/'ladybug-highscore-runtime.bin').read_bytes();helper=(B/'ladybug-highscore-helper.bin').read_bytes()
 gdb([f'dump binary memory {O}/name-runtime.bin 0x300 0x{0x300+len(low):x}','set $saved5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x23',f'dump binary memory {O}/name-helper.bin 0xac40 0x{0xac40+len(helper):x}','set {unsigned char}0xffa5=$saved5'])
 check('name low-RAM runtime equals artifact',(O/'name-runtime.bin').read_bytes()==low)
 check('name mapped helper equals artifact',(O/'name-helper.bin').read_bytes()==helper)
 moved=False
 for index,keyname in enumerate(('w','s','a','d')):
  phase('remapped-name-movement-'+str(index));before=snapshot()['player_cell'];key(keyname,states=(1,));q=snapshot()
  check('name mapped direction bit '+str(index),q['mapped_down']==1<<index and q['mode']==8)
  moved=moved or q['player_cell']!=before;key(keyname,states=(0,))
 check('at least one remapped key moves the actual name cursor',moved)
 phase('fixed-arrow-name-exclusion');before=snapshot()['player_cell'];key('Up',states=(1,));q=snapshot();check('fixed menu Up is not a rebound name movement',q['mapped_down']==0 and q['player_cell']==before);key('Up',states=(0,))
 phase('forced-END-natural-name-return');report['phases'][-1]['forced_state']='Set existing END completion flag E2=1; natural mapped helper commits and returns. This does not test reaching the END glyph.'
 gdb(['set {unsigned char}0xe2=1']);settled(3);label_pixels('ADD CREDITS')
def entry_edges():
 phase('held-arrow-through-credit-entry');key('Down',states=(1,));key('5');q=settled(3);check('inherited Down has no fresh menu edge',q['selection']==0);key('Down',states=(0,));key('Down');q=settled(3);check('fresh Down works after release',q['selection']==1)
 phase('simultaneous-credit-and-Enter');key('Up');gdb(['set {unsigned char}0xa8=0'])
 for name in ('5','Return'):
  code=xlib.XKeysymToKeycode(d,xlib.XStringToKeysym(name.encode()));assert xtest.XTestFakeKeyEvent(d,code,1,0);held_keys.add(code)
 xlib.XFlush(d);time.sleep(1);q=settled(3);check('fresh coin and Enter cannot start in same scan',q['credits']==1 and q['live']==0)
 key('5',states=(0,));key('Return',states=(0,));q=settled(3);check('release still does not start',q['live']==0)
 key('Return');q=await_state('fresh Enter starts after chord release',lambda q:q['live']==1);check('fresh Enter consumes chord credit',q['credits']==0)
log=(O/'xroar.log').open('wb',buffering=0)
process=subprocess.Popen(['/usr/local/bin/xroar','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(B/'ladybug.rom'),'-cart-autorun','-ao','null','-gdb','-gdb-port','65522'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
 phase('cold-attract-delivery');time.sleep(.7)
 gdb([f'break *0x{pres["attract_tick"]:x}','continue','delete breakpoints',f'dump binary memory {O}/resident.bin 0xc000 0xfe00'])
 check('live resident equals current runtime artifact',(O/'resident.bin').read_bytes()==resident)
 presentation=(B/'ladybug-presentation-runtime.bin').read_bytes()
 gdb([f'dump binary memory {O}/presentation.bin 0x1900 0x{0x1900+len(presentation):x}'])
 check('live presentation marker owner equals current module artifact',(O/'presentation.bin').read_bytes()==presentation)
 prompt_pixels()
 if a.instructions_multipliers:
  instruction_multiplier_probe();report['status']='PASS';raise SystemExit(0)
 if a.instructions_static:
  instruction_static_probe();report['status']='PASS';raise SystemExit(0)
 if a.prompt_only:
  report['status']='PASS'
  raise SystemExit(0)
 inventory=[(w,n,window_pid(w)) for w,n in windows(root) if 'XRoar' in n]
 report['window_inventory']=inventory;report['launched_pid']=process.pid
 ws=[(w,n) for w,n,pid in inventory if pid==process.pid and visible_window(w)];assert len(ws)==1,('launched visible XRoar host window identity absent or ambiguous',inventory,process.pid);window=ws[0][0]
 if a.trademark:
  phase('credit-entry-complete-trademark');key('5');settled(3);stage_helper_identity();trademark_pixels()
  key('Return');await_state('ordinary credited entry before name-return fixture',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1);active_gameplay_identity()
  name_controls();trademark_pixels();report['status']='PASS';raise SystemExit(0)
 if a.entry_edges_only:
  entry_edges();phase('ordinary-entry-active-identity');await_state('ordinary credited entry after fixed menu edge',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1);active_gameplay_identity();report['status']='PASS';raise SystemExit(0)
 if a.level_part:
  level_part_probe(a.level_part);report['status']='PASS';raise SystemExit(0)
 if a.next_part:
  level_part_probe(a.next_part,True);report['status']='PASS';raise SystemExit(0)
 if a.name_only:
  phase('credited-entry-for-name-controls');key('5');settled(3);key('Return');await_state('ordinary entry',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  name_controls();report['status']='PASS';raise SystemExit(0)
 if a.hud_parts or a.hud_lives:
  phase('credited-entry-for-HUD');key('5');settled(3);key('Return');await_state('ordinary entry',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  hud_probe(a.hud_lives);report['status']='PASS';raise SystemExit(0)
 phase('credit-and-fixed-menu');key('5');q=settled(3);check('one credit',q['credits']==1);label_pixels('START GAME')
 for name in ('1','2'):
  key(name);q=settled(3);check('old '+name+' cannot start',q['live']==0 and q['credits']==1)
 key('6');q=settled(3);check('second credit',q['credits']==2);label_pixels('START GAME')
 key('Down');q=settled(3);check('fixed Down selects Options',q['selection']==1)
 key('Return');settled(6)
 if a.bindings:
  phase('five-remapped-gameplay-bindings')
  key('Down');key('Down');key('Return');q=settled(8)
  old=list(q['bindings'])
  for index,name in enumerate(('w','s','a','d','space')):
   phase('remapped-gameplay-binding-'+str(index));key('Return');key(name);q=settled(8)
   check('binding '+str(index)+' captured uniquely',q['binding_state']==0 and q['bindings'][index]!=old[index] and len(set(q['bindings']))==5)
   key(name,states=(1,));q=snapshot();check('mapped signal '+str(index),q['mapped_down']==1<<index);key(name,states=(0,))
   key('Down')
  phase('keybinding-Back-return');key('Return');settled(6)
  phase('fixed-menu-controls-after-remapping')
 for _ in range(3):key('Down')
 key('Return');q=settled(3)
 if a.bindings:
  key('space',states=(1,));q=settled(3);check('ACTION cannot start menu',q['live']==0 and q['credits']==2);key('space',states=(0,))
 phase('credits-destination');key('Down');key('Down');q=settled(3);check('Credits selection',q['selection']==2)
 key('Return');settled(7);key('Return');settled(3)
 phase('zero-credit-and-held-enter');gdb(['set {unsigned char}0xa8=0']);key('Down');key('Up');q=settled(3);label_pixels('ADD CREDITS');key('Return',states=(1,));q=settled(3);check('zero credit cannot start',q['live']==0 and q['credits']==0)
 key('5');q=settled(3);check('held Enter plus coin remains menu',q['live']==0 and q['credits']==1);label_pixels('START GAME')
 key('Return',states=(0,));q=settled(3);check('release does not start',q['live']==0)
 phase('fresh-enter-credited-handoff');key('Return');
 while True:
  assert time.monotonic()<deadline,'fresh Enter handoff deadline'
  q=snapshot()
  if q['live']==1:break
  time.sleep(.05)
 check('fresh Enter consumes one credit',q['credits']==0)
 if a.bindings:
  phase('ACTION-inert-in-ordinary-gameplay')
  while True:
   assert time.monotonic()<deadline,'ordinary entry handoff deadline'
   q=snapshot()
   if q['mode']==0 and q['entry']==0:break
   time.sleep(.05)
  before=q['player_cell'];key('space',states=(1,));q=snapshot();check('ACTION has only reserved bit',q['mapped_down']==16);check('ACTION does not move player',q['player_cell']==before);key('space',states=(0,))
  active_gameplay_identity()
  for index,(name,direction) in enumerate((('w',0),('s',2),('a',3),('d',1))):
   phase('ordinary-remapped-movement-'+str(index));key(name,states=(1,));q=snapshot();check('ordinary movement consumes mapped direction',q['mode']==0 and q['mapped_down']==1<<index and q['player_want']==direction);key(name,states=(0,))
 report['status']='PASS'
finally:
 if report['phases']:report['phases'][-1]['elapsed_seconds']=round(time.monotonic()-phase_started,3)
 for code in held_keys:xtest.XTestFakeKeyEvent(d,code,0,0)
 xlib.XFlush(d)
 process.terminate();process.wait(timeout=3);log.close()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'phases':len(report['phases']),'output':str(a.output)}))
