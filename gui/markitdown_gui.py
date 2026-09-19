"""MarkItDown Batch Converter - a PyQt6 GUI for convert-to-Markdown.

Built on top of the local `markitdown` package (installed from
`packages/markitdown`). Select files or whole folders, then batch-convert
PDF / Word / Excel / PowerPoint and other common formats to Markdown.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from markitdown import (
        MarkItDown,
        FileConversionException,
        UnsupportedFormatException,
    )
except Exception as exc:  # pragma: no cover - import guard
    print("Failed to import markitdown:", exc)
    raise

# Extensions markitdown can meaningfully convert. Used for folder scanning
# and the file dialog filter.
SUPPORTED_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".docm",
    ".xlsx", ".xlsm", ".xls", ".xlsb",
    ".pptx", ".ppt", ".pptm",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg",
    ".csv", ".tsv", ".txt", ".md", ".rst",
    ".html", ".htm", ".xml", ".json", ".ipynb",
    ".epub", ".msg", ".zip",
}

FILTER_TEXT = "支援的檔案 ({})".format(
    " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
)

STATUS_PENDING = "待處理"
STATUS_CONVERTING = "轉換中"
STATUS_OK = "成功"
STATUS_SKIP = "已略過"
STATUS_ERROR = "失敗"

# Column layout for the file table.
COL_NAME = 0
COL_SIZE = 1
COL_DEST = 2
COL_STATUS = 3


@dataclass
class Job:
    src: Path
    dest: Path
    overwrite: bool
    status: str = STATUS_PENDING
    message: str = ""


class ConvertWorker(QThread):
    """Runs the batch conversion off the GUI thread so the UI stays responsive."""

    progress = pyqtSignal(int, int)  # finished index (0-based), total
    file_done = pyqtSignal(int, str, str)  # row, status, message
    finished_all = pyqtSignal(bool)  # at least one error?

    def __init__(self, jobs: List[Job], parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self._stop = False
        self._md: Optional[MarkItDown] = None

    def request_stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            self._md = MarkItDown()
        except Exception as exc:
            for i in range(len(self.jobs)):
                self.job(self.jobs[i]).status = STATUS_ERROR
                self.file_done.emit(i, STATUS_ERROR, f"無法初始化 MarkItDown: {exc}")
            self.finished_all.emit(True)
            return

        errors = 0
        total = len(self.jobs)
        for i, job in enumerate(self.jobs):
            if self._stop:
                job.status = STATUS_SKIP
                job.message = "已停止"
                self.file_done.emit(i, STATUS_SKIP, "已停止")
                continue
            job.status = STATUS_CONVERTING
            self.file_done.emit(i, STATUS_CONVERTING, "轉換中…")
            ok = self._convert_one(job)
            if job.status == STATUS_OK or job.status == STATUS_SKIP:
                pass
            else:
                errors += 1
            self.progress.emit(i + 1, total)

        self.finished_all.emit(errors > 0)

    def _convert_one(self, job: Job) -> bool:
        try:
            if not job.src.exists():
                job.status = STATUS_ERROR
                job.message = "檔案不存在"
                return False

            if job.dest.exists() and not job.overwrite and job.dest.suffix == ".md":
                job.status = STATUS_SKIP
                job.message = "已存在（未覆蓋）"
                return True

            result = self._md.convert(str(job.src))
            text = result.markdown

            job.dest.parent.mkdir(parents=True, exist_ok=True)
            with open(job.dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

            job.status = STATUS_OK
            job.message = f"{len(text)} 字元"
            return True
        except (FileConversionException, UnsupportedFormatException) as exc:
            job.status = STATUS_ERROR
            job.message = _short_error(exc)
            return False
        except Exception as exc:
            job.status = STATUS_ERROR
            job.message = f"{type(exc).__name__}: {exc}"
            return False


def _short_error(exc: Exception) -> str:
    """Collapse verbose markitdown exceptions to a single-line message."""
    msg = str(exc) or exc.__class__.__name__
    first = msg.splitlines()[0].strip()
    if len(first) > 240:
        first = first[:237] + "…"
    return first or exc.__class__.__name__


def human_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MarkItDown 批次轉檔工具")
        self.resize(1000, 680)

        self.jobs: List[Job] = []
        self.worker: Optional[ConvertWorker] = None
        self.output_dir: Optional[Path] = None

        self._build_ui()
        self._apply_table_headers()
        self._update_check_dialog = None
        self._auto_check_done = False
        self._bg_worker = None
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(400, self._maybe_auto_check)

    def _maybe_auto_check(self) -> None:
        if self._auto_check_done:
            return
        self._auto_check_done = True
        if self.chk_autoupdate.isChecked():
            self._log("啟動時背景檢查更新…")
            self._background_check()

    def _background_check(self) -> None:
        """Run the GitHub check without a dialog; notify only if an update exists."""
        try:
            from updater import UpdateWorker
        except Exception as exc:  # pragma: no cover
            self._log(f"無法載入更新模組：{exc}")
            return
        self._bg_worker = UpdateWorker()
        self._bg_worker.finished_result.connect(self._on_bg_result)
        self._bg_worker.finished.connect(self._bg_worker.deleteLater)
        self._bg_worker.start()

    def _on_bg_result(self, res) -> None:
        if not res.ok:
            self._log(f"背景檢查更新失敗：{res.error}")
            return
        if res.has_update:
            self._log(f"偵測到更新（本機 {res.short_build} → 遠端 {res.short_tip}），開啟更新視窗…")
            self.check_update()
        else:
            self._log(f"已是最終版本（build {res.short_build}）。")

    def check_update(self) -> None:
        """Open the full update-check dialog and show its result."""
        try:
            from updater import UpdateDialog
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "更新", f"無法載入更新模組：{exc}")
            return
        if self._update_check_dialog is not None:
            self._update_check_dialog.close()
        self._update_check_dialog = UpdateDialog(self)
        self._update_check_dialog.show()
        self._log("已開啟檢查更新")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Toolbar row
        toolbar = QHBoxLayout()
        self.btn_add_files = QPushButton("新增檔案…")
        self.btn_add_folder = QPushButton("新增資料夾…")
        self.btn_remove = QPushButton("移除選取")
        self.btn_clear = QPushButton("全清")
        self.btn_open_outdir = QPushButton("開啟輸出資料夾")
        self.btn_check_update = QPushButton("檢查更新")
        for b in (self.btn_add_files, self.btn_add_folder, self.btn_remove,
                  self.btn_clear, self.btn_open_outdir, self.btn_check_update):
            b.setMinimumHeight(28)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self.chk_autoupdate = QCheckBox("啟動時檢查更新")
        self.chk_autoupdate.setChecked(True)
        toolbar.addWidget(self.chk_autoupdate)
        toolbar.addStretch(1)
        toolbar.addStretch(1)
        self.btn_convert = QPushButton("開始轉換")
        self.btn_convert.setMinimumHeight(32)
        self.btn_convert.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 4px 22px; }"
        )
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setMinimumHeight(32)
        self.btn_stop.setEnabled(False)
        toolbar.addWidget(self.btn_convert)
        toolbar.addWidget(self.btn_stop)
        root.addLayout(toolbar)

        # File table
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )
        self.table.setDragDropMode(QTableWidget.DragDropMode.DragOnly)
        self.table.setAcceptDrops(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        root.addWidget(self.table, stretch=1)

        # Output options
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("輸出"))
        self.rb_same = QRadioButton("與來源相同資料夾")
        self.rb_custom = QRadioButton("指定資料夾")
        self.out_path_edit = QComboBox()
        self.out_path_edit.setEditable(True)
        self.out_path_edit.setPlaceholderText("選擇輸出的 Markdown 資料夾")
        self.out_path_edit.setMinimumWidth(360)
        self.btn_choose_out = QPushButton("選取…")
        self.cb_recurse = QCheckBox("遞迴子資料夾")
        self.cb_recurse.setChecked(True)
        self.cb_overwrite = QCheckBox("覆蓋已有 .md")
        self.cb_overwrite.setChecked(False)
        out_row.addWidget(self.rb_same)
        out_row.addWidget(self.rb_custom)
        out_row.addWidget(self.out_path_edit, stretch=1)
        out_row.addWidget(self.btn_choose_out)
        out_row.addWidget(self.cb_recurse)
        out_row.addWidget(self.cb_overwrite)
        out_row.addStretch(1)
        root.addLayout(out_row)

        # Progress row
        prog_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.lbl_status = QLabel("就緒")
        prog_row.addWidget(self.progress, stretch=1)
        prog_row.addWidget(self.lbl_status)
        root.addLayout(prog_row)

        # Log pane
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(self._mono_font())
        root.addWidget(self.log, stretch=1)

        # Signals
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_folder.clicked.connect(self.add_folder)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_open_outdir.clicked.connect(self.opendir_output)
        self.btn_choose_out.clicked.connect(self.choose_output)
        self.btn_convert.clicked.connect(self.start_convert)
        self.btn_stop.clicked.connect(self.stop_convert)
        self.btn_check_update.clicked.connect(self.check_update)
        self.table.itemDoubleClicked.connect(self._on_row_double_click)

    def _mono_font(self):
        from PyQt6.QtGui import QFont

        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(9)
        return f

    def _apply_table_headers(self) -> None:
        self.table.setHorizontalHeaderLabels(
            ["檔案", "大小", "輸出", "狀態"]
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(COL_SIZE, 80)
        self.table.setColumnWidth(COL_DEST, 240)
        self.table.setColumnWidth(COL_STATUS, 200)
        hh.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)

    # ----------------------------------------------------------- Log helper
    def _log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {msg}")

    # -------------------------------------------------------- File handling
    def _file_exists(self, path: Path) -> bool:
        return any(j.src == path for j in self.jobs)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇要轉換的檔案", "", FILTER_TEXT
        )
        for p in paths:
            self.add_file(Path(p))

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "選擇要轉換的資料夾"
        )
        if not folder:
            return
        f = Path(folder)
        if self.cb_recurse.isChecked():
            iterator = f.rglob("*")
        else:
            iterator = f.iterdir()
        added = 0
        for p in sorted(iterator):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                if self.add_file(p):
                    added += 1
        self._log(f"從 {f} 新增 {added} 個檔案")

    def add_file(self, path: Path) -> bool:
        path = path.resolve()
        if not path.is_file():
            return False
        if self._file_exists(path):
            return False
        job = Job(
            src=path,
            dest=self._base_dest(path),
            overwrite=self.cb_overwrite.isChecked(),
        )
        job.dest = self._next_free_dest(job, [j.dest for j in self.jobs])
        self.jobs.append(job)
        self._append_job_row(job)
        self._refresh_status_label()
        return True

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            return
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            try:
                if p.is_dir():
                    f = p
                    if self.cb_recurse.isChecked():
                        iterator = f.rglob("*")
                    else:
                        iterator = f.iterdir()
                    for q in sorted(iterator):
                        if q.is_file() and q.suffix.lower() in SUPPORTED_EXTENSIONS:
                            self.add_file(q)
                elif p.is_file():
                    self.add_file(p)
            except Exception:
                continue
        event.acceptProposedAction()

    def _append_job_row(self, job: Job) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(os.path.basename(job.src))
        name_item.setToolTip(str(job.src))
        size_item = QTableWidgetItem(human_size(job.src.stat().st_size))
        size_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        dest_item = QTableWidgetItem(str(job.dest))
        dest_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        status_item = QTableWidgetItem(job.status)
        status_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.table.setItem(row, COL_NAME, name_item)
        self.table.setItem(row, COL_SIZE, size_item)
        self.table.setItem(row, COL_DEST, dest_item)
        self.table.setItem(row, COL_STATUS, status_item)

    def _base_dest(self, src: Path) -> Path:
        """Where a file would naturally go, before resolving name collisions."""
        if self.rb_custom.isChecked() and self.output_dir:
            # Flatten into the chosen output dir; preserve subfolder structure
            # if the source came from a folder we added (heuristic: keep the
            # original folder name as a sub-path so distinct sources don't clash).
            parent = src.parent.name
            if parent and parent not in ("", os.path.basename(self.output_dir or "")):
                return self.output_dir / parent / (src.stem + ".md")
            return self.output_dir / (src.stem + ".md")
        return src.with_suffix(".md")

    def _next_free_dest(self, job: Job, already_used: List[Path]) -> Path:
        """Return a `.md` path that doesn't collide with `already_used` or an
        existing file (unless overwrite is set)."""
        base = self._base_dest(job.src)
        used: Set[Path] = set(already_used)
        candidate = base
        n = 2
        while candidate in used or (
            candidate.exists() and not job.overwrite and candidate.suffix == ".md"
        ):
            candidate = base.with_name(f"{base.stem}-{n}{base.suffix}")
            n += 1
        used.add(candidate)
        return candidate

    def refresh_all_dests(self) -> None:
        """Assign each job a unique output path (adding -2, -3, ... on clash)."""
        used: List[Path] = []
        for job in self.jobs:
            job.dest = self._next_free_dest(job, used)
            used.append(job.dest)

    # ------------------------------------------------------- Table helpers
    def remove_selected(self) -> None:
        rows: List[int] = []
        model = self.table.selectionModel()
        if model is None:
            return
        for idx in model.selectedRows():
            rows.append(idx.row())
        rows = sorted(set(rows))
        if not rows:
            return
        for r in reversed(rows):
            if r < len(self.jobs):
                self.jobs.pop(r)
                self.table.removeRow(r)
        # Rebuild jobs from the table so list and rows stay in lockstep.
        self._refresh_dest_column()
        self._refresh_status_label()

    def clear_all(self) -> None:
        if self.worker and self.worker.isRunning():
            self._log("先停止進行中的轉換")
            return
        self.jobs.clear()
        self.table.setRowCount(0)
        self._refresh_status_label()

    def _refresh_dest_column(self) -> None:
        # Rebuild jobs from the table (keeps list and rows in lockstep after
        # add/remove), then assign collision-free destinations and refresh cells.
        kept: List[Job] = []
        for r in range(self.table.rowCount()):
            path_text = self.table.item(r, COL_NAME).toolTip()
            src = Path(path_text)
            kept.append(
                Job(
                    src=src,
                    dest=self._base_dest(src),
                    overwrite=self.cb_overwrite.isChecked(),
                    status=self.table.item(r, COL_STATUS).text(),
                    message="",
                )
            )
        self.jobs = kept
        self.refresh_all_dests()
        for r, job in enumerate(self.jobs):
            self.table.item(r, COL_DEST).setText(str(job.dest))

    def _on_row_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if row < len(self.jobs):
            out = self.jobs[row].dest
            if out.exists():
                self._open_path(out)

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "選擇输出資料夾",
            str(self.output_dir) if self.output_dir else "",
        )
        if folder:
            self.output_dir = Path(folder)
            self.out_path_edit.setCurrentText(str(self.output_dir))
            self.rb_custom.setChecked(True)
            self._refresh_dest_column()

    def opendir_output(self) -> None:
        if self.output_dir and self.output_dir.exists():
            self._open_path(self.output_dir)
        else:
            QMessageBox.information(self, "輸出", "尚未設定輸出資料夾")

    # ------------------------------------------------------------ Converting
    def start_convert(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.jobs:
            QMessageBox.information(self, "無檔案", "請先新增要轉換的檔案。")
            return
        if self.rb_custom.isChecked() and not self.output_dir:
            QMessageBox.warning(
                self, "輸出資料夾",
                "請選擇指定的輸出資料夾。",
            )
            return

        self._refresh_dest_column()
        for r, j in enumerate(self.jobs):
            j.status = STATUS_PENDING
            j.message = ""
            self.table.item(r, COL_STATUS).setText(STATUS_PENDING)

        self.btn_convert.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setRange(0, len(self.jobs))
        self.progress.setValue(0)
        self._log(f"開始批次轉換：共 {len(self.jobs)} 個檔案")

        self.worker = ConvertWorker(self.jobs, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished_all.connect(self._on_all_done)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def stop_convert(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self._log("停止要求已送出（等待檔案完成）…")

    def _on_file_done(self, row: int, status: str, msg: str) -> None:
        if row < self.table.rowCount():
            item = self.table.item(row, COL_STATUS)
            if item is None:
                item = QTableWidgetItem(status)
                self.table.setItem(row, COL_STATUS, item)
            else:
                item.setText(status)
            self.table.item(row, COL_NAME).setToolTip(
                f"{self.table.item(row, COL_NAME).toolTip()}\n{status}: {msg}"
            )
        self._log(f"#{row + 1} {status} — {msg}")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.lbl_status.setText(f"{done}/{total}")

    def _on_all_done(self, had_errors: bool) -> None:
        self.btn_convert.setEnabled(True)
        self.btn_stop.setEnabled(False)
        done = sum(1 for j in self.jobs if j.status == STATUS_OK)
        ok = sum(1 for j in self.jobs if j.status == STATUS_SKIP)
        bad = sum(1 for j in self.jobs if j.status == STATUS_ERROR)
        self.lbl_status.setText(
            f"完成：{done} 成功 / {ok} 略過 / {bad} 失敗"
        )
        self._log(
            f"批次結束：{done} 成功，{ok} 略過，{bad} 失敗"
        )
        if done or ok:
            self._offer_open_output()

    def _offer_open_output(self) -> None:
        ans = QMessageBox.question(
            self, "完成", "要開啟輸出資料夾嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.opendir_output()

    # ------------------------------------------------------------- Utilities
    def _refresh_status_label(self) -> None:
        self.lbl_status.setText(f"{len(self.jobs)} 個檔案就緒")

    @staticmethod
    def _open_path(path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            ans = QMessageBox.question(
                self, "正在轉換", "轉換進行中，要停止並關閉嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_stop()
            self.worker.wait(5000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MarkItDown GUI")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
