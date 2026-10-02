import hashlib,json,subprocess
from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
w=root/'worktrees/bug111-transition-guard'; b=w/'build'
source=(b/'ladybug-adaptive-banked.s').read_text()
def once(old,new):
    global source
    assert source.count(old)==1,old
    source=source.replace(old,new)
once('        lda #4\n        sta AD_BATCH','        lda #2\n        sta AD_BATCH')
once('        tst AD_BARRIER\n        bne ab_ready\n        lda PRES_MODE','        tst AD_BARRIER\n        bne ab_rebase\n        lda PRES_MODE')
once('        dec AD_BATCH\n        bne ab_step\nab_ready','        dec AD_BATCH\n        bne ab_step\nab_rebase\n        clr AD_DEBT\n        clr AD_DEBT+1\nab_ready')
once('ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_ready','ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_rebase')
out=root/'repro/bug058-catchup-banked-fit.bin';asm=out.with_suffix('.s');asm.write_text(source)
subprocess.run(['lwasm','-9','--format=raw','-DADAPTIVE_RENDERING=1','-I',str(b),'-I',str(w/'src'),'--output='+str(out),'--map='+str(out.with_suffix('.map')),str(asm)],check=True)
old=(b/'ladybug-adaptive-banked.bin').read_bytes();new=out.read_bytes()
assert len(new)<=698
assert old[:3]==new[:3] and old[6:9]==new[6:9] and old[12:15]==new[12:15],'fixed API jump targets changed'
result={'baseline_bytes':len(old),'candidate_bytes':len(new),'limit':698,'sha256':hashlib.sha256(new).hexdigest(),'fixed_vector_entries':['BD44 reset','BD47 batch branch','BD4A append','BD4D reducer branch','BD50 complete'],'change':'cap2 and clear leftover debt on batch exhaustion/transient/phase barriers','scope':'isolated generated-helper source only, no production or built ROM changes','baseline_rom_sha256':hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest()}
(root/'repro/bug058-current-cap-fit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
