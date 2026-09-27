from pathlib import Path
import ast,re,sys
source=Path(__file__).with_name('bug058-render-crossover-20260927.py')
module=ast.parse(source.read_text());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='logical_rings')
es={n:int(v,16)for n,v in re.findall(r'Symbol: (\w+) .* = ([0-9A-F]+)',Path(sys.argv[1]).read_text())}
ns={'es':es};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns);norm=ns['logical_rings']
plain=bytearray(8192);rotated=bytearray(8192)
for meta,base in [(es['FB_META_A'],es['ENEMY_BG_BASE']),(es['FB_META_B'],es['ENEMY_BG_B'])]:
 for slot in range(4):
  off=base-0xa000+128*slot;phaseoff=meta-0xa000+es['FBM_ENEMY_RINGS']+slot;rp=slot+1;cp=slot+2;rotated[phaseoff]=rp*16+cp
  for row in range(16):
   for col in range(8):
    value=(row*17+col*31+slot*7)&255;plain[off+row*8+col]=value;rotated[off+((row+rp)%16)*8+(col+cp)%8]=value
live=es['ENEMY_BG_RING']-0xa000;ledger=es['FB_META_A']-0xa000+es['FBM_ENEMY_RINGS'];rotated[live:live+4]=rotated[ledger:ledger+4]
assert norm(plain,0)==norm(rotated,0),'equivalent layouts rejected'
for off in [0x10,es['ENEMY_BG_BASE']-0xa000]:
 damaged=bytearray(rotated);damaged[off]^=1;assert norm(plain,0)!=norm(damaged,0),'corruption hidden'
for off in [live,ledger]:
 damaged=bytearray(rotated);damaged[off]^=8
 try:norm(damaged,0)
 except AssertionError:pass
 else:raise AssertionError('invalid or mismatched phase accepted')
print('PASS: equivalent layout, altered background pixel, unrelated byte, live/ledger and reserved-bit guards')
