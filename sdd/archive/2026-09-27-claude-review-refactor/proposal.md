# 提案：基於 Claude Code (Opus) 審查之邊界健全度與強韌性重構 (claude-review-refactor)

## 為什麼做
在 Claude Code（Opus 旗艦模型）的深度審查中，指出了系統實務上的幾個關鍵邊界隱患：
1. **快取防偽驗證缺失**：`is_cache_hit()` 未呼叫 `verify_manifest()`，若本地存在殘留或不完整檔案會誤判命中而交付錯誤產物。
2. **省略號檔名誤殺**：`validate_artifact_filename` 使用 `".." in fname`，導致帶有常見英文省略號（如 `Wait... what?`）的正常標題在轉錄後被判定為惡意越界而同步失敗。
3. **檔名字節過長崩潰風險**：未針對 Linux 檔案系統（NAME_MAX = 255 bytes）進行 UTF-8 字節限長，長中文標題推論完寫檔時會拋出 `OSError: File name too long` 白白浪費雲端點數。
4. **音訊 16kHz PCM16 Mono 保證不足**：遇 `.wav` 副檔名未檢查取樣率即跳過轉碼，高採樣或多聲道音訊可能影響推論品質與效能。
5. **產物同步原子性不足**：同步直接寫入正式目錄，傳輸中斷可能污染或覆蓋既有良品。

## 要改什麼
1. **快取完全依賴 Manifest 完整性**：重構 `is_cache_hit()`，一律以 `verify_manifest()` 之 SHA-256 驗證作為唯一命中判斷。
2. **精確化檔名越界檢查**：修正 `validate_artifact_filename`，只阻擋真正的路徑跳脫（`os.path.basename(fname) != fname` 及排除 `.`/`..`），允許正常的文字省略號 `...`。
3. **安全限長（200 UTF-8 Bytes）**：重構 `sanitize_title_for_filename`，以 UTF-8 Bytes 限制在 200 位元組內，避免截斷多位元組字元，保留副檔名字節空間。
4. **統一強制 16kHz PCM16 Mono 轉碼**：重構 `convert_to_wav`，強制以 `ffmpeg` 轉碼為 16000Hz、單聲道、`pcm_s16le` 格式。
5. **原子化產物同步**：重構 `sync_artifacts.py`，先下載至獨立暫存區，校驗通過後再以原子操作替換發布。
6. **擴充單元測試**：針對省略號標題、超長中文字節截斷、壞檔快取阻擋、原子同步失敗回滾進行完整覆蓋。

## 影響範圍
- `scripts/cache_manager.py`
- `scripts/sync_artifacts.py`
- `scripts/universal_download.py`
- `tests/test_cache.py`
- `tests/test_sync_artifacts.py`
- `tests/test_download.py`
