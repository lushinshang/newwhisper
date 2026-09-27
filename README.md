# Colab Dual ASR：把 Google AI Pro 的 200 點算力，變成一台隨叫隨到的轉錄機

[![Version](https://img.shields.io/badge/version-v2.0.0-blue.svg)](prd.html)
[![GitHub Repo](https://img.shields.io/badge/github-lushinshang%2Fnewwhisper-181717.svg?logo=github)](https://github.com/lushinshang/newwhisper)
[![Tests](https://img.shields.io/badge/tests-27%2F27%20passed-success.svg)](tests/)
[![Security Audit](https://img.shields.io/badge/security%20audit-passed%20100%25-brightgreen.svg)](his.html)
[![Architecture](https://img.shields.io/badge/review-Codex%20%26%20Claude-orange.svg)](his.html)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 目錄
- [先講痛點：轉錄這件事，到底卡在哪](#先講痛點轉錄這件事到底卡在哪)
- [核心特色](#核心特色)
- [系統架構圖](#系統架構圖)
- [快速開始](#快速開始)
- [常用指令範例](#常用指令範例)
- [輸出檔案與 Manifest 規範](#輸出檔案與-manifest-規範)
- [自動化測試與品質保證](#自動化測試與品質保證)
- [工業級防禦性設計](#工業級防禦性設計)
- [資安稽核與隱私保護](#資安稽核與隱私保護)
- [致謝與引用](#致謝與引用)
- [專案文檔導覽](#專案文檔導覽)

---

## 先講痛點：轉錄這件事，到底卡在哪

一支 49 分鐘的中文演講丟進本機的 Whisper，MacBook 風扇轉到最大聲，記憶體條一路飆到見底，最後跳出一行 `Killed`——OOM，什麼都沒留下。換個做法，把音檔丟上網頁版的 Colab 跑，這次順利跑完了，但隔天打開帳單才發現，忘記關閉的 VM 已經在背景空轉了六個小時，把這個月的運算點數燒掉一大截。

問題不在模型不夠好，也不在筆電不夠力，而在於「轉錄」這件事一直卡在兩個爛選項之間：本機硬扛，扛不動；雲端網頁版跑，跑完了不會自己走。中間缺一條路——用得到雲端的算力，又不必透過瀏覽器分頁盯著、也不用擔心忘記按停止鍵。

Google AI Pro 訂閱每月附贈 200 點 Colab 運算額度，多數人用不完，也懶得用——因為要開 Notebook、貼程式碼、手動掛載雲端硬碟，一套流程走下來比自己轉錄還累。這 200 點，本質上是一筆放在那裡沒人領的算力補貼。這個專案要做的事很單純：把這筆補貼，透過一行終端機指令直接兌現。

## 核心特色

### 本機 CLI 直連 Colab，中間沒有任何跳板

不架設自己的雲端 VM，不透過 WebUI，不繞 Cloudflare Tunnel 或 ngrok。本機終端機用 `google-colab-cli` 直接對接 Colab 的 Control Plane API 與 Jupyter Kernel WebSocket，一行 `./run.sh` 就完成環境掛載、程式碼執行、產物回傳的整趟流程。省下的不只是設定的力氣，是每一次「開瀏覽器、找分頁、確認還在跑」的心智負擔。

### 實測數據：一小時影音，大約半點算力

在 Colab 的 L4 GPU 上實測過兩種典型場景：

- 49 分鐘的台灣繁體中文演講，推論耗時約 **3 分鐘**。
- 61 分鐘的 MIT 英語課程，推論耗時約 **3.5 分鐘**。

換算下來，一小時的影音轉錄大約只吃掉 **0.2 到 0.5 點**運算額度。每月 200 點的額度，理論上可以從容轉錄數百小時的內容——前提是額度不要被忘記關閉的 VM 默默吃掉，這點後面會講怎麼解決。

### 為什麼要兩套模型，而不是一套打天下

單一模型打天下聽起來省事，但語音辨識這件事，語言之間的差異比想像中更難用一套參數蓋過去。

**台灣繁體中文** 走的是 **BreezeSprint-25**，底層是中研院與聯發科特化過的 Breeze2-Whisper(引用自 [thc1006/breezesprint-25](https://github.com/thc1006/breezesprint-25))。一般 Whisper 系列模型的訓練語料裡，繁簡中文常常混在一起，結果就是轉出來的逐字稿會夾雜簡體字詞，標點也偏西式半形逗點，讀起來有一種「翻譯腔」。Breeze2 專門針對台灣用語、口音與全形標點做過調校，同樣一句話，轉出來的斷句習慣更貼近台灣人平常寫作的樣子。

**其他語言** 走的是 **WhisperSprint**(引用自 [thc1006/whispersprint](https://github.com/thc1006/whispersprint))，用 CTranslate2 重新實作的 faster-whisper large-v3，吃多國語言、跨國會議、英語授課這類場景，推論速度比原生 Whisper 快上不少。

兩套模型各自守住自己最擅長的語境，不互相妥協。

### 智慧混合偵測：不用自己選引擎

系統怎麼知道一支影片該丟給 Breeze2 還是 faster-whisper?流程分兩層:先讀影片的中繼資料(標題、標籤)判斷語言;如果標題模稜兩可(例如中文演講取了英文標題)，就切一段前 15 秒的音訊做語音特徵分析。整個判斷在 5 秒內完成，不需要使用者自己選引擎——除非標題真的會誤導系統，才需要手動加 `--lang zh` 覆寫。

### 住宅 IP 自動救援：繞過 YouTube 的機房封鎖

Colab 的伺服器跟一般雲端機房一樣，IP 落在資料中心網段。YouTube 對這類 IP 的風控向來嚴格，常見的下場是一句 `Sign in to confirm you're not a bot`，直接把下載擋下來。

這裡設計了兩軌降級機制。第一軌是遠端 VM 直接在雲端拉取音訊，頻寬快、不佔本機網路;一旦被 YouTube 判定為機房 IP 擋下，遠端會回報一個 FALLBACK 訊號，系統自動切換第二軌——由本機的住宅 IP(也就是使用者家裡或公司的正常網路)接手抓取音訊，再上傳回 Colab 接續推論。使用者從頭到尾不需要察覺這次切換發生過，唯一的差別是多花了幾秒鐘的上傳時間。

### 用完就關機：不留殭屍 VM 燒點數

前面提到，忘記關閉的 Colab VM 是預算失控最常見的原因。這個專案用 POSIX 訊號捕捉處理這件事——不管是正常結束(EXIT)、使用者按下 Ctrl+C(SIGINT)、還是行程被強制終止(SIGTERM)，都會觸發 `trap`，確保 `colab stop` 一定被呼叫。每次啟動前，系統還會自動巡檢一輪，清掉上次意外留下的孤兒實例。點數只在真正推論的那幾分鐘被消耗，其餘時間，VM 不存在。

### 重複呼叫不用等雲端：本地快取秒級交付

在建立任何雲端連線之前，系統會先檢查本地 `output/` 底下是否已經有對應的產物，並用 `verify_manifest` 做 SHA-256 雜湊校驗確認檔案完整。命中的話，0.2 秒內直接交付，不消耗任何算力點數——同一支影片轉錄第二次，不該再付一次錢。

---

## 系統架構圖

採用直屏友好的由上而下(`flowchart TD`)架構設計，手機直屏與寬螢幕皆可順暢閱讀:

```mermaid
flowchart TD
    subgraph Local["本地端 (Local Machine)"]
        User["使用者輸入音訊/影片網址"] --> CacheCheck{"前置快取驗證<br>(verify_manifest SHA-256)"}
        CacheCheck -- "命中" --> FastDeliver["⚡ 秒級交付現成字幕 (0.2s)<br>(0 雲端通訊、0 點數消耗)"]
        
        CacheCheck -- "未命中" --> Reconcile["孤兒 Session 巡檢清理<br>(清理殘留殭屍 VM)"]
        Reconcile --> RunSh["調度核心 (run.sh)"]
        RunSh --> Detect["智慧混合語言偵測<br>(中繼資料優先 + 15s 短音訊特徵備援)"]
        
        Detect --> Decision{"語言分流"}
        Decision -- "中文" --> Breeze["BreezeSprint-25 (Breeze2-Whisper)"]
        Decision -- "非中文" --> Whisper["WhisperSprint (faster-whisper)"]
        
        Breeze --> Payload["Base64 + JSON 安全序列化 Payload<br>(免疫 Bash 三重引號注入)"]
        Whisper --> Payload
        
        Rescue["本地住宅 IP 救援機制<br>(yt-dlp + ffmpeg PCM16 16k)"]
    end

    subgraph Colab["Google Colab 雲端基礎設施"]
        ColabCLI["google-colab-cli (uv 隔離)"]
        ColabCLI == "Jupyter Kernel WSS" ==> GPU["Google AI Pro GPU (L4 / T4)"]
        
        GPU --> CloudFetch{"第一軌:雲端拉取音訊"}
        CloudFetch -- "成功" --> Infer["模型推論轉錄"]
        CloudFetch -- "遇 YouTube Bot 429" --> FallbackSignal["遠端回報 FALLBACK 訊號"]
        
        FallbackSignal -. 通知本地住宅 IP 抓取 .-> Rescue
        Rescue -. "colab upload 上傳" .-> Infer
        
        Infer --> GenArtifacts["生成字幕 (.srt / .txt)<br>簽署 manifest.json (SHA-256)"]
    end

    Payload -. 注入執行代碼 .-> ColabCLI
    GenArtifacts == "下載至 .staging/ 暫存區" ==> VerifyManifest{"SHA-256 數位雜湊校驗"}
    VerifyManifest -- "驗證通過" --> AtomicMove["原子替換至 output/"]
    AtomicMove --> Done["轉錄交付完成"]
```

---

## 快速開始

### 環境前置需求
- **作業系統**:macOS 或 Linux
- **工具鏈**:
  - [uv](https://docs.astral.sh/uv/)(極速 Python 套件管理器)
  - [ffmpeg](https://ffmpeg.org/)(音訊切片與轉檔)
  - [gcloud CLI](https://cloud.google.com/sdk/docs/install)(已登入 Application Default Credentials)

```bash
# 1. 確保 gcloud 具有 Colab 權限
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/colaboratory,https://www.googleapis.com/auth/cloud-platform"

# 2. 複製專案並安裝依賴 (使用 uv 自動管理虛擬環境)
uv sync
```

---

## 常用指令範例

### 基本用法（自動探測語言並分流調度）
```bash
# 轉錄 YouTube 影片 (自動依標題/內容分流至 Breeze2 或 Whisper)
./run.sh "https://www.youtube.com/watch?v=hy8UstR2NEg"

# 轉錄 Google Drive 分享連結 (49 分鐘繁中演講實測通過)
./run.sh "https://drive.google.com/file/d/1YourFileIdHere/view"

# 轉錄 HTTP(S) 音訊直連網址
./run.sh "https://example.com/audio/sample.mp3"
```

### 指定參數用法（手動覆寫與算力調配）
```bash
# 強制指定以繁中 Breeze2 引擎轉錄 (適合中英夾雜、台灣在地時事/科技演講)
./run.sh "https://example.com/audio.mp3" --lang zh

# 強制指定以英文 faster-whisper 引擎轉錄 (適合全英語授課、國際多語研討會)
./run.sh "https://example.com/audio.mp3" --lang en

# 點數精省模式:指定租賃 T4 GPU (預設優先租賃推論極速之 L4 GPU)
./run.sh "https://example.com/audio.mp3" --gpu T4
```

> **模型切換與 GPU 選型指南**:
> - **預設模式(不加參數)**:系統會自動探測語言，繁中自動派送 Breeze2、非中文自動派送 faster-whisper。
> - **何時覆寫 `--lang`？** 若影片標題為英文(例如 `Tech Talk Ep.12`)但內部實為中文演講，或混合語音無法自動判定時，建議明確加上 `--lang zh`。
> - **何時覆寫 `--gpu`？** 系統預設租賃 L4 GPU(推論極速，約 17~20x 即時速度);若 Colab 尖峰時段 L4 配額較緊，或希望進一步精打細算點數開銷，可加上 `--gpu T4` 換取更低點數消耗。

---

## 輸出檔案與 Manifest 規範

轉錄產物會自動儲存於專案根目錄的 `output/` 資料夾下，檔名已進行安全正規化與 UTF-8 200 Bytes 長度截斷:

```
output/
├── sample_chinese_lecture_49min.srt        # SRT 字幕檔 (含精準時間軸)
├── sample_chinese_lecture_49min.txt        # 純文字轉錄稿 (段落重構)
└── sample_chinese_lecture_49min.manifest.json  # 數位簽章與 SHA-256 雜湊驗證檔
```

### Manifest 結構範例
```json
{
  "source_url": "https://drive.google.com/file/d/...",
  "base_name": "sample_chinese_lecture_49min",
  "generated_at": 1727457000,
  "files": {
    "sample_chinese_lecture_49min.srt": {
      "sha256": "4a7b9e...",
      "size": 128450
    },
    "sample_chinese_lecture_49min.txt": {
      "sha256": "8f3c2a...",
      "size": 65120
    }
  }
}
```

---

## 自動化測試與品質保證

本專案配置完整的 Pytest 自動化測試套件，涵蓋快取驗證、語言探測、下載與備援、參數傳遞與腳本信號控制:

```bash
# 執行全量測試 (27 項測試規格)
uv run pytest
```

### 測試覆蓋範疇
- `tests/test_cache.py`:產物快取命中判定、Manifest SHA-256 驗證、壞檔排除與安全檔名處理。
- `tests/test_detect.py`:中繼資料解析、語言分類邏輯、15 秒切片決策分支。
- `tests/test_download.py`:安全檔名長度截斷（200 Bytes）、白名單省略號保留、Path Traversal 防禦。
- `tests/test_sync_artifacts.py`:Staging 暫存下載、原子替換（Atomic Move）、雜湊不符防護。
- `tests/test_transcribe_driver.py`:Base64 + JSON 安全序列化傳參結構檢驗。
- `tests/test_run_sh.py`:POSIX 信號捕捉(SIGINT / SIGTERM / EXIT)、孤兒清理邏輯。

---

## 工業級防禦性設計

每一條防禦規則背後，都是一個真實會發生的失敗場景——不是為了防禦而防禦:

| 潛在威脅與隱患 | 根本原因 | 本系統工程防禦措施 |
| :--- | :--- | :--- |
| **Bash 代碼注入** | Python 以三重引號字串直接拼接 URL 參數 | 改用 **Base64 + JSON 安全序列化** 傳參，代碼與資料完全隔離。 |
| **壞檔假命中** | 快取只看檔名與檔案是否存在 | 強制調用 `verify_manifest` 逐檔比對 **SHA-256 數位雜湊**。 |
| **Linux 檔名崩潰** | 影片長標題超過 ext4 255 位元組上限 | 實裝 **200 UTF-8 Bytes 安全長度截斷**，預留副檔名空間。 |
| **下載中斷毀損** | 遠端直接下載覆蓋本地檔案 | 實裝 **Staging 暫存隔離與原子替換**，驗證失敗絕不替換良品。 |
| **雲端點數偷跑** | 使用者按下 Ctrl+C 或網路中斷 | POSIX `trap` 精確攔截信號，退出時強制觸發 `colab stop`。 |
| **YouTube 429 阻擋** | Colab 資料中心 IP 被 YouTube 風控 | 自動啟用 **住宅 IP 救援機制**，本地無感抓取直傳續推。 |

---

## 資安稽核與隱私保護

本專案在正式開源發布至 GitHub 之前，全面導入紅藍隊視角，由 **OpenAI Codex** 與 **Claude Code（搭配 `security-review` 資安技能）** 進行雙重動態與靜態滲透稽核，達到 **100% 零機密外洩標準**:

| 稽核項目 | 檢查手段與規則 | 實測防護結論 |
| :--- | :--- | :--- |
| **個人識別資訊 (PII)** | 全局掃描電子郵件、電話號碼、個人帳號與身份標識 | ✅ **安全無外露**。僅包含正規開源套件版本號與 CDN 靜態資源。 |
| **API Keys 與憑證** | 檢測 `AIza`、`sk-`、`ghp_`、`AKIA`、PEM 私鑰等機密特徵 | ✅ **安全無外露**。無任何硬編碼金鑰，敏感配置完全依賴本地環境變數。 |
| **開發者路徑脫敏** | 全文檢索 `/Users/`、`/home/`、`C:\Users` 等絕對路徑 | ✅ **安全無外露**。全數改用 `os.path.expanduser` 動態解析與相對路徑。 |
| **雲端連結與測試資料** | 檢驗 Google Drive ID、YouTube 私人連結與真實檔名 | ✅ **安全無外露**。所有測試連結與檔案皆已 Mock 去識別化與佔位符處理。 |
| **Git 歷史完整性** | `git log --all --diff-filter=A` 審查所有曾提交檔名 | ✅ **乾淨無殘留**。單一純淨 Commit 交付，無歷史覆寫前殘留機密。 |
| **邊界防護 (.gitignore)** | 覆蓋 `.env*`、憑證、Token、私鑰與暫存快取 | ✅ **防護完備**。杜絕本機快取與私人 Cookie 不慎上傳風險。 |

---

## 致謝與引用

本專案的核心轉錄引擎，建立在開源社群 **[thc1006](https://github.com/thc1006)** 所開發維護的兩個專案之上:

- **[breezesprint-25](https://github.com/thc1006/breezesprint-25)**:專為台灣繁體中文語境、術語與標點符號最佳化的 Breeze2-Whisper 轉錄專案。
- **[whispersprint](https://github.com/thc1006/whispersprint)**:基於 faster-whisper / CTranslate2 高通量架構的國際多語言轉錄專案。

沒有這兩套模型打下的底子，這個專案能做的就只是排程，不是轉錄。感謝原作者 thc1006 的貢獻。

---

## 專案文檔導覽

- **[產品需求規格書 (PRD.html)](prd.html)**:包含專案經理(PM)、系統分析師(SA)、主任架構師(Tech Lead)視角的完整規劃、容錯狀態機與 FMEA 失效分析。
- **[專案演進歷程 (his.html)](his.html)**:詳細記錄從雙模型探索、YouTube 攻防突破、長音訊全量驗收，到 Codex 與 Claude Opus 雙專家 Review 的工程歷程。
