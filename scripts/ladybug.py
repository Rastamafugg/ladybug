#!/usr/bin/env python3
"""Local Ladybug engineering commands; execute production jobs from WSL."""
import sys

sys.dont_write_bytecode = True
from engineering.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
