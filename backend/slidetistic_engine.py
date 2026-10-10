"""PyInstaller entry point: the packaged app runs this instead of `python -m engine.cli`."""
import sys

from engine.cli import main

if __name__ == "__main__":
    sys.exit(main())
