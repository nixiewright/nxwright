"""Runs the nxwright command as `python -m nxwright`."""
import sys

from nxwright.cli import main

# Only when run, not when imported.
if __name__ == "__main__":
    sys.exit(main())
