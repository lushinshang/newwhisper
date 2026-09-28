# SDD 提案：修復本地住宅 IP 救援上傳與 stdout 污染 (fix-fallback-upload)

分類：修 bug

## 為什麼做

在雲端資料中心 IP 下載 YouTube 音訊遭遇 429 Bot 阻擋後，系統成功觸發本地住宅網路救援機制，並順利下載轉檔出 42MB 的音訊檔。但隨後執行 `colab upload` 時，卻拋出 `Local file '[youtube] Extracting...' not found` 錯誤，導致任務中斷並釋放 GPU。

經雙專家（Codex 與 Claude Code）深度逆向審查證實，根本原因在於：
1. `run.sh` 使用命令替換 `PRELOAD_WAV=$(...)` 捕捉輸出，而 `yt-dlp` 的下載與轉碼進度全部輸出至 stdout，導致 `PRELOAD_WAV` 被塞入多行日誌字串，使得 `colab upload` 的 `os.path.isfile(local_path)` 檢查失敗。
2. `scripts/universal_download.py` 原本使用原始標題猜測 output 檔名，特殊字元可能導致回傳不存在的路徑；且未將 yt-dlp 日誌導向 stderr。
3. 遠端暫存目錄未確保預先建立，可能導致上傳失敗；且缺少預載音訊在遠端的存在性與有效性驗證。

## 要改什麼

- **重構 run.sh 救援流程**：
  - 指定確定性的本地中轉檔名（例如 `${LOCAL_STAGING}/input.wav`），由 Python 腳本將音訊直接產出/標準化到該目標路徑，徹底擺脫對 stdout 傳遞路徑的依賴。
  - 將 Python 救援命令的標準輸出全數重導向至 stderr (`1>&2`)，杜絕 stdout 污染。
  - 上傳前加入 `-s "$PRELOAD_WAV"` 防禦性檢查，確保本地檔案存在且非空。
  - 上傳前確保遠端 `/content/audio_staging` 目錄已建立。
  - 在接力推論的注入環境變數中，加入預載音訊的有效性驗證，避免檔案缺失時遠端又退回 URL 下載陷入死循環。
- **優化 scripts/universal_download.py**：
  - 設定 `logtostderr: True`，將 yt-dlp 內部日誌導向 stderr。
  - 改由 `info.get("filepath")` 精準取得後處理後的實際音訊路徑，消除基於標題猜測的潛在錯誤。
  - 確保產物經過 `convert_to_wav` 標準化為 16kHz / mono / PCM16 WAV 檔案。

## 影響範圍

| 檔案 | 動作 | 說明 |
|------|------|------|
| `scripts/universal_download.py` | 修改 | yt-dlp 設定 `logtostderr: True`，改用 `info.get('filepath')` 取得真實檔案路徑 |
| `run.sh` | 修改 | 改為目標路徑傳遞、stdout 導向 stderr、上傳前檢查本地檔案與遠端目錄、注入遠端預載音訊驗證 |
