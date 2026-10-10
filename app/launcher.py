"""Quiet shortcut entrypoint with the same local runtime path as ORSI.cmd."""
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    libraries = str(root / "runtime/python/Lib/site-packages/nvidia/cu13/bin/x86_64")
    os.environ["PATH"] = libraries + os.pathsep + os.environ.get("PATH", "")
    from app.main import main as desktop_main
    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
