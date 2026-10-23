"""Makes the Editor automation tool's environment: a virtual environment in
build/venv, beside this file, made from the Python that runs this script,
with the packages requirements.txt pins.

    python tools/editor/bootstrap.py

It refuses when build/venv exists, rather than replacing it: the tool
deletes no folder. To make it again, remove that folder first.
"""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
VENV = HERE / "build" / "venv"


def main() -> int:
    if VENV.exists():
        print("%s exists already; remove it first to make it again" % VENV)
        return 1
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    python = VENV / "Scripts" / "python.exe"
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(HERE / "requirements.txt")], check=True)
    print("Made %s. Run the tool with %s" % (VENV, python))
    return 0


if __name__ == "__main__":
    sys.exit(main())
