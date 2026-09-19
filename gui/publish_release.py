"""Package the folder build into a ZIP and publish it as a GitHub release.

Asset filename embeds the build SHA so the in-app updater can detect and
download the exact, verified update:
    markitdown-gui-Windows-x64-<sha7>.zip

Uses the `gh` CLI (token) for the authenticated upload. Run:
    .venv\\Scripts\\python gui\\publish_release.py            # new release (tag = sha7)
    .venv\\Scripts\\python gui\\publish_release.py --release TAG   # attach to TAG
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
EXE_NAME = "markitdown-gui.exe"


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


def build_zip() -> Path:
    sha7 = read_sha()[:7]
    zip_path = ROOT / f"markitdown-gui-Windows-x64-{sha7}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in DIST_DIR.rglob("*"):
            if f.is_file():
                # Skip our own zip / build cruft that shouldn't ship.
                if f.name.endswith(".spec") or f.name.endswith(".toc"):
                    continue
                zf.write(f, Path("markitdown-gui") / f.relative_to(DIST_DIR))
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"Zipped: {zip_path}  ({size_mb:.1f} MB)")
    return zip_path


def main() -> int:
    if not EXE.exists():
        print(f"No build found at {EXE}. Run gui/build_exe.py first.", file=sys.stderr)
        return 1

    tag = None
    if "--release" in sys.argv:
        tag = sys.argv[sys.argv.index("--release") + 1]
    # Optional publish SHA: use when the build was made with a forced SHA
    # (MKG_PUBLISH_SHA) so the asset name and buildinfo always agree.
    if "--sha" in sys.argv:
        os.environ["MKG_PUBLISH_SHA"] = sys.argv[sys.argv.index("--sha") + 1]

    zip_path = build_zip()

    if tag:
        # Attach/replace the asset on an existing release.
        run(["gh", "release", "upload", tag, str(zip_path), "--clobber"])
    else:
        tag = "v" + read_sha()[:7]
        run([
            "gh", "release", "create", tag,
            "--title", f"MarkItDown GUI {tag}",
            "--notes",
            f"Windows x64 folder-based build.\n\nSHA: {read_sha()}\n\n"
            "Unzip and run markitdown-gui.exe. The app auto-checks for newer builds.",
            str(zip_path),
        ])

    print(f"\nPublished to release {tag}:\n  {zip_path.name}")
    print("Now build an older build (MKG_SHA=<old>) and run the updater selftest "
          "to confirm it auto-downloads this release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
