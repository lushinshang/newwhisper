# 任務清單：Claude Code (Opus) 審查之邊界健全度與強韌性改善 (claude-review-refactor)

- [x] 任務 1：重構 `cache_manager.py` 的 `is_cache_hit()`，改為必須通過 `verify_manifest()` 才視為命中
- [x] 任務 2：修正 `sync_artifacts.py` 的 `validate_artifact_filename`，解鎖標題省略號 `...` 同時保持路徑跳脫防禦
- [x] 任務 3：在 `cache_manager.py` 的 `sanitize_title_for_filename` 加入 200 位元組（UTF-8 bytes）安全長度截斷
- [x] 任務 4：重構 `universal_download.py` 的 `convert_to_wav`，強制以 ffmpeg 產出標準 16kHz PCM16 Mono 音訊
- [x] 任務 5：重構 `sync_artifacts.py` 實作原子化同步（Staging 暫存下載 + 驗證通過後原子替換）
- [x] 任務 6：擴充 `tests/test_cache.py`，新增「壞檔不命中快取」與「超長中文標題安全截斷」測試
- [x] 任務 7：擴充 `tests/test_sync_artifacts.py`，新增「標題含省略號正常放行」與「原子同步中斷不污染」測試
- [x] 任務 8：執行全量單元測試 (`uv run pytest`)，確保全綠且所有功能相容正常

## 驗收條件
- 情境：當目錄下存在大小大於 10 bytes 但未經 Manifest 簽章或 SHA-256 損壞的檔案時，`is_cache_hit()` 必須回傳 `False`，避免交付壞檔。
- 情境：當影片標題包含英文省略號（如 `Wait... what.srt`）時，`validate_artifact_filename()` 必須回傳 `True` 正確放行。
- 情境：當影片標題為 100 個中文漢字（300 bytes）時，`sanitize_title_for_filename()` 產出的字串編碼後必須小於等於 200 bytes，且不切斷中文多字節字元。
- 情境：當輸入任意音訊或不同取樣率的 WAV 檔時，`convert_to_wav()` 輸出的檔案必為 16kHz、單聲道、`pcm_s16le`。
- 情境：當同步過程中校驗失敗時，本地原本存在的良品檔案必須原封不動保持完好。
- 情境：全量測試通過，0 迴歸錯誤。
