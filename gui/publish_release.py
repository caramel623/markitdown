r"""Publish a folder-build ZIP as a GitHub release.

The distribution zip is produced by gui/build_exe.py:
    markitdown-gui-Windows-x64-<sha7>.zip   (contains markitdown-gui\)

The asset filename embeds the build SHA so the in-app updater can detect and
download the exact, verified update. This script only publishes it (via the
`gh` CLI/token). Run:
    .venv\\Scripts\\python gui\\publish_release.py            # new release (tag = v<sha7>)
    .venv\\Scripts\\python gui\\publish_release.py --release TAG   # attach/clobber on TAG
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST_DIR = ROOT / "dist" / "markitdown-gui"
EXE = DIST_DIR / "markitdown-gui.exe"


def run(cmd: list[str]) -> str:
    print("$", " ".join(cmd), flush=True)
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace").strip()


def read_sha() -> str:
    override = os.environ.get("MKG_PUBLISH_SHA")
    if override:
        return override
    bi = DIST_DIR / "buildinfo.py"
    if bi.exists():
        m = re.search(r'BUILD_SHA\s*=\s*["\']([0-9a-f]+)', bi.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return run(["git", "rev-parse", "HEAD"])


def get_zip(sha7: str) -> Path:
    """Reuse the distribution zip built by build_exe.py; make one if missing."""
    zip_path = ROOT / f"markitdown-gui-Windows-x64-{sha7}.zip"
    if zip_path.exists():
        return zip_path
    if not EXE.exists():
        raise SystemExit("No build found. Run gui/build_exe.py first (it creates the zip).")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in DIST_DIR.rglob("*"):
            if f.is_file() and not (f.name.endswith(".spec") or f.name.endswith(".toc")):
                zf.write(f, Path("markitdown-gui") / f.relative_to(DIST_DIR))
    print(f"Zipped (zip was missing): {zip_path}")
    return zip_path


def main() -> int:
    tag = None
    if "--release" in sys.argv:
        tag = sys.argv[sys.argv.index("--release") + 1]
    # Optional publish SHA: use when the build was made with a forced SHA so the
    # asset name and buildinfo always agree.
    if "--sha" in sys.argv:
        os.environ["MKG_PUBLISH_SHA"] = sys.argv[sys.argv.index("--sha") + 1]

    sha = read_sha()
    zip_path = get_zip(sha[:7])

    if not EXE.exists():
        print(f"No build found at {EXE}. Run gui/build_exe.py first.", file=sys.stderr)
        return 1

    if tag:
        run(["gh", "release", "upload", tag, str(zip_path), "--clobber"])
    else:
        tag = "v" + sha[:7]
        run([
            "gh", "release", "create", tag,
            "--title", f"MarkItDown GUI {tag}",
            "--notes",
            f"Windows x64 folder-based build.\n\nSHA: {sha}\n\n"
            "Unzip and run markitdown-gui.exe. The app auto-checks for newer builds.",
            str(zip_path),
        ])

    print(f"\nPublished to release {tag}:\n  {zip_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
