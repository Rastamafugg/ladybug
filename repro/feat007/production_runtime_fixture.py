"""Snapshot normal build outputs for existing read-only GMC verification."""
from pathlib import Path
import hashlib,json,re,shutil

def prepare(root):
    source=root/'build';out=Path(__file__).parent/'production';out.mkdir(exist_ok=True)
    mapping={'main.map':'ladybug.map','presentation.map':'ladybug-presentation-runtime.map','enemy.map':'ladybug-enemy-runtime.map','highscore.map':'ladybug-highscore-runtime.map','cold.bin':'ladybug-presentation-cold.bin','presentation.bin':'ladybug-presentation-runtime.bin','enemy.bin':'ladybug-enemy-runtime.rom','instruction.bin':'ladybug-instruction-runtime.bin','demo.bin':'ladybug-demo-runtime.bin','highscore.bin':'ladybug-highscore-runtime.bin','highscore-helper.bin':'ladybug-highscore-helper.bin','hold.bin':'ladybug-perimeter-reset-helper.bin','ladybug-checkpoint.rom':'ladybug.rom'}
    for name,original in mapping.items():shutil.copyfile(source/original,out/name)
    text=(source/'ladybug.map').read_text();end=int(re.search(r'^Symbol: asset_end .* = ([0-9A-Fa-f]+)$',text,re.M)[1],16)
    (out/'main.bin').write_bytes((source/'ladybug-runtime.rom').read_bytes()[:end-0xC000])
    checkpoint=out.parent/'dynamic'
    startup=(checkpoint/'probe-startup.bin').read_bytes()
    probe=bytearray((source/'ladybug-runtime.rom').read_bytes());probe[:len(startup)]=startup
    (out/'publication.rom').write_bytes(probe)
    shutil.copyfile(checkpoint/'probe-startup.map',out/'probe-startup.map')
    for path in checkpoint.glob('*.pixels'):shutil.copyfile(path,out/path.name)
    # The independent glyph fixtures remain valid only while their bytes match
    # the compiler's current font and gameplay descriptors.
    raw=(source/'ladybug_shared_text.inc').read_text()
    labels=('font','colour_lut','hud_glyph_cells','gameplay_descriptors','dynamic_descriptors')
    blob=bytearray()
    for a,z in zip(labels,labels[1:]):
        section=raw.split('\n'+a+'\n')[1].split('\n'+z+'\n')[0]
        blob.extend(int(v) for line in section.splitlines() if 'fcb' in line for v in line.split('fcb')[1].strip().split(','))
    assert bytes(blob)==(out.parent/'fit/asset-text-data.bin').read_bytes(),'independent font fixture drift'
    section=raw.split('\ndynamic_descriptors\n')[1]
    descriptors=bytes(int(v) for line in section.splitlines() if 'fcb' in line for v in line.split('fcb')[1].strip().split(','))
    (out/'descriptors.bin').write_bytes(descriptors)
    metadata=json.loads((source/'ladybug-presentation.json').read_text())
    (out/'graphics.bin').write_bytes((out/'cold.bin').read_bytes()[:metadata['shared_text']['graphics']*32])
    manifest={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in [*mapping,'main.bin']}
    (out/'source-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return out
