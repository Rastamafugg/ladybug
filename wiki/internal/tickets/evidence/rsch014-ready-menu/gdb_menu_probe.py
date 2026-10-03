import ctypes as c,subprocess,time,json,os,hashlib,re,sys
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--worktree',type=Path,required=True);p.add_argument('--rom-sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prompt-only',action='store_true');a=p.parse_args()
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
def key(name,states=(1,0)):
 code=xlib.XKeysymToKeycode(d,xlib.XStringToKeysym(name.encode()));assert code
 xlib.XSetInputFocus(d,window,1,0)
 for pressed in states:
  assert xtest.XTestFakeKeyEvent(d,code,pressed,0);xlib.XFlush(d);time.sleep(.2)
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
 dp=(O/'dp.bin').read_bytes();row={'mode':dp[0xa5],'screen':dp[0xa6],'credits':dp[0xa8],'pending':dp[0x91],'transaction':dp[0xd4],'selection':dp[0xe0],'live':dp[0xa7]}
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
def front_frame():
 commands=['set $owner=*(unsigned char*)0x8f']
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
log=(O/'xroar.log').open('wb',buffering=0)
process=subprocess.Popen(['/usr/local/bin/xroar','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(B/'ladybug.rom'),'-cart-autorun','-ao','null','-gdb','-gdb-port','65522'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
 phase('cold-attract-delivery');time.sleep(.7)
 gdb([f'break *0x{pres["attract_tick"]:x}','continue','delete breakpoints',f'dump binary memory {O}/resident.bin 0xc000 0xfe00'])
 check('live resident equals current runtime artifact',(O/'resident.bin').read_bytes()==resident)
 prompt_pixels()
 if a.prompt_only:
  report['status']='PASS'
  raise SystemExit(0)
 inventory=[(w,n,window_pid(w)) for w,n in windows(root) if 'XRoar' in n]
 report['window_inventory']=inventory;report['launched_pid']=process.pid
 ws=[(w,n) for w,n,pid in inventory if pid==process.pid and visible_window(w)];assert len(ws)==1,('launched visible XRoar host window identity absent or ambiguous',inventory,process.pid);window=ws[0][0]
 phase('credit-and-fixed-menu');key('5');q=settled(3);check('one credit',q['credits']==1);label_pixels('START GAME')
 for name in ('1','2'):
  key(name);q=settled(3);check('old '+name+' cannot start',q['live']==0 and q['credits']==1)
 key('6');q=settled(3);check('second credit',q['credits']==2);label_pixels('START GAME')
 key('Down');q=settled(3);check('fixed Down selects Options',q['selection']==1)
 key('Return');settled(6)
 for _ in range(3):key('Down')
 key('Return');q=settled(3)
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
 report['status']='PASS'
finally:
 if report['phases']:report['phases'][-1]['elapsed_seconds']=round(time.monotonic()-phase_started,3)
 process.terminate();process.wait(timeout=3);log.close()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'phases':len(report['phases']),'output':str(a.output)}))
