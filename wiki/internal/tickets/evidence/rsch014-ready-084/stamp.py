from pathlib import Path
import sys,time
Path(sys.argv[1]).write_text(str(time.monotonic()))
