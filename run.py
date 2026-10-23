"""Runs the nxwright command from a checkout, with the packages pyproject.toml
lists installed:

  python run.py <subcommand> ...

Python puts this script's own folder first on its import path, which is the
folder holding the nxwright package, so the import below finds it.
"""
import sys

from nxwright.cli import main

# Only as the main program: a pool's processes import this module too.
if __name__ == "__main__":
    sys.exit(main())
