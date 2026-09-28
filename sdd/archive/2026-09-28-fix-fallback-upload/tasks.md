## 任務清單

- [x] 1. 優化 `scripts/universal_download.py`：設定 yt-dlp `logtostderr: True`，並由 `info.get('filepath')` 精準取得後處理完成的路徑
- [x] 2. 重構 `run.sh` 本地救援直傳邏輯：改由命令列參數傳入目標檔案 `${LOCAL_STAGING}/input.wav`，所有下載訊息導向 stderr，徹底消除 stdout 污染
- [x] 3. 補強 `run.sh` 防禦性檢查：上傳前檢查本地檔案非空、確保遠端 `/content/audio_staging` 目錄存在、接力推論前注入預載音訊有效性檢查
- [x] 4. 執行全量單元測試 (`uv run pytest`)，確保現有 27 項測試 100% 綠燈通過

## 驗收條件

- 情境：當遠端下載失敗觸發本地住宅 IP 救援時，`PRELOAD_WAV` 變數僅包含純淨合法的檔案路徑，`colab upload` 不再拋出 `Local file not found` 錯誤。
- 情境：當影片標題含有特殊字元時，`universal_download.py` 能正確透過 `info.get('filepath')` 取得真實產出路徑，不會回傳不存在的檔案。
- 情境：當執行 `uv run pytest` 時，所有 27 個單元測試均能正常通過。
