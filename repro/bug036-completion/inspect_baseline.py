from pathlib import Path
import sys,importlib.util,time,json,re,os
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];out=Path(sys.argv[1])
BUILD=Path(os.environ.get('BUG036_BUILD',str(ROOT/'build')))
spec=importlib.util.spec_from_file_location('oracle',ROOT/'repro/rsch009/native-publication-package/compare_pixels.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
budget=m.Budget(time.monotonic()+20)
payloads=[(BUILD/p).read_bytes() for p in ['ladybug-presentation-cold.bin','ladybug-runtime.rom','ladybug-highscore-runtime.bin','ladybug-player-sparse.bin']]
glyphaddr=int(re.search(r'^Symbol: score_glyphs .* = ([0-9A-F]+)$',(BUILD/'ladybug-highscore-runtime.map').read_text(),re.M)[1],16)
adapted=bytearray(821);adapted[0x324:0x32e]=payloads[2][glyphaddr-0x300:glyphaddr-0x300+10];payloads[2]=bytes(adapted)
expected=m.expected_images(*payloads,budget)
dp=(out/'dp-3.bin').read_bytes()
if dp[0xe9]:
    inc=(BUILD/'ladybug_presentation.inc').read_text();table=int(re.search(r'PRESENTATION_NAME_ENTRY_TIMER_TABLE equ \$([0-9A-F]+)',inc)[1],16)
    background=bytearray(expected['background'])
    for i in range(dp[0xe9]):
        rec=payloads[0][table+4*i:table+4*i+4];dest=int.from_bytes(rec[:2],'big');ptr=int.from_bytes(rec[2:],'big')
        m.draw_tile(background,payloads[0][ptr:ptr+32],dest,budget)
    expected['background']=bytes(background)
palette=[(0,0,0),(0,180,0),(255,255,0),(0,0,255),(220,0,0),(230,230,230),(0,220,220),(230,0,230),(180,70,0),(160,160,160),(0,100,0),(110,110,0),(0,0,110),(110,0,0),(100,180,255),(255,150,180)]
def png(data,name):
    im=Image.new('RGB',(320,192));im.putdata([palette[n] for b in data for n in (b>>4,b&15)]);im.resize((960,576),0).save(out/name)
png(expected['frame'],'expected.png')
report=[]
for owner in (0,1):
    actual=(out/f'frame-{owner}.bin').read_bytes();png(actual,f'frame-{owner}.png')
    report.append(m.compare_bytes(expected['frame'],actual,budget))
    dp=(out/'dp-3.bin').read_bytes();origin=int.from_bytes(dp[0xda+owner*2:0xdc+owner*2],'big')-0x2000
    candidates=[]
    for pose in range(16):
        player=payloads[3];offset=int.from_bytes(player[pose*3+1:pose*3+3],'big')-0xa000
        frame=bytearray(expected['background'])
        for dest,mask,value in m.sprite_operations(player[offset:],origin,budget):frame[dest]=(frame[dest]&mask)|value
        count=sum(a!=b for a,b in zip(frame,actual));candidates.append(count)
    report[-1]['single_sprite_at_owner_pointer_min_mismatches']=min(candidates)
    report[-1]['matching_pose']=[i for i,n in enumerate(candidates) if n==0]
(out/'pixel-comparison.json').write_text(json.dumps(report,indent=2))
print([(r['mismatches'],r['single_sprite_at_owner_pointer_min_mismatches'],r['matching_pose']) for r in report])

