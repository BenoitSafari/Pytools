"""Module entry point: ``python -m psx_archiver [options]``."""

import sys

from psx_archiver.cli import main

if __name__ == "__main__":
    sys.exit(main())
