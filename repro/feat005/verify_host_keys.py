import ctypes as c,subprocess,time,json,os,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];B=ROOT/'build';O=B/'menu-host-probe';O.mkdir(exist_ok=True)
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
def key(name):
 code=xlib.XKeysymToKeycode(d,xlib.XStringToKeysym(name.encode()));assert code
 xlib.XSetInputFocus(d,window,1,0)
 for pressed in [1,0]:
  assert xtest.XTestFakeKeyEvent(d,code,pressed,0);xlib.XFlush(d);time.sleep(.08)
 time.sleep(.05)
started=time.monotonic()
def gdb(lines):
 if time.monotonic()-started>40:raise TimeoutError('40-second host-key observation boundary')
 p=O/'probe.gdb';p.write_text('\n'.join(['set pagination off','set confirm off','set remotetimeout 3','set architecture m6809','target remote 127.0.0.1:65522',*lines,'detach','quit'])+'\n')
 r=subprocess.run(['m6809-gdb','-q','-nx','-batch','-x',str(p)],capture_output=True,text=True,timeout=10);assert r.returncode==0,r.stdout+r.stderr
 return r.stdout+r.stderr
m={k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',(B/'ladybug-presentation-runtime.map').read_text(),re.M)}
log=(O/'xroar.log').open('wb',buffering=0)
p=subprocess.Popen(['/usr/local/bin/xroar','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(B/'ladybug.rom'),'-cart-autorun','-ao','null','-gdb','-gdb-port','65522','-debug-ui','1'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
 time.sleep(.7)
 print('phase=host menu keys marker=options selection change deadline=40s; timeout=host delivery boundary failure',flush=True)
 print(gdb([f'break *0x{m["attract_tick"]:x}','continue','delete breakpoints',f'dump binary memory {O}/resident.bin 0xc000 0xfe00',f'dump binary memory {O}/presentation.bin 0x1900 0x{0x1900+(B/"ladybug-presentation-runtime.bin").stat().st_size:x}']),flush=True)
 assert (O/'resident.bin').read_bytes()==(B/'ladybug-runtime.rom').read_bytes()[:0x3e00]
 assert (O/'presentation.bin').read_bytes()==(B/'ladybug-presentation-runtime.bin').read_bytes()
 ws=[(w,n) for w,n in windows(root) if 'XRoar' in n];assert ws, list(windows(root));window=ws[-1][0];print('window',ws,flush=True)
 snapshots=[]
 def snapshot(label):
  gdb([f'dump binary memory {O}/dp.bin 0 0x100'])
  dp=(O/'dp.bin').read_bytes();state={'key':label,'mode':dp[0xa5],'screen':dp[0xa6],'selection':dp[0xe0],'previous':dp[0xdf],'lives':dp[0xea],'level':dp[0xeb],'hold':dp[0xd4],'pending':dp[0x91]};snapshots.append(state);print(state,flush=True);return state
 def ready(screen):
  until=time.monotonic()+8
  while True:
   st=snapshot('ready '+str(screen))
   if st['screen']==screen and st['mode']==5 and st['hold']==0 and st['pending']==0:return st
   if time.monotonic()>until:raise TimeoutError('natural screen publication '+str(screen))
   time.sleep(.2)
 key('5');ready(3)
 key('Down');st=snapshot('Down during first hydration');assert st['selection']==1
 key('Up');st=snapshot('Up during hydration');assert st['selection']==0
 key('Return');ready(6)
 key('Right');ready(6);assert snapshot('lives increment')['lives']==4
 key('Down');ready(6);assert snapshot('level selection')['selection']==1
 key('Right');ready(6);assert snapshot('level increment')['level']==2
 key('Left');ready(6);assert snapshot('level decrement')['level']==1
 key('Down');ready(6);assert snapshot('BACK selection')['selection']==2
 key('Return');ready(3)
 key('Down');ready(3);key('Return');ready(7)
 key('Return');ready(3)
 (ROOT/'repro/feat005-host-keys-after-20260930.json').write_text(json.dumps({'status':'pass','rom_sha256':hashlib.sha256((B/'ladybug.rom').read_bytes()).hexdigest(),'input':'desktop X11 XTest through installed XRoar1.10 GTK keyboard handler, 80ms key dwell; CoCo inject_key unused','snapshots':snapshots},indent=2)+'\n')
finally:
 p.terminate();p.wait(timeout=3)
