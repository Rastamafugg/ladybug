"""Pure local-file pixel oracle."""
import hashlib
FRAME_BYTES=30720; MAX_SAMPLES=64; STATIC_SHA='d994c4575891f72441836057a7a737f1b72fcc5b3d385ed878527dc60ab47b17'
class Budget:
 def __init__(self,limit=256): self.n=0; self.limit=limit
 def tick(self,n=1): self.n+=n; self.n>self.limit and (_ for _ in ()).throw(TimeoutError('checkpoint budget'))
def sha256_bytes(x): return hashlib.sha256(x).hexdigest()
def compare_bytes(a,b,budget=None):
 if len(a)!=len(b): return {'passed':False,'reason':'length-mismatch'}
 q=budget or Budget(max(256,len(a))); m=[]
 for i,(x,y) in enumerate(zip(a,b)):
  q.tick()
  if x!=y and len(m)<MAX_SAMPLES:m.append({'offset':i,'expected':x,'actual':y})
 return {'passed':a==b,'mismatches':sum(x!=y for x,y in zip(a,b)),'samples':m,'sha256':sha256_bytes(b)}
def compose_static(cold,runtime,budget=None):
 b=budget or Budget(1000000); out=bytearray(FRAME_BYTES); s=cold[0x1e26:0x21d5]; i=cell=0
 while cell<960:
  b.tick(); count=s[i];i+=1
  if not count: raise ValueError('zero RLE count')
  if i+1>len(s): raise ValueError('truncated RLE')
  value,colour=s[i],s[i+1];i+=2
  for _ in range(count):
   if cell>=960: raise ValueError('RLE overrun')
   row,col=divmod(cell,40); dst=row*1280+col*4;cell+=1
   if value<174:g=cold[value*32:value*32+32]
   else:
    glyph=value-174
    if glyph>=41 or not colour: raise ValueError('invalid descriptor')
    off=0xf5c8-0xc000+glyph*8;g=runtime[off:off+8]
   if len(g)<8:raise ValueError('graphic truncation')
   for r in range(8): out[dst+r*160:dst+r*160+min(4,len(g[r*4:r*4+4]))]=g[r*4:r*4+4]
 if i!=len(s):raise ValueError('RLE trailing data')
 return bytes(out)
def decode_sprite(stream,origin,limit=FRAME_BYTES):
 p=0;d=origin;out=[]
 while p<len(stream):
  z=stream[p];p+=1
  if z==255:
   if p+2>len(stream):raise ValueError('truncated escape')
   z=int.from_bytes(stream[p:p+2],'big');p+=2
   if z==0:return out
   d+=z
   if p>=len(stream):raise ValueError('missing stage delta')
   p+=1
  else:d+=z
  if p>=len(stream):raise ValueError('missing run')
  c=stream[p];p+=1; masked=bool(c&128);run=c&127
  if not run or d<0 or d+run>limit:raise ValueError('sprite bounds')
  width=run*(2 if masked else 1)
  if p+width>len(stream):raise ValueError('run truncation')
  for n in range(run):
   if masked: mask,value=stream[p+2*n:p+2*n+2];out.append((d+n,value,mask))
   else:out.append((d+n,stream[p+n],None))
  p+=width
 raise ValueError('unterminated sprite')
def apply_sprite(bg,stream,origin):
 x=bytearray(bg)
 for p,v,m in decode_sprite(stream,origin,len(x)):x[p]=v if m is None else (x[p]&m)|v
 return bytes(x)
def compare_publications(frame,frames,save,saves):
 if len(frames)!=2 or len(saves)!=4:raise ValueError('capture cardinality')
 f=[compare_bytes(frame,x) for x in frames];s=[compare_bytes(save,x) for x in saves]
 return {'frames':f,'saves':s,'passed':all(x['passed'] for x in f+s)}
