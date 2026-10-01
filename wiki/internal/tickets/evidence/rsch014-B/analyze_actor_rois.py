import hashlib
from pathlib import Path
raw=Path('/tmp/rsch014-B-attract-video.bin').read_bytes(); w,h,bpp=192,240,4; frame_size=w*h*bpp; n=len(raw)//frame_size
for name,(x0,y0,x1,y1) in {'pink':(24,64,40,80),'green':(96,72,112,88),'yellow':(64,16,80,32),'blue':(152,32,168,48)}.items():
 runs=[]
 for fi in range(n):
  base=fi*frame_size
  crop=b''.join(raw[base+(y*w+x0)*bpp:base+(y*w+x1)*bpp] for y in range(y0,y1))
  d=hashlib.sha256(crop).hexdigest()[:12]
  if runs and runs[-1][0]==d:runs[-1][2]+=1
  else:runs.append([d,fi,1])
 print(name,[(s+300,k,d) for d,s,k in runs])
