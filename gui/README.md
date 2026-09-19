# MarkItDown 批次轉檔 GUI（PyQt6）

建立在 [`markitdown`](https://github.com/microsoft/markitdown) 之上的圖形介面工具，
可**批次**把 PDF / Word / Excel / PowerPoint 等常見文件格式轉換成 **Markdown（.md）**。

> 這個 fork（`caramel623/markitdown`）是以 `feature/qt6-gui` 作為預設分支獨立開發，
> **不會**向主線提交 PR，也不影響上游 `main` 分支。

---

## 支援的格式

- **文件**：PDF（`.pdf`）、Word（`.docx`）、PowerPoint（`.pptx`）
- **試算表**：Excel（`.xlsx`、`.xls`）
- **圖片**：`.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tif` `.tiff` `.webp` `.svg`
- **其他**：`.csv` `.tsv` `.txt` `.md` `.rst` `.html` `.htm` `.xml` `.json` `.ipynb` `.epub` `.msg` `.zip`

> 注意：舊版二進位的 `.doc` / `.ppt` / `.xlsb` 不在本機轉換器支援範圍內，請先另存為 `.docx` / `.pptx`。

---

## 一、使用者：直接執行現成 EXE（資料夾版）

### 取得方式
從本 repo 的 **Releases** 下載 `markitdown-gui-Windows-x64-<sha>.zip`，
解壓後得到一個資料夾：

```
markitdown-gui\
├─ markitdown-gui.exe      ← 雙擊執行
└─ _internal\              ← 所有依賴（Qt、markitdown、ONNX 模型等），請保留
```

**請把整個資料夾一起複製／搬移**，不要只拖曳那個 `.exe`。

### 使用流程
1. 打開 `markitdown-gui.exe`。
2. **新增檔案…** 或 **新增資料夾…**（或直接拖曳檔案／資料夾到檔案表），勾選 `遞迴子資料夾` 可一併抓取子目錄。
3. 設定輸出：
   - `與來源相同資料夾`：每個 `.md` 放在原檔案旁邊。
   - `指定資料夾`：選擇一個固定的輸出目錄（可勾 `遞迴子資料夾` 保留結構）。
   - `覆蓋已有 .md`：預設跳過已存在的輸出；勾選則覆蓋。
4. 按下 **開始轉換**。進度條、狀態表（成功／略過／失敗）與日誌視窗會即時更新；可用 **停止** 中止。
5. 完成後可點 **開啟輸出資料夾**；雙擊表格列可直接開啟該檔的 `.md`。
   - 若多個檔案檔名相同（例如都有 `test.pdf`、`test.docx`），輸出會自動加 `-2`、`-3`… 避免互相覆蓋。

### 檢查更新（自動更新）
- 點工具列的 **檢查更新**，會連上 GitHub 比對**當前版本 vs 最新 release**：
  - 若已是最新：顯示「已是最終版本」。
  - 若有新版：按下 **自動下載並更新…** → 下載對應版本 → 驗證 SHA → 套用更新並重新啟動。
- 預設 **啟動時背景檢查更新**（可勾選停用）；偵測到新版會彈出更新視窗，不會自動下載。
- 更新是**就地替換整個資料夾**：下載→解壓→驗證→背景批次換版→重啟，不需安裝程式。

> **更新機制對 fork 的意義**：更新器固定檢查**這個 fork 的 default branch（`feature/qt6-gui`）**
> 最新 release，所以下載的更新永遠來自本 repo，**與上游 `main` 完全無關**。

---

## 二、開發者：從來源建置

> 需要 Python 3.10+（建議 3.14）。以下以 Windows PowerShell 為準。

### 1. 一鍵環境設定
```powershell
install.ps1
```
會建立 `.venv`、以「一般安裝（非 editable）」安裝本專案的 `markitdown` + 轉換器 extras + `PyQt6`。
> **為什麼不能用 editable？** PyInstaller 封裝時需要真實安裝在 `site-packages` 的模組，
> 因此本專案刻意改為一般安裝。

### 2. 啟動 GUI（從來源）
```powershell
run_gui.bat
# 或
.venv\Scripts\python gui\run_gui.py
```

### 3. 打包成「資料夾版」EXE
```powershell
.venv\Scripts\python gui\build_exe.py
```
- 以目前 git commit 的 SHA 寫入 `gui/buildinfo.py`（更新器靠它比對版本）。
- 輸出到 `dist\markitdown-gui\`（`markitdown-gui.exe` + `_internal\`，約 230MB）。
- 可用環境變數覆寫 build SHA／版本（建置與發布版本不同時有用）：
  ```powershell
  $env:MKG_SHA="ca03e2e"; $env:MKG_VERSION="1.0.0"
  .venv\Scripts\python gui\build_exe.py
  ```

### 4. 發布成 Release（讓使用者的 EXE 能自動下載更新）
```powershell
.venv\Scripts\python gui\publish_release.py
```
- 把 `dist\markitdown-gui\` 壓成 `markitdown-gui-Windows-x64-<sha7>.zip`。
- 透過 `gh` 上傳成 GitHub release（asset 檔名內嵌 build SHA）。

**發布新版 = 改程式 → `build_exe.py` → `publish_release.py`**，
使用者手上的舊 EXE 之後就會**自動偵測並下載**這個 release。

### 5. 自測（可選）
`run_gui.py` 支援在**已封裝的 EXE 內**做非互動自測，方便驗證封裝是否正確：

| 環境變數 | 用途 |
|---|---|
| `MKG_SELFTEST=1` | 批次轉換指定資料夾（`MKG_SELFTEST_SRC`）並跑更新檢查 |
| `MKG_SELFTEST_UPDATE=1` | 抓取最新 release→下載→驗證 SHA（不真正換版） |
| `MKG_SELFTEST_APPLY=1` | 完整「下載→驗證→就地換版」流程 |

結果寫到 `MKG_SELFTEST_OUT`（預設 `C:\temp\*.txt`）。

---

## 常見問題

- **雙擊 EXE 沒反應？** 確認 `_internal\` 跟著 `markitdown-gui.exe` 在同一資料夾。
- **第一次轉換較慢？** magika 會載入 ONNX 模型（約 3MB）做格式偵測，首檔稍慢之後就快了。
- **更新卡住 / 下載失敗？** 更新是連 `github.com` 下載，請確認網路可連；若仍失敗，請到 Releases 手動下載對應 zip 解壓覆蓋即可。
- **中文亂碼？** 程式介面與產出的 `.md` 皆以 UTF-8 儲存。
