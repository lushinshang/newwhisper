#!/usr/bin/env bash
# =====================================================================
# Colab Dual ASR 智慧語音轉錄雙引擎分流排程系統 (run.sh)
# 特性：
# 1. 快取前置命中 (Cache-First) 秒級交付，0 雲端開銷
# 2. agy cli 方案 C 語言探測與智慧分流 (BreezeSprint-25 vs WhisperSprint)
# 3. Google AI Pro 算力漸進式降級 (TPU v5e-1 -> L4 -> T4 -> CPU)
# 4. 孤兒會話 (Orphan Session) 自動對帳清理與防禦性 trap 退出保障
# =====================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${NEWWHISPER_OUTPUT_DIR:-${SCRIPT_DIR}/output}"
mkdir -p "$OUTPUT_DIR"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=====================================================================${NC}"
echo -e "${CYAN}       Colab Dual ASR 智慧語音轉錄雙引擎分流系統 v1.0.0               ${NC}"
echo -e "${CYAN}=====================================================================${NC}"

# 1. 檢查 uv 環境
if ! command -v uv &> /dev/null; then
    echo -e "${RED}❌ 錯誤：本地未安裝 uv 套件管理器！請先安裝: brew install uv${NC}"
    exit 1
fi

# 2. 取得音訊 URL
URL="$1"
if [ -z "$URL" ]; then
    echo ""
    echo -e "${YELLOW}請輸入音訊來源網址 (支援 YouTube / Google Drive / HTTP 直連影音):${NC}"
    read -r -p "🔗 URL: " URL
fi

if [ -z "$URL" ]; then
    echo -e "${RED}❌ 錯誤：未輸入有效網址！${NC}"
    exit 1
fi

# 4. 方案 C 語言與標題探測
echo ""
echo -e "${BLUE}🌐 [語言探測] 正在執行方案 C 混合語系與標題分析...${NC}"
DETECT_RESULT=$(uv run --directory "$SCRIPT_DIR" python3 -c "
import sys, json
from scripts.detect_language import detect_language_scheme_c
res = detect_language_scheme_c(sys.argv[1])
print(json.dumps(res, ensure_ascii=False))
" "$URL")

DETECTED_LANG=$(echo "$DETECT_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('language', 'zh'))")
TITLE=$(echo "$DETECT_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', ''))")

TITLE_BASE=$(uv run --directory "$SCRIPT_DIR" python3 -c "
import sys
from scripts.cache_manager import sanitize_title_for_filename, normalize_url_key
url = sys.argv[1]
raw_title = sys.argv[2]
key = normalize_url_key(url)
print(sanitize_title_for_filename(raw_title, fallback_key=key))
" "$URL" "$TITLE")

echo -e "📌 影音標題: ${YELLOW}${TITLE}${NC}"

# 5. 快取前置檢查 (Cache-First)
echo ""
echo -e "${BLUE}⚡ [快取檢驗] 正在檢查本地快取指紋...${NC}"
CACHE_HIT=$(uv run --directory "$SCRIPT_DIR" python3 -c "
import sys
from scripts.cache_manager import is_cache_hit, get_cache_file_paths, normalize_url_key
url = sys.argv[1]
out_dir = sys.argv[2]
raw_title = sys.argv[3]
if is_cache_hit(url, out_dir, title=raw_title):
    srt, txt, _ = get_cache_file_paths(url, out_dir, title=raw_title)
    print('HIT|' + srt + '|' + txt)
else:
    print('MISS|' + normalize_url_key(url))
" "$URL" "$OUTPUT_DIR" "$TITLE")

STATUS=$(echo "$CACHE_HIT" | cut -d'|' -f1)
if [ "$STATUS" = "HIT" ]; then
    SRT_PATH=$(echo "$CACHE_HIT" | cut -d'|' -f2)
    TXT_PATH=$(echo "$CACHE_HIT" | cut -d'|' -f3)
    echo -e "${GREEN}🎉 [快取秒級命中] 偵測到本地已存在完整轉錄產物！${NC}"
    echo -e "${GREEN}💡 略過雲端算力請求，0 點數消耗，直接交付：${NC}"
    echo -e "   📄 SRT 字幕: ${CYAN}${SRT_PATH}${NC}"
    echo -e "   📄 TXT 文字: ${CYAN}${TXT_PATH}${NC}"
    exit 0
fi

CACHE_KEY=$(echo "$CACHE_HIT" | cut -d'|' -f2)
echo -e "ℹ️ 快取未命中 (Key: ${CACHE_KEY})，啟動轉錄管線..."

# 孤兒會話防禦性對帳與清理 (僅在快取未命中、準備使用雲端資源時執行)
echo -e "${BLUE}🔍 [啟動檢查] 正在掃描是否存在未釋放的孤兒會話...${NC}"
ORPHAN_SESSIONS=$(uv run --directory "$SCRIPT_DIR" colab sessions 2>/dev/null | grep -oE '\[newwhisper-[^]]+\]' | tr -d '[]' || true)
if [ -n "$ORPHAN_SESSIONS" ]; then
    echo -e "${YELLOW}⚠️ 偵測到殘留的孤兒會話，正在主動清理以停止雲端計費...${NC}"
    for s in $ORPHAN_SESSIONS; do
        echo -e "  - 正在停止會話: $s"
        uv run --directory "$SCRIPT_DIR" colab stop -s "$s" > /dev/null 2>&1 || true
    done
    echo -e "${GREEN}✅ 孤兒會話清理完畢！${NC}"
fi

if [ "$DETECTED_LANG" = "zh" ]; then
    ENGINE="breezesprint25"
    ENGINE_DESC="🇹🇼 BreezeSprint-25 (繁體中文最佳化)"
else
    ENGINE="whispersprint"
    ENGINE_DESC="🇺🇸 WhisperSprint (英文/多語系通用)"
fi

echo -e "🎯 系統判定語系: ${GREEN}${DETECTED_LANG}${NC} → 預計分流至: ${CYAN}${ENGINE_DESC}${NC}"

# 互動確認視窗 (5 秒超時自動前進)
echo -e "${YELLOW}⏱️  5 秒內可按 [c] 強制中文，按 [e] 強制英文，或直接 [Enter] 依判定前進...${NC}"
USER_OVERRIDE=""
if [ -t 0 ]; then
    read -t 5 -n 1 -r USER_OVERRIDE || true
    echo ""
fi

if [ "$USER_OVERRIDE" = "c" ] || [ "$USER_OVERRIDE" = "C" ]; then
    ENGINE="breezesprint25"
    echo -e "${GREEN}👉 已由使用者手動切換為: BreezeSprint-25 (繁中)${NC}"
elif [ "$USER_OVERRIDE" = "e" ] || [ "$USER_OVERRIDE" = "E" ]; then
    ENGINE="whispersprint"
    echo -e "${GREEN}👉 已由使用者手動切換為: WhisperSprint (英文)${NC}"
else
    echo -e "🚀 5 秒超時或確認，依系統判定自動啟動: ${ENGINE_DESC}"
fi

# 6. 雲端算力配置 (L4 -> T4 -> TPU -> CPU 降級狀態機)
SESSION_NAME="newwhisper-$(date +%s)-$RANDOM"
echo ""
echo -e "${BLUE}☁️  [雲端租賃] 正在為會話 [${SESSION_NAME}] 配置硬體加速器...${NC}"

CLEANED=false
LOG_PIPE=""

cleanup_vm() {
    if [ "$CLEANED" = true ]; then
        return
    fi
    CLEANED=true
    if [ "$ALLOCATED" = true ]; then
        echo ""
        echo -e "${YELLOW}🛑 [安全防護] 正在釋放雲端虛擬機 [${SESSION_NAME}]...${NC}"
        uv run --directory "$SCRIPT_DIR" colab stop -s "$SESSION_NAME" > /dev/null 2>&1 || true
        echo -e "${GREEN}✅ 雲端運算資源已安全釋放，杜絕閒置燃燒點數。${NC}"
    fi
    rm -rf "${SCRIPT_DIR}/output/.staging" 2>/dev/null || true
    if [ -n "$LOG_PIPE" ] && [ -f "$LOG_PIPE" ]; then
        rm -f "$LOG_PIPE" 2>/dev/null || true
    fi
}

handle_int() {
    trap - INT EXIT
    cleanup_vm
    exit 130
}

handle_term() {
    trap - TERM EXIT
    cleanup_vm
    exit 143
}

trap handle_int INT
trap handle_term TERM
trap cleanup_vm EXIT

ALLOCATED=false

# 優先嘗試 L4 GPU (Google AI Pro 專屬 24GB VRAM 極速 Tensor Core 推論)
echo -e "🚀 [1/4] 嘗試配置 L4 GPU (24GB VRAM)..."
if uv run --directory "$SCRIPT_DIR" colab new -s "$SESSION_NAME" --gpu L4 2>/dev/null; then
    echo -e "${GREEN}✅ 成功取得 L4 GPU (24GB VRAM)！推論速度預計提升 30 倍！${NC}"
    ALLOCATED=true
else
    echo -e "⚠️ L4 GPU 不可用，嘗試降級至標準 T4 GPU (16GB VRAM)..."
    if uv run --directory "$SCRIPT_DIR" colab new -s "$SESSION_NAME" --gpu T4 2>/dev/null; then
        echo -e "${GREEN}✅ 成功取得 T4 GPU (16GB VRAM)！${NC}"
        ALLOCATED=true
    else
        echo -e "⚠️ T4 GPU 不可用，嘗試配置 TPU v5e-1..."
        if uv run --directory "$SCRIPT_DIR" colab new -s "$SESSION_NAME" --tpu v5e1 2>/dev/null; then
            echo -e "${GREEN}✅ 成功取得 TPU v5e-1 加速器！${NC}"
            ALLOCATED=true
        else
            echo -e "⚠️ 無可用 GPU/TPU，改用 CPU 執行..."
            if uv run --directory "$SCRIPT_DIR" colab new -s "$SESSION_NAME" 2>/dev/null; then
                echo -e "${YELLOW}⚠️ 已取得 CPU 虛擬機 (推論速度較慢)。${NC}"
                ALLOCATED=true
            fi
        fi
    fi
fi

if [ "$ALLOCATED" = false ]; then
    echo -e "${RED}❌ 錯誤：無法在 Colab 上建立或配置虛擬機，請檢查網路或 Google 授權！${NC}"
    exit 1
fi

# 7. 自適應推論驅動執行 (遠端優先，若遇 Bot 攔截自動本地救援)
echo ""
echo -e "${BLUE}🚀 [推論執行] 正在注入轉錄管線並串流遠端日誌...${NC}"

build_env_inject() {
    local url="$1"
    local engine="$2"
    local title="$3"
    local preloaded="${4:-}"
    local b64_payload
    b64_payload=$(uv run --directory "$SCRIPT_DIR" python3 -c "
import json, sys, base64
payload = {
    'TRANSCRIPTION_URL': sys.argv[1],
    'TRANSCRIPTION_ENGINE': sys.argv[2],
    'TRANSCRIPTION_OUTPUT': '/content/output',
    'TRANSCRIPTION_TITLE': sys.argv[3],
    'TRANSCRIPTION_PRELOADED_AUDIO': sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else ''
}
filtered = {k: v for k, v in payload.items() if v}
print(base64.b64encode(json.dumps(filtered).encode('utf-8')).decode('ascii'))
" "$url" "$engine" "$title" "$preloaded")
    echo "import os, json, base64; os.environ.update(json.loads(base64.b64decode('$b64_payload').decode('utf-8')));"
}

EXEC_SCRIPT="${SCRIPT_DIR}/scripts/run_transcribe.py"
ENV_INJECT=$(build_env_inject "$URL" "$ENGINE" "$TITLE_BASE")

LOG_PIPE=$(mktemp)
set +e
{ echo "$ENV_INJECT"; cat "$EXEC_SCRIPT"; } | uv run --directory "$SCRIPT_DIR" colab exec -s "$SESSION_NAME" --timeout 3600 2>&1 | tee "$LOG_PIPE"
EXEC_STATUS=${PIPESTATUS[1]}
set -e

# 若遠端觸發 Bot 檢測攔截，自動啟用本地住宅網路極速救援直傳
if [ $EXEC_STATUS -ne 0 ] && grep -qE "BOT_DETECTED|Sign in to confirm you’re not a bot" "$LOG_PIPE"; then
    echo ""
    echo -e "${YELLOW}⚠️ [自適應機制] 偵測到雲端機房 IP 遭遇 YouTube Bot 攔截，立即無縫啟動本地住宅網路救援直傳...${NC}"
    LOCAL_STAGING="${SCRIPT_DIR}/output/.staging"
    mkdir -p "$LOCAL_STAGING"
    PRELOAD_WAV=$(uv run --directory "$SCRIPT_DIR" python3 -c "
import sys
from scripts.universal_download import process_audio_source
wavs = process_audio_source(sys.argv[1], output_dir='$LOCAL_STAGING')
print(wavs[0])
" "$URL")
    echo -e "${GREEN}✅ 本地音訊已就緒，正在直傳至雲端會話 [${SESSION_NAME}]...${NC}"
    uv run --directory "$SCRIPT_DIR" colab upload -s "$SESSION_NAME" "$PRELOAD_WAV" "content/audio_staging/input.wav"
    
    echo -e "${BLUE}🚀 [接力推論] 音訊直傳完畢，重啟遠端 GPU 推論管線...${NC}"
    ENV_INJECT=$(build_env_inject "$URL" "$ENGINE" "$TITLE_BASE" "/content/audio_staging/input.wav")
    { echo "$ENV_INJECT"; cat "$EXEC_SCRIPT"; } | uv run --directory "$SCRIPT_DIR" colab exec -s "$SESSION_NAME" --timeout 3600
fi
rm -f "$LOG_PIPE"

# 8. 同步產物回本地
echo ""
echo -e "${BLUE}📦 [產物回傳] 正在同步遠端字幕與 Manifest...${NC}"
SYNC_OK=false
if uv run --directory "$SCRIPT_DIR" python3 "${SCRIPT_DIR}/scripts/sync_artifacts.py" "$SESSION_NAME" "$CACHE_KEY" "$OUTPUT_DIR" "$TITLE_BASE"; then
    SYNC_OK=true
fi

if [ "$SYNC_OK" = true ]; then
    echo ""
    echo -e "${GREEN}=====================================================================${NC}"
    echo -e "${GREEN}🎉 語音轉錄任務圓滿完成！產物已成功落地：${NC}"
    echo -e "   📄 字幕檔案 (SRT): ${CYAN}${OUTPUT_DIR}/${TITLE_BASE}.srt${NC}"
    echo -e "   📄 純文字檔 (TXT): ${CYAN}${OUTPUT_DIR}/${TITLE_BASE}.txt${NC}"
    echo -e "   📋 驗證清單 (JSON): ${CYAN}${OUTPUT_DIR}/${CACHE_KEY}.manifest.json${NC}"
    echo -e "${GREEN}=====================================================================${NC}"
    exit 0
else
    echo -e "${RED}❌ 轉錄產物同步或 Manifest 驗證失敗，請檢查上方雲端執行日誌。${NC}"
    exit 1
fi
