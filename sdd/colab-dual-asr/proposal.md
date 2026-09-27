## 為什麼做

為了解決本地電腦跑語音轉錄時算力不足、發燙、記憶體耗盡問題，並克服單一 Whisper 模型在台灣繁體中文（俚語、專有名詞）辨識上的語意失準。

本功能以**測試驅動開發（TDD）**為品質核心，建立本地 CLI 驅動、透過 Google Colab Control Plane API + Jupyter Kernel WSS 直連的自動化雙引擎轉錄管線。利用 Google AI Pro 提供的 GPU/TPU 算力（TPU v5e-1 / L4 / T4），搭配 `agy cli` 方案 C 語言探測，智慧將任務分流至 **BreezeSprint-25**（繁中最佳化）或 **WhisperSprint**（英文/多語系），支援 YouTube、Google Drive、HTTP(S) 直連影音多元來源，並具備快取前置與孤兒會話防禦性清理契約。

本提案已納入使用者指定之雙語系真實 YouTube 測試案例作為端到端黃金驗收依據：
- **中文黃金樣本**：`https://www.youtube.com/watch?v=mnDNJSopb6Q`
- **英文黃金樣本**：`https://www.youtube.com/watch?v=AzxoU7kxjig`

## 要改什麼

- **本地專案庫準備**：下載 `breezesprint-25` 與 `whispersprint` 儲存庫至本地目錄。
- **虛擬環境與測試框架配置**：建立 `pyproject.toml`，以 `uv` 配置 `pytest` 測試框架及 `google-colab-cli`、`yt-dlp` 等依賴。
- **[TDD] 萬用音訊前處理模組**：先寫單元測試 `tests/test_download.py`（覆蓋 YouTube、Google Drive 3 種 ID 格式、HTTP 直連與 Content-Disposition 解析）$\rightarrow$ 實作 `scripts/universal_download.py` 至測試通過。
- **[TDD] 快取指紋與 Manifest 校驗模組**：先寫測試 `tests/test_cache.py`（覆蓋 URL 正規化快取比對、字幕有效性與 Manifest 生成）$\rightarrow$ 實作快取檢查核心至測試通過。
- **[TDD] 方案 C 語言探測模組**：先寫測試 `tests/test_detect.py`（納入中文 `mnDNJSopb6Q` 與英文 `AzxoU7kxjig` 實體特徵，驗證中繼資料優先、15 秒切片取樣模擬、agy 判定決策樹）$\rightarrow$ 實作 `scripts/detect_language.py` 至測試通過。
- **遠端推論注入驅動核心**：建立 `scripts/run_transcribe.py`，支援 Breeze2 與 Whisper 引擎之遠端推論執行與 Manifest 輸出。
- **產物同步與驗證機制**：建立自動下載遠端 `.srt` 與 `.txt` 至 `output/` 並核對 Manifest 之回傳機制。
- **主入口協調排程腳本**：建立 `run.sh`，整合快取前置命中秒級交付、硬體降級狀態機（TPU v5e-1 $\rightarrow$ L4 $\rightarrow$ T4 $\rightarrow$ CPU）、本地音訊上傳備援與孤兒會話對帳清理。
- **端到端雙語系實機驗收**：以使用者指定之真實中文影片（`mnDNJSopb6Q`）與英文影片（`AzxoU7kxjig`）執行端到端轉錄驗收，確保分流精準、產出合法字幕、支援快取二次命中與自動資源釋放。

## 影響範圍

| 檔案 | 動作 | 說明 |
|------|------|------|
| `breezesprint-25/` | 新增 | 中文最佳化轉錄專案原始碼 |
| `whispersprint/` | 新增 | 英文/多語系轉錄專案原始碼 |
| `pyproject.toml` | 新增 | uv 專案配置、pytest 框架與依賴宣告 |
| `tests/test_download.py` | 新增 | 萬用下載與 URL 特徵解析單元測試 |
| `tests/test_cache.py` | 新增 | 快取指紋與 Manifest 校驗單元測試 |
| `tests/test_detect.py` | 新增 | 方案 C 語言探測與決策邏輯單元測試 (含中英黃金樣本) |
| `scripts/universal_download.py` | 新增 | 萬用音訊下載與轉檔模組 |
| `scripts/detect_language.py` | 新增 | 方案 C 語言探測模組 |
| `scripts/run_transcribe.py` | 新增 | 遠端 Colab 轉錄執行驅動 |
| `run.sh` | 新增 | 主入口調度排程腳本 |
| `output/` | 新增 | 本地字幕檔產物輸出目錄 |
