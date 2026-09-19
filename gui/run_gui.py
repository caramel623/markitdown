"""Convenience launcher: python run_gui.py

Supports an optional self-test for the frozen (PyInstaller) build:
    set MKG_SELFTEST=1  (optional MKG_SELFTEST_SRC=folder)
    Run the exe; it will batch-convert the given folder (or the repo's
    built-in test files), run a GitHub update check, write results to
    MKG_SELFTEST_OUT (or C:\\temp\\mkg_selftest.txt) and exit.
"""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)


def _selftest() -> int:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    from pathlib import Path

    from markitdown_gui import MainWindow
    from updater import UpdateWorker

    out_path = Path(os.environ.get("MKG_SELFTEST_OUT", "C:\\temp\\mkg_selftest.txt"))
    report: list[str] = []
    src_env = os.environ.get("MKG_SELFTEST_SRC")
    if src_env:
        src_dir = Path(src_env)
    else:
        # Fall back to the repo test files (available when run from source tree).
        src_dir = Path(here) / ".." / "packages" / "markitdown" / "tests" / "test_files"
    src_dir = src_dir.resolve()
    out_dir = Path(os.environ.get("MKG_SELFTEST_OUTDIR", "C:\\temp\\mkg_selftest_md"))

    app = QApplication([])
    win = MainWindow()

    files = sorted(
        p for p in src_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".xlsx", ".pptx"}
    )
    for f in files[:4]:
        win.add_file(f)
    report.append(f"src_dir={src_dir} files={[p.name for p in files[:4]]}")

    win.cb_overwrite.setChecked(True)
    out_dir.mkdir(parents=True, exist_ok=True)
    win.rb_custom.setChecked(True)
    win.output_dir = out_dir
    win._offer_open_output = lambda: None

    loop = QEventLoop()
    win.start_convert()
    QTimer.singleShot(120000, loop.quit)
    loop.exec()

    for j in win.jobs:
        report.append(f"{j.status} {j.dest.name} exists={j.dest.exists()} {j.message}")

    # Run the update check (network).
    uloop = QEventLoop()
    w = UpdateWorker()
    w.finished_result.connect(
        lambda r: (
            report.append(
                f"update ok={r.ok} has_update={r.has_update} "
                f"tip={(r.tip_sha or '')[:7]} tag={r.latest_release_tag} err={r.error}"
            ),
            uloop.quit(),
        )
    )
    QTimer.singleShot(25000, uloop.quit)
    w.start()
    uloop.exec()

    report.append("SELFTEST_OK")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(report), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        print("selftest write failed:", exc)
    print("\n".join(report))
    return 0


def main() -> int:
    if os.environ.get("MKG_SELFTEST"):
        return _selftest()
    from markitdown_gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
