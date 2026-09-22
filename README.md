# MarkItDown

[![PyPI](https://img.shields.io/pypi/v/markitdown.svg)](https://pypi.org/project/markitdown/)
![PyPI - Downloads](https://img.shields.io/pypi/dd/markitdown)

> [!IMPORTANT]
> MarkItDown 會以目前程序（process）的權限進行 I/O。就像 `open()` 或 `requests.get()` 一樣，它會存取該程序本身能存取的資源。在不受信的環境中請對輸入做消毒（sanitize），並針對你的使用情境呼叫最精確的 `convert_*` 函式（例如 `convert_stream()` 或 `convert_local()`）。更多資訊請見文件中的[安全注意事項](#安全注意事項)章節。

MarkItDown 是一個輕量級的 Python 工具，可用來將各種檔案轉換為 Markdown，供 LLM 與相關的文字分析管線使用。為了這個目的，它最接近 [textract](https://github.com/deanmalmgren/textract)，但著重於以 Markdown 保留重要的文件結構與內容（包括：標題、清單、表格、連結等等）。雖然輸出通常相當可觀且對人類友善，但它的目的是給文字分析工具使用——未必是人類消費用途之高保真文件轉換的最佳選擇。

MarkItDown 目前支援從以下來源轉換：

- PDF
- PowerPoint
- Word
- Excel
- 圖片（EXIF 中繼資料與 OCR）
- 音訊（EXIF 中繼資料與語音轉錄）
- HTML
- 以文字為基礎的格式（CSV、JSON、XML）
- ZIP 檔案（逐一迭代其內容）
- YouTube URL
- EPub
- ……以及更多！

## 為什麼是 Markdown？

Markdown 非常接近純文字，標記與格式極少，但仍能表示重要的文件結構。主流 LLM（例如 OpenAI 的 GPT-4o）天生就「會說話」Markdown，且常常在未經提示的情況下就把 Markdown 納入其回應。這顯示它們經過大量 Markdown 格式文字的訓練、且對它理解良好。帶一個額外的好處是，Markdown 慣例在 token 上也非常高效。

## 先決條件
MarkItDown 需要 Python 3.10 至 3.14。建議使用虛擬環境以避免依賴衝突。

使用標準的 Python 安裝，你可以用下列指令建立並啟動虛擬環境：

```bash
python -m venv .venv
source .venv/bin/activate
```

如果使用 `uv`，可以用：

```bash
uv venv --python=3.12 .venv
source .venv/bin/activate
# 注意：請務必使用 'uv pip install' 而不是單純的 'pip install'，來在此虛擬環境中安裝套件
```

如果你使用 Anaconda，可以用：

```bash
conda create -n markitdown python=3.12
conda activate markitdown
```

## 安裝

要安裝 MarkItDown，使用 pip：`pip install 'markitdown[all]'`。或者，你也可以從原始碼安裝：

```bash
git clone git@github.com:microsoft/markitdown.git
cd markitdown
pip install -e 'packages/markitdown[all]'
```

## 使用

### 命令列（Command-Line）

```bash
markitdown path-to-file.pdf > document.md
```

或使用 `-o` 指定輸出檔案：

```bash
markitdown path-to-file.pdf -o document.md
```

你也可以用管道（pipe）送入內容：

```bash
cat path-to-file.pdf | markitdown
```

### 選擇性依賴（Optional Dependencies）
MarkItDown 有選擇性依賴，用來啟用各種檔案格式。文件前面我們以 `[all]` 選項安裝了所有選擇性依賴。不過，你也可以分別安裝它們以獲得更多控制。例如：

```bash
pip install 'markitdown[pdf, docx, pptx]'
```

就只會安裝 PDF、DOCX 與 PPTX 檔案的依賴。

目前可用的選擇性依賴如下：

* `[all]` 安裝所有選擇性依賴
* `[pptx]` 安裝 PowerPoint 檔案的依賴
* `[docx]` 安裝 Word 檔案的依賴
* `[xlsx]` 安裝 Excel 檔案的依賴
* `[xls]` 安裝較舊 Excel 檔案的依賴
* `[pdf]` 安裝 PDF 檔案的依賴
* `[outlook]` 安裝 Outlook 訊息的依賴
* `[az-doc-intel]` 安裝 Azure Document Intelligence 的依賴
* `[az-content-understanding]` 安裝 Azure Content Understanding 的依賴
* `[audio-transcription]` 安裝 wav 與 mp3 檔案語音轉錄的依賴
* `[youtube-transcription]` 安裝擷取 YouTube 影片轉錄的依賴

### 外掛（Plugins）

MarkItDown 也支援第三方外掛。外掛預設是停用的。要列出已安裝的外掛：

```bash
markitdown --list-plugins
```

要啟用外掛，使用：

```bash
markitdown --use-plugins path-to-file.pdf
```

要尋找可用外掛，請在 GitHub 搜尋標籤 `#markitdown-plugin`。要開發外掛，請參考 `packages/markitdown-sample-plugin`。

#### markitdown-ocr 外掛

`markitdown-ocr` 外掛為 PDF、DOCX、PPTX 與 XLSX 轉換器加上 OCR 支援，使用 LLM Vision 從嵌入圖片中提取文字——與 MarkItDown 已用於圖片描述的 `llm_client` / `llm_model` 模式相同。不需要新增 ML 函式庫或二進位依賴。

**安裝：**

```bash
pip install markitdown-ocr
pip install openai  # 或任何 OpenAI 相容的 client
```

**使用：**

傳入與圖片描述相同的 `llm_client` 與 `llm_model`：

```python
from markitdown import MarkItDown
from openai import OpenAI

md = MarkItDown(
    enable_plugins=True,
    llm_client=OpenAI(),
    llm_model="gpt-4o",
)
result = md.convert("document_with_images.pdf")
print(result.markdown)
```

若未提供 `llm_client`，外掛仍會載入，但 OCR 會被靜默略過，改用標準的內建轉換器。

詳細文件請見 [`packages/markitdown-ocr/README.md`](packages/markitdown-ocr/README.md)。

### Azure Content Understanding

[Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/) 提供更高品質的轉換、結構化欄位抽取（YAML front matter）、多模態支援（文件、圖片、音訊、影片），以及可配置的解析器（analyzers）。

安裝：`pip install 'markitdown[az-content-understanding]'`

#### 何時使用 Content Understanding

Content Understanding 適用於你需要內建或 Document Intelligence 轉換器無法提供之能力的情境：

- **音訊與影片檔案**——CU 是影片的唯一選項，也是音訊較高品質的雲端選項。內建轉換器不支援影片，且只有基礎的音訊轉錄。
- **結構化欄位抽取**——[Prebuilt](https://learn.microsoft.com/azure/ai-services/content-understanding/concepts/prebuilt-analyzers) 或 [custom-built](https://learn.microsoft.com/azure/ai-services/content-understanding/how-to/customize-analyzer-content-understanding-studio?tabs=portal) 解析器可抽取領域特定的欄位（發票金額、收據日期、合約條款），並序列化為 YAML front matter。內建整合與 Doc Intel 整合都沒辦法暴露欄位。
- **更高質量的文件抽取**——對掃描 PDF、複雜表格與多頁文件的雲端版面分析与 OCR。
- **單一 API 對齊所有模態**——一個 `cu_endpoint` 即可透過自動解析器路由處理文件、圖片、音訊與影片。

| 能力 | 內建轉換器 | Azure Document Intelligence | Azure Content Understanding |
|------------|---------------------|-----------------------------|-----------------------------|
| 文件轉換 | 離線、特定格式抽取 | 雲端版面抽取 | 雲端多模態抽取 |
| 結構化欄位 | 不可用 | 該整合未暴露 | 由解析器欄位產出 YAML front matter |
| 自訂解析器 | 不可用 | 該整合中不可配置 | 以 `cu_analyzer_id` 支援 |
| 音訊與影片 | 基礎音訊、無影片 | 不支援 | 音訊與影片解析器 |
| 成本 | 僅本地運算 | 計費的 Azure API 呼叫 | 計費的 Azure API 呼叫 |

**CLI：**

```bash
markitdown path-to-file.pdf --use-cu --cu-endpoint "<content_understanding_endpoint>"
```

端點也可以在環境中一次設定好，這樣呼叫者只需要 `--use-cu`：

```bash
export MARKITDOWN_CU_ENDPOINT="<content_understanding_endpoint>"
markitdown path-to-file.pdf --use-cu
```

**Python API：**

```python
from markitdown import MarkItDown

# Zero-config — 依檔案類型自動選擇解析器
md = MarkItDown(cu_endpoint="<content_understanding_endpoint>")
result = md.convert("report.pdf")   # documents → prebuilt-documentSearch
result = md.convert("meeting.mp4")  # video → prebuilt-videoSearch
result = md.convert("call.wav")     # audio → prebuilt-audioSearch
print(result.markdown)
```

**使用自訂解析器**（用於領域特定的欄位抽取）：

```python
md = MarkItDown(
    cu_endpoint="<content_understanding_endpoint>",
    cu_analyzer_id="my-invoice-analyzer",
)
result = md.convert("invoice.pdf")
print(result.markdown)
# Output includes YAML front matter with extracted fields:
# ---
# contentType: document
# fields:
#   VendorName: CONTOSO LTD.
#   InvoiceDate: '2019-11-15'
# ---
# <!-- page 1 -->
# ...
```

當 `cu_analyzer_id` 被設定時，轉換器會依解析器的模態自動把它限制在相容的檔案類型。不相容的類型（例如對音訊檔案使用文件解析器）會自動路由到預設的 prebuilt 解析器。

**成本提醒：** 每一次對 CU 路由類型的 `convert()` 呼叫，都是一次計費的 Azure API 呼叫。使用 `cu_file_types` 限制哪些類型路由到 CU：

```python
from markitdown.converters import ContentUnderstandingFileType

md = MarkItDown(
    cu_endpoint="<content_understanding_endpoint>",
    cu_file_types=[ContentUnderstandingFileType.PDF],  # 只有 PDF 使用 CU
)
```

關於 Azure Content Understanding 的更多資訊，可見[這裡](https://learn.microsoft.com/azure/ai-services/content-understanding/)。

### Azure Document Intelligence

要使用 Microsoft Document Intelligence 進行轉換：

```bash
markitdown path-to-file.pdf -o document.md -d -e "<document_intelligence_endpoint>"
```

端點也可以在環境中一次設定好，這樣呼叫者只需要 `-d`：

```bash
export MARKITDOWN_DOCINTEL_ENDPOINT="<document_intelligence_endpoint>"
markitdown path-to-file.pdf -o document.md -d
```

關於如何建立 Azure Document Intelligence 資源的更多資訊，可見[這裡](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/create-document-intelligence-resource?view=doc-intel-4.0.0)

### Python API

Python 中的基本用法：

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False) # 若要啟用外掛請設為 True
result = md.convert("test.xlsx")
print(result.markdown)
```

Python 中的 Document Intelligence 轉換：

```python
from markitdown import MarkItDown

md = MarkItDown(docintel_endpoint="<document_intelligence_endpoint>")
result = md.convert("test.pdf")
print(result.markdown)
```

要用大型語言模型（LLM）做圖片描述（目前僅支援 pptx 與圖片檔案），請提供 `llm_client` 與 `llm_model`：

```python
from markitdown import MarkItDown
from openai import OpenAI

client = OpenAI(max_retries=5)
md = MarkItDown(llm_client=client, llm_model="gpt-4o", llm_prompt="optional custom prompt")
result = md.convert("example.jpg")
print(result.markdown)
```

`max_retries` 控制 OpenAI client 對可重試錯誤的自動重試次數（預設為 2）；`5` 代表最多六次嘗試並附帶退避（backoff）。請參考 [OpenAI SDK 的重試文件](https://github.com/openai/openai-python#retries)。

只要有任何一次嘗試成功，圖片轉換就會正常繼續。若 client 在重試耗盡後仍丟出錯誤，或遇到不可重試的錯誤，MarkItDown 會嘗試其他適用的轉換器，只有在全部失敗時才會丟出 `FileConversionException`。

### Docker

```sh
docker build -t markitdown:latest .
docker run --rm -i markitdown:latest < ~/your-file.pdf > output.md
```

## 貢獻（Contributing）

在開始重要工作前，請先閱讀[要貢獻什麼](#要貢獻什麼)，它以說明這個 repository 的範圍（in/out of scope）。

本專案歡迎貢獻與建議。多數貢獻需要你同意一份「貢獻者授權協議」（CLA），聲明你有權且確實願意授予我們使用你的貢獻的權利。詳情請參訪 https://cla.opensource.microsoft.com。

當你提交 pull request 時，CLA bot 會自動判斷你是不是需要提供 CLA，並適當地標註該 PR（例如 status check、comment）。你只要遵循 bot 提供的指示即可。在所有使用我們 CLA 的 repos 中你只需要做一次。

本專案已採用 [Microsoft 開源行為準則](https://opensource.microsoft.com/codeofconduct/)。更多資訊請參閱 [行為準則 FAQ](https://opensource.microsoft.com/codeofconduct/faq/)，或有任何額外問題或意見，致信 [opencode@microsoft.com](mailto:opencode@microsoft.com)。

### 要貢獻什麼

MarkItDown 是一個把檔案轉換成 Markdown、供 LLM 與相關文字分析管線使用的 Python 工具。這個 repository 的用途是提供可整合進其他系統的 Python 函式庫——而不是建立在其上的終端使用者的應用程式。

#### 範圍內（In scope）

- 改善現有轉換器的還原度（fidelity）（新格式的加入會審慎處理——特別是當它們會引入新的依賴時。多數情況下，新格式能透過[第三方外掛](#不需修改本-repository-即可延伸-markitdown)獲得更好的支援。）
- Bug 修正、效能改善與安全性修正
- `markitdown` 命令列介面
- `markitdown-mcp` 套件
- 測試、文件與開發者工具

#### 範圍外（Out of scope）

我們無法接受額外的應用程式、服務或伺服器。這包括：

- Web 伺服器、REST 或 HTTP API，以及託管式的轉換服務
- Web 前端與瀏覽器端的介面
- 桌面與行動應用（PyQt、PySide、Tkinter、Electron、Flutter 之類）

這類專案确实很有用，我們寧願看到它們茁壯成長，而不是被擋在門外。如果你希望為 MarkItDown 提供 web 服務、API 或圖形化應用，請把它作為一個依賴 [PyPI 上的 markitdown](https://pypi.org/project/markitdown/) 的獨立套件或專案來維持。

### 不需修改本 repository 即可延伸 MarkItDown

MarkItDown 支援第三方外掛，所以對新格式的支援可以獨立於這個 repository 發布與安裝：

```sh
markitdown --list-plugins
markitdown --use-plugins path-to-file.pdf
```

從 `packages/markitdown-sample-plugin` 開始，並把你的 repository 標上 `#markitdown-plugin` 標籤，讓其他人能找得到。

### 如何貢獻

你可以透過查看 issues 或協助審查 PR 來幫忙。我們也把部分 issues 標記為「open for contribution」、部分 PR 標記為「open for reviewing」，藉此促進社群貢獻。這些標籤只是建議；在上述範圍內的貢獻都歡迎。

<div align="center">

|            | All                                                          | 特別是來自社群需要的協助                                                                                                      |
| ---------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Issues** | [All Issues](https://github.com/microsoft/markitdown/issues) | [Issues open for contribution](https://github.com/microsoft/markitdown/issues?q=is%3Aissue+is%3Aopen+label%3A%22open+for+contribution%22) |
| **PRs**    | [All PRs](https://github.com/microsoft/markitdown/pulls)     | [PRs open for reviewing](https://github.com/microsoft/markitdown/pulls?q=is%3Apr+is%3Aopen+label%3A%22open+for+reviewing%22)              |

</div>

### 執行測試與檢查

- 進入 MarkItDown 套件：

  ```sh
  cd packages/markitdown
  ```

- 在你的環境安裝 `hatch` 並執行測試：

  ```sh
  pip install hatch  # 安裝 hatch 的其他方法：https://hatch.pypa.io/dev/install/
  hatch shell
  hatch test
  ```

  （替代方案）使用已安裝所有依賴的 Devcontainer：

  ```sh
  # 在 Devcontainer 中重新開啟專案並執行：
  hatch test
  ```

- 在提交 PR 前執行 pre-commit 檢查：`pre-commit run --all-files`

### 安全注意事項

MarkItDown 會以目前程序的權限進行 I/O。就像 `open()` 或 `requests.get()` 一樣，它會存取該程序本身能存取的資源。

**對輸入做消毒：** 不要直接把不受信的輸入傳給 MarkItDown。若輸入的任何部分可能由不受信的使用者或系統控制（例如在託管或伺服器端應用程式中），就必須在呼叫 MarkItDown 前驗證並加以限制。這對你的環境而言，可能包括限制檔案路徑、限制 URI scheme 與網路目的地，以及封鎖對私有、迴圈（loopback）、鏈路本地（link-local）或 metadata 服務（metadata-service）位址的存取。

**只呼叫你需要的轉換方法：** 優先選擇符合你使用情境的最精確轉換 API。MarkItDown 的 `convert()` 方法刻意是寬容的，可以處理本地檔案、遠端 URI 與 byte stream。如果你的應用程式只需要讀取本地檔案，請改用 `convert_local()`。如果你需要對 URI 擷取更多控制，請自行呼叫 `requests.get()`，並把 response 物件傳給 `convert_response()`。若要最大程度的控制，開一個到你想要轉換的輸入的 stream，並呼叫 `convert_stream()`。

## 商標（Trademarks）

本專案可能包含某些專案、產品或服務的商標或標誌。Microsoft 商標或標誌的授權使用，須遵循
[Microsoft 的商標與品牌指南](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general)。
在修改版本中對 Microsoft 商標或標誌的使用，不得造成混淆或暗示 Microsoft 的贊助。
任何第三方商標或標誌的使用，都須遵循對應第三方的政策。
