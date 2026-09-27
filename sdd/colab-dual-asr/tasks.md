## 任務清單

- [x] 1. 下載 `breezesprint-25` 與 `whispersprint` 至本地目錄，盤點推論進入點與硬體依賴
- [x] 2. 建立 `pyproject.toml` 並以 `uv` 初始化本地虛擬環境、`pytest` 測試框架與套件依賴
- [x] 3. [TDD] 先撰寫 `tests/test_download.py`（驗證 YT / GDrive 3種ID / 直連解析）$\rightarrow$ 實作 `universal_download.py` 至測試全綠
- [x] 4. [TDD] 先撰寫 `tests/test_cache.py`（驗證 URL 正規化快取指紋與 Manifest 驗證）$\rightarrow$ 實作快取檢查核心至測試全綠
- [x] 5. [TDD] 先撰寫 `tests/test_detect.py`（納入中文 `mnDNJSopb6Q` 與英文 `AzxoU7kxjig` 雙樣本，驗證中繼資料優先、15 秒短音訊與分支）$\rightarrow$ 實作 `detect_language.py` 至測試全綠
- [x] 6. 實作 Colab 遠端推論注入驅動腳本 `scripts/run_transcribe.py`（支援 Breeze2 與 Whisper 引擎推論與 Manifest 生成）
- [x] 7. 實作轉錄產物同步機制（自動下載 `.srt` 與 `.txt` 至 `output/` 並核對 Manifest）
- [x] 8. 實作主入口排程腳本 `run.sh`（快取前置命中秒級交付、硬體降級狀態機、孤兒會話防禦性對帳清理）
- [x] 9. 端到端實機雙語系整合驗收：使用中文測試影片 `https://www.youtube.com/watch?v=mnDNJSopb6Q`（分流 BreezeSprint-25）與英文測試影片 `https://www.youtube.com/watch?v=AzxoU7kxjig`（分流 WhisperSprint）完成驗收與快取二次命中測試
- [x] 10. [實戰驗證] 成功驗證 49 分鐘 Google Drive 長音訊實例（`sample_chinese_lecture_49min.mp3`），L4 GPU 極速轉錄、逐句串流與秒級快取二次命中皆全數通過驗收！

## 驗收條件

- 情境：當執行 `uv run pytest` 時，所有單元測試全數通過（Green）。
- 情境：當使用者執行 `./run.sh` 輸入中文測試影片 `https://www.youtube.com/watch?v=mnDNJSopb6Q` 時，系統在 5 秒內判定為「中文」，調用 BreezeSprint-25，成功於 `output/` 產出繁體中文 `.srt` 與 `.txt`。
- 情境：當使用者執行 `./run.sh` 輸入英文測試影片 `https://www.youtube.com/watch?v=AzxoU7kxjig` 時，系統在 5 秒內判定為「英文/非中文」，調用 WhisperSprint，成功於 `output/` 產出英文 `.srt` 與 `.txt`。
- 情境：當再次輸入上述任一 YouTube 網址時，系統在 1 秒內命中快取直接交付字幕檔，不啟動雲端虛擬機。
- 情境：當使用者輸入 Google Drive 分享連結或 HTTP 直連影音，系統就正確下載並轉換為標準 WAV 音檔供模型推論。
- 情境：當轉錄任務完成或本機中途異常中斷，系統就安全釋放雲端虛擬機，並在下次啟動時主動對帳清理殘留之孤兒會話。
