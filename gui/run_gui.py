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


def _selftest_update() -> int:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    from pathlib import Path
    import zipfile

    from updater import (
        UpdateWorker,
        DownloadWorker,
        verify_update,
        extract_zip,
        APP_DIR,
    )

    report: list[str] = []
    app = QApplication([])
    out_path = Path(os.environ.get("MKG_SELFTEST_OUT", "C:\\temp\\mkg_update.txt"))

    # 1. Check for updates.
    loop = QEventLoop()
    res_holder: list = []
    w = UpdateWorker()
    w.finished_result.connect(
        lambda r: (
            res_holder.append(r),
            report.append(
                f"update ok={r.ok} has_update={r.has_update} "
                f"current={r.current_sha[:7]} latest={(r.latest_sha or '')[:7]} "
                f"tag={r.latest_release_tag} asset={r.asset_name} "
                f"size={r.asset_size} err={r.error}"
            ),
            loop.quit(),
        )
    )
    QTimer.singleShot(30000, loop.quit)
    w.start()
    loop.exec()
    if not res_holder:
        report.append("update check: no result (timeout)")
        report.append("SELFTEST_UPDATE_FAIL")
        _write(out_path, report)
        return 1
    res = res_holder[0]
    if not (res.ok and res.can_auto):
        report.append(f"update not downloadable (can_auto={res.can_auto})")
        report.append("SELFTEST_UPDATE_OK_NOUPDATE" if res.ok else "SELFTEST_UPDATE_FAIL")
        _write(out_path, report)
        return 0

    # 2. Download the exact asset.
    import tempfile

    dl = Path(os.environ.get("MKG_DOWNLOAD_DIR", tempfile.mkdtemp(prefix="mkg_dl_")))
    dl.mkdir(parents=True, exist_ok=True)
    res.download_path = dl / (res.asset_name or "update.zip")
    dloop = QEventLoop()
    dw = DownloadWorker(res)
    dw.finished_result.connect(
        lambda r: (
            report.append(
                f"download ready={r.update_ready} msg={r.update_message}"
            ),
            dloop.quit(),
        )
    )
    QTimer.singleShot(300000, dloop.quit)
    dw.start()
    dloop.exec()

    # 3. Verify the extracted update matches the expected sha.
    if res.extract_dir:
        ok, msg, sha = verify_update(res.extract_dir, res.latest_sha)
        report.append(f"verify ok={ok} msg={msg} sha={(sha or '')[:7]}")
        # Show a couple of extracted entries to prove real content.
        entries = list(res.extract_dir.rglob("markitdown-gui.exe"))
        report.append(f"exe_count_in_update={len(entries)}")

    # 4. Report: was it actually newer than our build?
    report.append(f"would_auto_update={res.has_update and ok}")
    report.append("SELFTEST_UPDATE_OK" if res.update_ready and ok else "SELFTEST_UPDATE_FAIL")
    _write(out_path, report)
    return int(not (res.update_ready and ok))


def _write(path: Path, lines: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        print("write failed:", exc)
    print("\n".join(lines))


def main() -> int:
    if os.environ.get("MKG_SELFTEST_UPDATE"):
        return _selftest_update()
    if os.environ.get("MKG_SELFTEST"):
        return _selftest()
    from markitdown_gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
