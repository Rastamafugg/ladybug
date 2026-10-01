import hashlib
from pathlib import Path
raw = Path('/tmp/rsch014-B-attract-video.bin').read_bytes()
w,h,bpp=192,240,4
assert len(raw)%(w*h*bpp)==0
n=len(raw)//(w*h*bpp)
x0,y0,x1,y1=6,100,186,158
states=[]
for fi in range(n):
    base=fi*w*h*bpp
    crop=b''.join(raw[base+(y*w+x0)*bpp:base+(y*w+x1)*bpp] for y in range(y0,y1))
    digest=hashlib.sha256(crop).hexdigest()[:16]
    if states and states[-1][0]==digest: states[-1][2]+=1
    else: states.append([digest,fi,1])
print('frames',n,'roi',x0,y0,x1,y1,'unique',len(set(s[0] for s in states)))
print('runs:')
for d,start,length in states: print(f'{start+300}-{start+300+length-1} len={length} sha256-prefix={d}')
# Pixel-difference coordinates for each visible state transition in the ROI.
for prev,cur in zip(states,states[1:]):
    a=prev[1]; b=cur[1]; assert b==a+prev[2]
    pa=raw[a*w*h*bpp: (a+1)*w*h*bpp]; pb=raw[b*w*h*bpp:(b+1)*w*h*bpp]
    changed=[]
    for y in range(y0,y1):
        for x in range(x0,x1):
            i=(y*w+x)*bpp
            if pa[i:i+3]!=pb[i:i+3]: changed.append((x,y))
    if changed:
      print(f'diff {a+300}->{b+300}: pixels={len(changed)} bbox={min(x for x,y in changed)},{min(y for x,y in changed)}-{max(x for x,y in changed)},{max(y for x,y in changed)}')
