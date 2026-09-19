"""GitHub online update check + auto self-update for the standalone build.

Flow:
    1. Query the public GitHub API for the newest release that publishes a
       folder-based EXE asset (asset filename embeds the target build SHA).
    2. Compare that SHA against the SHA this EXE was built from (see
       gui/buildinfo.py, rewritten by gui/build_exe.py at build time).
    3. If newer: download the exact asset into a temp dir, extract the full
       app folder, verify its buildinfo SHA and the exe, swap it into place
       with a small background batch (so the running, file-locked process
       stays valid), and relaunch.

Public (unauthenticated) calls are used, so it works even on machines
without a logged-in `gh`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

try:
    from buildinfo import APP_VERSION, BUILD_SHA, OWNER, REPO, BRANCH
except Exception:  # pragma: no cover - dev fallback
    APP_VERSION = "1.0.0"
    BUILD_SHA = "unknown"
    OWNER = "caramel623"
    REPO = "markitdown"
    BRANCH = "feature/qt6-gui"

API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
# Folder that holds the frozen app (== the folder containing this exe).
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
NEW_DIR = BASE_DIR / (APP_DIR.name + ".new")
SHA_RE = re.compile(r"[0-9a-f]{7,40}")
HTTP_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"markitdown-gui/{APP_VERSION}",
}


def _short(s: Optional[str], n: int = 7) -> str:
    return (s or "")[:n]


def _api_get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class UpdateResult:
    def __init__(self) -> None:
        self.ok = False
        self.error: Optional[str] = None
        self.has_update = False
        self.current_sha = BUILD_SHA

        # Latest release that publishes a downloadable EXE asset.
        self.latest_release_tag: Optional[str] = None
        self.latest_release_url: Optional[str] = None
        self.latest_sha: Optional[str] = None
        self.asset_name: Optional[str] = None
        self.asset_url: Optional[str] = None
        self.asset_size: Optional[int] = None  # bytes
        self.tip_sha: Optional[str] = None
        self.tip_date: Optional[str] = None
        self.tip_message: Optional[str] = None

        # After download/update.
        self.download_path: Optional[Path] = None
        self.extract_dir: Optional[Path] = None
        self.update_ready = False
        self.update_message: Optional[str] = None

        self.repo_url = f"https://github.com/{OWNER}/{REPO}"
        self.releases_url = f"{self.repo_url}/releases"

    # ------------------------------------------------------------------ props
    @property
    def can_auto(self) -> bool:
        return self.has_update and bool(self.asset_url)

    def compare_url(self) -> str:
        if BUILD_SHA != "unknown":
            return f"{self.repo_url}/compare/{BUILD_SHA}...{BRANCH}?expand=1"
        return f"{self.repo_url}/commits/{BRANCH}"

    def summary(self) -> str:
        if not self.ok:
            return f"檢查失敗：{self.error}"
        if self.has_update:
            mode = "自動" if self.can_auto else "手動"
            return (
                f"偵測到更新（本機 {_short(self.current_sha)} → 遠端 "
                f"{_short(self.latest_sha) or self.latest_release_tag}），可{mode}更新"
            )
        return f"已是最終版本（build {_short(self.current_sha)}）"


# --------------------------------------------------------------------------- worker
class UpdateWorker(QThread):
    """Fetches the latest release + branch tip and decides if an update exists."""

    finished_result = pyqtSignal(object)

    def run(self) -> None:
        res = UpdateResult()
        # Latest release that has a downloadable EXE asset matching a build sha.
        try:
            releases = _api_get(f"{API_BASE}/releases?per_page=15")[:15]
            for rel in releases:
                tag = rel.get("tag_name")
                for asset in rel.get("assets", []):
                    name = asset.get("name", "")
                    m = SHA_RE.search(name)
                    if not m:
                        continue
                    sha = m.group(0)
                    if self._same_build(sha):
                        continue  # this is (equivalent to) our own build
                    res.latest_sha = sha
                    res.asset_name = name
                    res.asset_url = asset.get("browser_download_url")
                    res.asset_size = asset.get("size")
                    res.latest_release_tag = tag
                    res.latest_release_url = rel.get("html_url")
                    break
                if res.latest_sha:
                    break
        except urllib.error.HTTPError as e:
            if e.code != 404:  # a 404 "no releases" is not fatal
                res.error = _short_error(e)
        except Exception as exc:
            res.error = _short_error(exc)

        # Branch tip -- used to surface "is the branch ahead of my build?".
        try:
            commit = _api_get(f"{API_BASE}/commits/{BRANCH}")
            res.tip_sha = commit.get("sha")
            cm = commit.get("commit", {}) or {}
            res.tip_date = (cm.get("committer") or {}).get("date")
            res.tip_message = (cm.get("message") or "").splitlines()[0]
        except Exception as exc:
            if not res.error:
                res.error = _short_error(exc)

        res.has_update = bool(res.latest_sha) or bool(
            res.tip_sha and not self._same_build(res.tip_sha)
        )
        res.ok = True
        self.finished_result.emit(res)

    def _same_build(self, other: Optional[str]) -> bool:
        if not other:
            return False
        a = (BUILD_SHA or "").lower()
        return a.startswith(other.lower()) or other.lower().startswith(a)


def _short_error(exc: Exception) -> str:
    msg = str(exc) or exc.__class__.__name__
    first = msg.splitlines()[0].strip()
    return first[:200] or exc.__class__.__name__


# --------------------------------------------------------------------------- downloader
class DownloadWorker(QThread):
    finished_result = pyqtSignal(object)  # UpdateResult
    progress_bytes = pyqtSignal(int)  # bytes downloaded so far

    def __init__(self, res: UpdateResult):
        super().__init__()
        self.res = res

    def run(self) -> None:
        dest = Path(self.res.download_path)
        try:
            req = urllib.request.Request(self.res.asset_url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp, open(
                dest, "wb"
            ) as fh:
                total = int(resp.headers.get("Content-Length") or self.res.asset_size or 0)
                got = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    self.progress_bytes.emit(got)
            if self.res.asset_size and dest.stat().st_size < self.res.asset_size:
                raise IOError(
                    f"下載不完整（{dest.stat().st_size}/{self.res.asset_size} bytes）"
                )
            self.res.extract_dir = extract_zip(dest)
            ok, msg, verified_sha = verify_update(self.res.extract_dir, self.res.latest_sha)
            if ok:
                self.res.update_ready = True
                self.res.update_message = (
                    f"已下載並驗證更新（build {_short(verified_sha)}）"
                )
            else:
                self.res.update_message = f"驗證失敗：{msg}"
        except Exception as exc:
            self.res.update_ready = False
            self.res.update_message = _short_error(exc)
        self.finished_result.emit(self.res)


def extract_zip(zip_path: Path) -> Path:
    """Unzip into a temp dir, returning the inner app folder (the one holding
    markitdown-gui.exe), skipping build/ cache dirs and nested archives."""
    work = Path(
        tempfile.mkdtemp(prefix="mkg_update_", dir=str(APP_DIR.parent))
    )
    target = work
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    exe = target / "markitdown-gui.exe"
    if not exe.exists() and target.rglob("markitdown-gui.exe"):
        exe = next(target.rglob("markitdown-gui.exe"))
    inner = exe.parent if exe.exists() else target

    # Strip obvious cruft that shouldn't be shipped inside an update.
    for sub in ("build", "__pycache__", "gui"):
        p = inner / sub
        if p.exists() and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    # Drop the old zip and any spec/toc cruft at the top if present.
    for f in target.glob("*.spec"):
        f.unlink(missing_ok=True)
    return inner


def verify_update(extract_dir: Path, expected_sha: Optional[str]) -> tuple[bool, str, Optional[str]]:
    exe = extract_dir / "markitdown-gui.exe"
    if not exe.exists():
        return False, "未找到 markitdown-gui.exe", None
    bi = extract_dir / "buildinfo.py"
    if not bi.exists():
        candidates = [
            c for c in extract_dir.rglob("buildinfo.py")
            if ".venv" not in c.parts and "__pycache__" not in c.parts
        ]
        # Prefer the shallowest (closest to the app root) buildinfo.py.
        if candidates:
            bi = min(candidates, key=lambda c: len(c.relative_to(extract_dir).parts))
    if bi is None:
        return False, "未找到 buildinfo.py", None
    text = bi.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'BUILD_SHA\s*=\s*["\']([0-9a-f]+)["\']', text)
    if not m:
        return False, "buildinfo.py 無有效 BUILD_SHA", None
    actual = m.group(1).lower()
    if expected_sha and not (
        actual.startswith(expected_sha.lower())
        or expected_sha.lower().startswith(actual)
    ):
        return (
            False,
            f"SHA 不符（預期 {_short(expected_sha)}，實際 {_short(actual)}）",
            actual,
        )
    return True, "ok", actual


# --------------------------------------------------------------------------- applier
def apply_update(res: UpdateResult, relaunch: bool = True) -> str:
    """Swap the downloaded app folder into place via a background batch,
    and (optionally) relaunch. Returns a human-readable status message."""
    new_dir: Path = res.extract_dir
    if not new_dir or not new_dir.exists() or not (new_dir / "markitdown-gui.exe").exists():
        return "尚無已驗證的更新可用"

    if NEW_DIR.exists():
        shutil.rmtree(NEW_DIR, ignore_errors=True)
    # Stage as a sibling of the app dir: BASE_DIR/markitdown-gui.new
    shutil.copytree(new_dir, NEW_DIR, dirs_exist_ok=False)

    app = APP_DIR
    app_old = app.parent / (app.name + ".old")
    relaunch_flag = "1" if relaunch else "0"

    # Batch performs the swap after our process releases its file handles.
    # The bat lives OUTSIDE the app folder so it survives the move.
    lines = [
        "@echo off",
        f'cd /d "{app.parent}"',
        'ping -n 3 127.0.0.1 >nul',  # wait ~2s for the old process to exit
        f'if exist "{app.name}.old" rmdir /s /q "{app.name}.old"',
        f'move "{app.name}" "{app.name}.old" >nul 2>&1',
        f'move "{NEW_DIR.name}" "{app.name}" >nul 2>&1',
        f'rmdir /s /q "{app.name}.old" >nul 2>&1',
        'del "%~f0" >nul 2>&1',  # delete this batch once done
    ]
    if relaunch:
        lines.append(f'start "" "{app.name}\\markitdown-gui.exe"')

    bat = BASE_DIR / f".mkg_update_{int(_now())}.bat"
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    # Launch detached so the swap proceeds after we shutdown.
    DETACHED = 0x00000008
    CREATE_NEW = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    import subprocess

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            creationflags=DETACHED | CREATE_NEW | CREATE_NO_WINDOW,
            cwd=str(app.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return f"排程更新時發生錯誤：{_short_error(exc)}"

    # Clean up our staging files we own.
    shutil.rmtree(new_dir, ignore_errors=True)
    if res.download_path:
        try:
            res.download_path.unlink(missing_ok=True)
        except Exception:
            pass
    _run_gc()
    return f"已排程更新（build {_short(res.latest_sha)}），將於重啟後套用"


def _now() -> float:
    import time

    return time.time()


def _run_gc() -> None:
    import gc

    gc.collect()


# --------------------------------------------------------------------------- dialog
class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("檢查更新")
        self.resize(520, 320)
        self.result: Optional[UpdateResult] = None
        self._dl_worker: Optional[DownloadWorker] = None

        v = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setText(
            f"正在檢查 {OWNER}/{REPO} 分支 {BRANCH} 的更新…\n\n"
            f"本機版本 {APP_VERSION}（build {_short(BUILD_SHA)}）"
        )
        v.addWidget(self.lbl)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        v.addWidget(self.progress)
        v.addStretch(1)

        btn_row = QHBoxLayout()
        self.btn_auto = QPushButton("自動下載並更新…")
        self.btn_auto.setEnabled(False)
        self.btn_repo = QPushButton("開啟專案頁面")
        self.btn_release = QPushButton("檢視 Releases")
        self.btn_release.setEnabled(False)
        self.btn_close = QPushButton("關閉")
        for b in (self.btn_auto, self.btn_repo, self.btn_release, self.btn_close):
            btn_row.addWidget(b, stretch=1)
        v.addLayout(btn_row)

        self.btn_auto.clicked.connect(self._do_auto_update)
        self.btn_repo.clicked.connect(lambda: _open_url((self.result or UpdateResult()).repo_url))
        self.btn_release.clicked.connect(lambda: _open_url((self.result or UpdateResult()).releases_url))
        self.btn_close.clicked.connect(self.accept)

        self._worker = UpdateWorker()
        self._worker.finished_result.connect(self._on_checked)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_checked(self, res: UpdateResult) -> None:
        self.result = res
        if not res.ok:
            self.lbl.setText(f"檢查失敗：{res.error}")
            return
        lines = [res.summary(), ""]
        if res.latest_release_tag:
            lines.append(f"最新發布：{res.latest_release_tag}")
        if res.tip_sha:
            ahead = "（分支領先本機）" if (res.tip_sha and not self._same(res.tip_sha)) else ""
            lines.append(f"分支 {BRANCH} 最新提交：{_short(res.tip_sha)}{ahead}")
            if res.tip_date:
                lines.append(f"  日期：{res.tip_date}")
        if res.can_auto and res.asset_size:
            lines.append(f"可用更新包：{res.asset_name}（{_human(res.asset_size)}）")
        lines.append("")
        lines.append(f"本機版本 {APP_VERSION}（build {_short(res.current_sha)}）")
        self.lbl.setText("\n".join(lines))
        self.btn_auto.setEnabled(res.can_auto)
        self.btn_release.setEnabled(bool(res.latest_release_url))

    @staticmethod
    def _same(sha: str) -> bool:
        a = (BUILD_SHA or "").lower()
        b = (sha or "").lower()
        return a.startswith(b) or b.startswith(a)

    def _do_auto_update(self) -> None:
        res = self.result
        if not res or not res.can_auto:
            return
        tmp = Path(tempfile.mkdtemp(prefix="mkg_dl_", dir=str(APP_DIR.parent)))
        res.download_path = tmp / (res.asset_name or "update.zip")
        self.btn_auto.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.lbl.setText("正在下載更新…")
        self._dl_worker = DownloadWorker(res)
        self._dl_worker.progress_bytes.connect(self._on_progress)
        self._dl_worker.finished_result.connect(self._on_download_done)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_worker.start()

    def _on_progress(self, got: int) -> None:
        res = self.result
        total = res.asset_size or 0
        if total:
            self.progress.setValue(int(got * 100 / total))
            self.lbl.setText(f"正在下載更新… {_human(got)} / {_human(total)}")

    def _on_download_done(self, res: UpdateResult) -> None:
        self.progress.setVisible(False)
        if res.update_ready:
            ans = QMessageBox.question(
                self,
                "更新就緒",
                res.update_message + "\n\n要現在套用更新並重新啟動嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans == QMessageBox.StandardButton.Yes:
                msg = apply_update(res, relaunch=True)
                self.lbl.setText(msg + "（本程式即將關閉）")
                self.accept()
        else:
            self.lbl.setText(res.update_message or "更新失敗")
            QMessageBox.warning(self, "更新", res.update_message or "更新失敗")
            self.btn_auto.setEnabled(res.can_auto)


def _open_url(url: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception as exc:  # pragma: no cover
        print("open url failed:", exc)


def _human(n: Optional[int]) -> str:
    if not n:
        return "?"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
