"""Build a folder-based (onedir) EXE for the MarkItDown GUI with PyInstaller.

Usage:
    .venv\\Scripts\\python gui\\build_exe.py
    .venv\\Scripts\\python gui\\build_exe.py --no-zip   # skip the distribution zip

Steps:
    1. Rewrite gui/buildinfo.py with the current git commit SHA + version.
    2. Run PyInstaller in onedir mode (produces dist\\markitdown-gui\\).
    3. Ship a top-level buildinfo.py into the app folder (for the updater).
    4. Zip the whole app folder into a distribution zip:
           markitdown-gui-Windows-x64-<sha7>.zip   (contains markitdown-gui\\)

The resulting folder is a self-contained distribution: just copy the whole
folder and double-click markitdown-gui.exe. It also performs an online
GitHub update check against the commit it was built from.
"""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
SPEC = HERE / "markitdown-gui.spec"
APP_NAME = "markitdown-gui"
DIST = ROOT / "dist" / APP_NAME
ICON = HERE / "app.ico"


def dist_zip_path(sha7: str) -> Path:
    return ROOT / f"{APP_NAME}-Windows-x64-{sha7}.zip"


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
    args = [
        str(VENV_PY),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
    ]
    if ICON.exists():
        # --icon sets the .exe file icon; --add-data bundles the .ico so the
        # running window can also use it as its window/taskbar icon.
        # PyInstaller splits the value on os.pathsep (';' on Windows).
        args += ["--icon", str(ICON), "--add-data", f"{ICON}{os.pathsep}."]
    args += [
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
    return args


def make_zip(sha7: str) -> Path:
    """Zip the whole app folder into a distribution zip at the repo root."""
    zip_path = dist_zip_path(sha7)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in DIST.rglob("*"):
            if f.is_file():
                zf.write(f, Path(APP_NAME) / f.relative_to(DIST))
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"Zipped: {zip_path}  ({size_mb:.1f} MB)")
    return zip_path


def main() -> int:
    import shutil

    no_zip = "--no-zip" in sys.argv
    if not VENV_PY.exists():
        print(f"Virtualenv python not found at {VENV_PY}; run install.ps1 first.")
        return 1

    sha_full = os.environ.get("MKG_SHA")
    if not sha_full:
        try:
            sha_full = git("rev-parse", "HEAD")
        except Exception:
            sha_full = "unknown"
    sha7 = sha_full[:7]

    write_buildinfo()

    # Clean previous build outputs and any stale distribution zip.
    for p in (DIST, ROOT / "build", SPEC, dist_zip_path(sha7)):
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

    run(pyinstaller_args())

    # Ship a top-level buildinfo.py so the auto-updater can read the build
    # SHA straight from the app folder (inside the release zip).
    shutil.copyfile(HERE / "buildinfo.py", DIST / "buildinfo.py")
    print("Copied buildinfo.py into", DIST)

    if not (DIST / "markitdown-gui.exe").exists():
        print("WARNING: exe not found after build; check the log above.", file=sys.stderr)
        return 2

    print("\nDone. Folder-based build here:")
    print(f"  {DIST}\\")
    print(f"  {DIST}\\markitdown-gui.exe")

    if not no_zip:
        zip_path = make_zip(sha7)
        print("Distribution zip ready:")
        print(f"  {zip_path}\\")
        print("  -> publish with: .venv\\Scripts\\python gui\\publish_release.py")
    else:
        print("Skipped zip creation (--no-zip).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
