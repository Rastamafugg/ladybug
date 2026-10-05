from pathlib import Path
import sys
p=Path(sys.argv[1]); m=(p/'swap-meta.bin').read_bytes();assert len(m)==512
(p/'swap-meta-reversed.bin').write_bytes(m[256:]+m[:256])
