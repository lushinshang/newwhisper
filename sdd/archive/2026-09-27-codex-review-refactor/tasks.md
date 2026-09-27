# 任務清單：Codex Review 安全性與穩定性改善 (codex-review-refactor)

- [x] 任務 1：重構 `run.sh` 遠端注入邏輯，使用安全 JSON 序列化傳入執行參數
- [x] 任務 2：重構 `scripts/cache_manager.py` 的 `verify_manifest()`，落實實體 SHA-256 雜湊計算比對
- [x] 任務 3：重構 `scripts/sync_artifacts.py`，加入檔名 Path Traversal 與副檔名白名單防禦
- [x] 任務 4：改進 `run.sh` 的信號處理與 Session 清理狀態機（確保 INT/TERM 正確退出且清理暫存）
- [x] 任務 5：擴充 `tests/test_cache.py`，新增「篡改內容 SHA-256 驗證失敗」與「缺少雜湊欄位攔截」之測試
- [x] 任務 6：擴充 `tests/test_sync_artifacts.py`，新增「檔名含 `../` 越界路徑防禦攔截」之測試
- [x] 任務 7：執行全量單元測試 (`uv run pytest`)，確保全綠且所有功能相容正常

## 驗收條件
- 情境：當 Manifest 記錄的檔案內容遭到篡改（大小相同但內容不同），`verify_manifest()` 必須回傳 `False` 攔截錯誤產物。
- 情境：當遠端 Manifest 中的檔名被惡意修改為 `../../etc/passwd` 或包含路徑分隔符號時，`sync_artifacts.py` 必須立刻拒絕下載並拋出錯誤。
- 情境：當音訊標題包含單雙引號、換行符號或 Python 程式碼語法時，`run.sh` 傳遞參數至遠端 Colab 時不會引發語法崩潰或注入。
- 情境：當使用者在轉錄過程中按下 `Ctrl+C` 中斷時，系統能安全停止雲端會話、清理本地臨時檔並以正確退出碼中斷。
- 情境：執行全量測試，所有測試案例（包含新補齊的安全性邊界測試）全數綠燈通過。
