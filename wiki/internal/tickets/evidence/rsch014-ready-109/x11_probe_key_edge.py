"""One X11 host-key edge for an already identified runtime-probe window."""
import ctypes as c,sys
window=int(sys.argv[1]);name=sys.argv[2];pressed=int(sys.argv[3]);assert pressed in (0,1)
x=c.CDLL('libX11.so.6');x.XOpenDisplay.restype=c.c_void_p;x.XOpenDisplay.argtypes=[c.c_char_p]
x.XStringToKeysym.argtypes=[c.c_char_p];x.XStringToKeysym.restype=c.c_ulong
x.XKeysymToKeycode.argtypes=[c.c_void_p,c.c_ulong];x.XKeysymToKeycode.restype=c.c_uint
x.XSetInputFocus.argtypes=[c.c_void_p,c.c_ulong,c.c_int,c.c_ulong];x.XFlush.argtypes=[c.c_void_p]
t=c.CDLL('libXtst.so.6');t.XTestFakeKeyEvent.argtypes=[c.c_void_p,c.c_uint,c.c_int,c.c_ulong]
d=x.XOpenDisplay(None);assert d
x.XSetInputFocus(d,window,1,0);key=x.XKeysymToKeycode(d,x.XStringToKeysym(name.encode()));assert key
assert t.XTestFakeKeyEvent(d,key,pressed,0);x.XFlush(d)
