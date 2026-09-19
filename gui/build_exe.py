"""Build a folder-based (onedir) EXE for the MarkItDown GUI with PyInstaller.

Usage:
    .venv\\Scripts\\python gui\\build_exe.py

Steps:
    1. Rewrite gui/buildinfo.py with the current git commit SHA + version.
    2. Run PyInstaller in onedir mode (produces dist\\markitdown-gui\\).

The resulting folder is a self-contained distribution: just copy the whole
folder and double-click markitdown-gui.exe. It also performs an online
GitHub update check against the commit it was built from.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
SPEC = HERE / "markitdown-gui.spec"
DIST = ROOT / "dist" / "markitdown-gui"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace"
    ).strip()


def write_buildinfo() -> None:
    import os

    sha = os.environ.get("MKG_SHA")
    if not sha:
        try:
            sha = git("rev-parse", "HEAD")
        except Exception:
            sha = "unknown"
    try:
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
    except Exception:
        branch = "feature/qt6-gui"
    version = os.environ.get("MKG_VERSION", "1.0.0")
    content = (
        "# Auto-populated by gui/build_exe.py from the current git commit.\n"
        f'APP_VERSION = "{version}"\n'
        f'BUILD_SHA = "{sha}"\n'
        f'OWNER = "caramel623"\n'
        f'REPO = "markitdown"\n'
        f'BRANCH = "{branch}"\n'
    )
    (HERE / "buildinfo.py").write_text(content, encoding="utf-8")
    print("Wrote gui/buildinfo.py  build_sha =", sha[:7])


def pyinstaller_args() -> list[str]:
    return [
        str(VENV_PY),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "markitdown-gui",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(HERE),
        # Bundle the whole markitdown package (converters do many lazy imports).
        "--collect-submodules",
        "markitdown",
        # Lazy third-party libraries used inside converters (not statically visible).
        *[f"--hidden-import={m}"
          for m in (
              "mammoth", "pptx", "pandas", "openpyxl", "xlrd",
              "pdfminer", "pdfminer.high_level", "pdfplumber",
              "olefile", "lxml", "markdownify", "bs4",
              "magika", "onnxruntime",
              "charset_normalizer", "defusedxml",
          )],
        # magika ships an ONNX model + JSON the analyser needs at runtime.
        "--collect-data",
        "magika",
        # onnxruntime ships native libs (.pyd/.dll) the runtime loads.
        "--collect-binaries",
        "onnxruntime",
        str(HERE / "run_gui.py"),
    ]


def main() -> int:
    if not VENV_PY.exists():
        print(f"Virtualenv python not found at {VENV_PY}; run install.ps1 first.")
        return 1

    write_buildinfo()

    # Clean previous build outputs.
    for p in (DIST, ROOT / "build", SPEC):
        if p.exists():
            if p.is_dir():
                import shutil

                shutil.rmtree(p)
            else:
                p.unlink()

    run(pyinstaller_args())

    print("\nDone. Folder-based build here:")
    print(f"  {DIST}\\")
    print(f"  {DIST}\\markitdown-gui.exe")
    if not (DIST / "markitdown-gui.exe").exists():
        print("WARNING: exe not found after build; check the log above.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
