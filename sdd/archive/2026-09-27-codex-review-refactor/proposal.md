# 提案：基於 Codex Code Review 之安全性、完整性與生命週期防護重構 (codex-review-refactor)

## 為什麼做
透過 `codex exec`（模型 `gpt-6-astra`）全面性審查後，發現目前的轉錄系統存在以下關鍵問題：
1. **注入風險**：`run.sh` 在遠端推論呼叫時以三重單引號拼接字串，未轉義之外部標題或 URL 可能造成語法中斷或程式碼注入。
2. **校驗虛報**：Manifest 原校驗函式宣稱驗證 SHA-256，但實作僅檢驗檔案大小門檻，未實體逐字計算雜湊，無法防範檔案不完整寫入或等長內容竄改。
3. **路徑越界**：`sync_artifacts.py` 解析 Manifest 時直接將遠端檔名進行路徑拼接，若檔名含 `../` 存在路徑遍歷風險。
4. **生命週期與信號防禦**：`run.sh` 啟動時掃描孤兒會話的範圍需更精準；信號 trap 在收到 INT/TERM 時需保證乾淨退出並返回對應退出碼。

本重構旨在消除上述安全隱患、落實嚴格的 SHA-256 數位簽章檢驗，並健全資源清理機制。

## 要改什麼
1. **參數安全序列化**：`run.sh` 改以安全 JSON 編碼或環境變數匯入遠端 Python 腳本，避免字串拼接注入。
2. **實裝嚴格 SHA-256 雜湊校驗**：`cache_manager.py` 中的 `verify_manifest()` 逐檔計算 SHA-256 雜湊值並與 Manifest 記錄比對。
3. **檔名路徑遍歷安全防護**：`sync_artifacts.py` 在下載前強制檢查檔名僅包含安全 basename 與合規副檔名（`.srt`, `.txt`, `.manifest.json`），阻止越界寫入。
4. **信號處理與清理完善**：優化 `run.sh` 的 `cleanup_vm` 與 trap 邏輯，確保中斷時正確退出且安全清理暫存檔。
5. **單元測試補充**：補齊 SHA-256 雜湊校驗失敗、路徑越界攔截、特殊字元注入防禦等邊界單元測試。

## 影響範圍
- 修改：
  - `run.sh`
  - `scripts/cache_manager.py`
  - `scripts/sync_artifacts.py`
  - `tests/test_cache.py`
  - `tests/test_sync_artifacts.py`
