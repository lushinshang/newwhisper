#!/usr/bin/env python3
"""
遠端 Colab 轉錄推論驅動器 (Remote Colab Transcription Driver)
透過 Jupyter Kernel WSS 直連注入執行。
功能：
1. 自動環境依賴確保 (ffmpeg, yt-dlp, gdown, pydub, JAX/PyTorch/faster-whisper)
2. 具備完全自包含 (Self-contained) 萬用音訊下載與標準化能力 (YouTube / GDrive / HTTP)
3. 分流推論：BreezeSprint-25 (繁中) vs WhisperSprint (英文/多語系)
4. 產生標準 SRT, TXT 與完整性 Manifest
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# =====================================================================
# 1. 遠端環境初始化與依賴檢查
# =====================================================================
def ensure_remote_environment():
    """確保遠端 Colab 環境具備必備 CLI 工具與套件"""
    print("🔧 [Colab 遠端] 正在檢查與準備執行環境...")
    if not shutil.which("ffmpeg"):
        print("📥 正在安裝 ffmpeg...")
        subprocess.run(["apt-get", "update", "-qq"], check=False)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=False)

    pkgs = ["gdown", "pydub", "requests"]
    try:
        import gdown
        import pydub
        import requests
    except ImportError:
        print("📦 正在安裝通用音訊處理套件 (gdown, pydub, requests)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + pkgs, check=False)

    # 強制升級 yt-dlp 至最新版本，確保具備最新 YouTube n-sig / cipher 解密修復能力
    print("📦 正在同步升級遠端 yt-dlp 至最新版本以規避風控...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=False)
    print("✅ 遠端基礎執行環境就緒！")


# =====================================================================
# 2. 獨立萬用音訊前處理 (Self-contained Ingest Pipeline)
# =====================================================================
def is_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return bool(re.search(r"(youtube\.com|youtu\.be)", url))


def is_gdrive_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return "drive.google.com" in url


def extract_gdrive_file_id(url: str) -> str | None:
    if not url or not is_gdrive_url(url):
        return None
    try:
        parsed_url = urlparse(url)
        if "open?id=" in url or "uc?id=" in url:
            return parse_qs(parsed_url.query).get("id", [None])[0]
        elif "/file/d/" in url:
            parts = url.split("/file/d/")[1].split("/")
            return parts[0].split("?")[0]
        return None
    except Exception:
        return None


def parse_source_type(url: str) -> str:
    if not url or not isinstance(url, str):
        return "invalid"
    if not url.startswith(("http://", "https://")):
        return "invalid"
    if is_youtube_url(url):
        return "youtube"
    if is_gdrive_url(url):
        return "gdrive"
    return "direct"


def convert_to_wav(filename: str, output_wav: str | None = None) -> str:
    """將音訊檔案轉換為標準 16kHz 單聲道 16-bit PCM WAV"""
    if filename.lower().endswith(".wav") and (output_wav is None or output_wav == filename):
        return filename

    target_wav = output_wav or f"{os.path.splitext(filename)[0]}.wav"
    try:
        from pydub import AudioSegment

        ext = os.path.splitext(filename)[1].lower().lstrip(".") or "mp3"
        audio = AudioSegment.from_file(filename, format=ext)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(target_wav, format="wav")
        return target_wav
    except Exception:
        # Fallback to direct ffmpeg CLI
        cmd = ["ffmpeg", "-y", "-i", filename, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", target_wav]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return target_wav


def download_from_gdrive(file_id: str, output_dir: str = ".") -> str:
    import gdown

    os.makedirs(output_dir, exist_ok=True)
    existing_files = set(os.listdir(output_dir)) if os.path.exists(output_dir) else set()
    url = f"https://drive.google.com/uc?id={file_id}"
    dest = gdown.download(url, output=output_dir, quiet=False, fuzzy=True)

    if dest and os.path.isdir(dest):
        new_files = [f for f in os.listdir(dest) if f not in existing_files and not f.startswith(".")]
        if new_files:
            dest = os.path.join(dest, new_files[0])
        else:
            all_files = [os.path.join(dest, f) for f in os.listdir(dest) if not f.startswith(".")]
            if all_files:
                dest = max(all_files, key=lambda f: os.path.getmtime(f))

    if not dest or not os.path.exists(dest) or os.path.isdir(dest):
        raise RuntimeError(f"Google Drive 下載失敗，請確認檔案分享權限 (ID: {file_id})")
    return dest


def download_from_youtube(url: str, output_dir: str = ".") -> str:
    from yt_dlp import YoutubeDL

    os.makedirs(output_dir, exist_ok=True)
    out_tmpl = os.path.join(output_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        err_str = str(e)
        print(f"⚠️ [FALLBACK_REQUIRED] YouTube 遠端機房 IP 拉取音訊失敗 ({err_str})，正在觸發本地住宅 IP 救援機制...", flush=True)
        raise


def download_from_url(url: str, output_dir: str = ".") -> str:
    import requests

    os.makedirs(output_dir, exist_ok=True)
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path) or f"audio_{int(time.time())}.mp3"
    target_path = os.path.join(output_dir, filename)

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(target_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return target_path


def process_audio_source(url: str, output_dir: str = ".") -> list[str]:
    """統一音訊前處理：偵測來源 -> 下載原始檔 -> 標準化為 16kHz WAV"""
    stype = parse_source_type(url)
    if stype == "invalid":
        raise ValueError(f"不支援或無效的音訊來源網址: {url}")

    os.makedirs(output_dir, exist_ok=True)
    raw_path = ""
    if stype == "youtube":
        raw_path = download_from_youtube(url, output_dir=output_dir)
    elif stype == "gdrive":
        fid = extract_gdrive_file_id(url)
        if not fid:
            raise ValueError(f"無法從 Google Drive 連結解析檔案 ID: {url}")
        raw_path = download_from_gdrive(fid, output_dir=output_dir)
    elif stype == "direct":
        raw_path = download_from_url(url, output_dir=output_dir)

    if os.path.isdir(raw_path):
        candidates = [os.path.join(raw_path, f) for f in os.listdir(raw_path) if not f.startswith(".")]
        if candidates:
            raw_path = max(candidates, key=lambda f: os.path.getmtime(f))

    wav_path = convert_to_wav(raw_path)
    return [wav_path]


# =====================================================================
# 3. 快取鍵與 Manifest 生成器
# =====================================================================
def normalize_url_key(url: str) -> str:
    if not url:
        return "unknown"
    url_str = url.strip()
    if is_youtube_url(url_str):
        if "youtu.be/" in url_str:
            vid = url_str.split("youtu.be/")[1].split("?")[0].split("&")[0]
            return f"yt_{vid}"
        parsed = urlparse(url_str)
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            return f"yt_{qs['v'][0]}"
        match = re.search(r"v=([a-zA-Z0-9_-]+)", url_str)
        if match:
            return f"yt_{match.group(1)}"
    if is_gdrive_url(url_str):
        fid = extract_gdrive_file_id(url_str)
        if fid:
            return f"gdrive_{fid}"
    parsed = urlparse(url_str)
    base = os.path.basename(parsed.path) or "audio"
    base_safe = re.sub(r"[^a-zA-Z0-9_-]", "_", base)
    url_hash = hashlib.sha256(url_str.encode("utf-8")).hexdigest()[:10]
    return f"direct_{base_safe}_{url_hash}"


MAX_NAME_BYTES = 200  # 保留副檔名空間


def sanitize_title_for_filename(title: str, fallback_key: str = "audio", max_bytes: int = MAX_NAME_BYTES) -> str:
    """清理標題或檔名，去除副檔名並轉化為安全的檔案系統名稱，並嚴格限制 UTF-8 Bytes 長度"""
    if not title:
        return fallback_key
    name, ext = os.path.splitext(title)
    audio_exts = {".mp3", ".wav", ".m4a", ".mp4", ".flac", ".ogg", ".aac", ".webm"}
    if ext.lower() in audio_exts:
        clean_name = name
    else:
        clean_name = title

    import unicodedata
    normalized = unicodedata.normalize("NFC", clean_name)
    safe = re.sub(r'[\x00-\x1f\x7f/\\?*"<>|:]', "_", normalized)
    safe = re.sub(r"\s+", " ", safe).strip(" .")

    raw_bytes = safe.encode("utf-8")
    if len(raw_bytes) > max_bytes:
        safe = raw_bytes[:max_bytes].decode("utf-8", errors="ignore").rstrip(" .")

    return safe or fallback_key


def generate_manifest(
    output_dir: str, url: str, model_name: str, language: str, title: str | None = None
) -> dict:
    target_key = normalize_url_key(url)
    manifest_path = os.path.join(output_dir, f"{target_key}.manifest.json")

    title_base = sanitize_title_for_filename(title, fallback_key=target_key) if title else target_key
    srt_path = os.path.join(output_dir, f"{title_base}.srt")
    txt_path = os.path.join(output_dir, f"{title_base}.txt")

    def file_sha256(path: str) -> str:
        if not os.path.exists(path):
            return ""
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    srt_size = os.path.getsize(srt_path) if os.path.exists(srt_path) else 0
    txt_size = os.path.getsize(txt_path) if os.path.exists(txt_path) else 0
    srt_hash = file_sha256(srt_path)
    txt_hash = file_sha256(txt_path)

    manifest_data = {
        "url": url,
        "cache_key": target_key,
        "key": target_key,
        "title": title_base,
        "model": model_name,
        "model_name": model_name,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "srt_file": os.path.basename(srt_path),
        "srt_sha256": srt_hash,
        "txt_file": os.path.basename(txt_path),
        "txt_sha256": txt_hash,
        "files": {
            "srt": {
                "name": os.path.basename(srt_path),
                "size": srt_size,
                "sha256": srt_hash,
            },
            "txt": {
                "name": os.path.basename(txt_path),
                "size": txt_size,
                "sha256": txt_hash,
            },
        },
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
    return manifest_data


def format_srt_time(seconds: float) -> str:
    """轉換秒數為標準 SRT 時間戳記 (HH:MM:SS,mmm)"""
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_srt_content(segments: list[dict]) -> str:
    """將片段轉為標準 SRT 字幕字串"""
    cues = []
    for idx, seg in enumerate(segments, start=1):
        start_str = format_srt_time(seg["start"])
        end_str = format_srt_time(seg["end"])
        text = seg["text"].strip()
        cues.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    return "\n".join(cues)


# =====================================================================
# 4. 轉錄主控流程
# =====================================================================
def run_transcription(audio_url: str, engine_type: str, output_dir: str = "/content/output") -> dict:
    """執行完整雲端轉錄流程"""
    ensure_remote_environment()
    os.makedirs(output_dir, exist_ok=True)
    work_dir = "/content"

    # 1. 萬用下載並轉碼音訊 (支援本地預載直傳)
    preloaded = os.environ.get("TRANSCRIPTION_PRELOADED_AUDIO")
    if preloaded and os.path.exists(preloaded):
        print(f"📦 [Colab 遠端] 檢測到本地預載音訊，直接使用: {preloaded}")
        target_wav = convert_to_wav(preloaded)
    else:
        print(f"📥 [Colab 遠端] 正在拉取音訊來源: {audio_url}")
        wav_files = process_audio_source(audio_url, output_dir=os.path.join(work_dir, "audio_staging"))
        if not wav_files or not os.path.exists(wav_files[0]):
            raise RuntimeError("無法在遠端順利下載並轉檔音訊！")
        target_wav = wav_files[0]

    print(f"✅ 音訊已成功轉碼為標準 WAV: {target_wav} ({os.path.getsize(target_wav)} bytes)")

    # 2. 依指定引擎載入轉錄專案
    print(f"🧠 [Colab 遠端] 啟動推論引擎: {engine_type}...")
    segments = []

    if engine_type == "breezesprint25":
        repo_dir = "/content/breezesprint-25"
        if not os.path.exists(repo_dir):
            print("🚀 正在複製 BreezeSprint-25 原始碼...")
            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/thc1006/breezesprint-25.git", repo_dir],
                check=True,
            )
        sys.path.insert(0, os.path.join(repo_dir, "src"))

        try:
            import breezesprint25

            print("⚡ 載入 BreezeSprint-25 繁中核心模組...")
            if hasattr(breezesprint25, "transcribe_file"):
                segments = breezesprint25.transcribe_file(target_wav)
            else:
                raise NotImplementedError("使用相容管線處理")
        except Exception as e:
            print(f"ℹ️ BreezeSprint 引擎載入提示: {e}，啟用高效能繁中 ASR 保底管線...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper"], check=False)
            from faster_whisper import WhisperModel

            # 若有 GPU 優先使用 float16，TPU 或 CPU 則使用 int8
            device = "cuda" if shutil.which("nvidia-smi") else "cpu"
            compute = "float16" if device == "cuda" else "int8"
            print(f"⚡ 啟動 Faster-Whisper large-v3 ({device}, {compute})...")
            model = WhisperModel("large-v3", device=device, compute_type=compute)
            raw_segs, info = model.transcribe(
                target_wav, language="zh", initial_prompt="繁體中文，台灣用語，科技與軟體工程。"
            )
            print(f"🎙️ [即時串流] 開始繁中語音轉錄 (總時長: {info.duration:.1f} 秒)...", flush=True)
            for s in raw_segs:
                seg = {"start": s.start, "end": s.end, "text": s.text}
                segments.append(seg)
                pct = min(100.0, (s.end / info.duration * 100)) if info.duration > 0 else 0
                print(f"[{format_srt_time(s.start)} --> {format_srt_time(s.end)}] ({pct:5.1f}%) {s.text.strip()}", flush=True)

    else:
        # WhisperSprint 國際英文/多語系引擎
        repo_dir = "/content/whispersprint"
        if not os.path.exists(repo_dir):
            print("🚀 正在複製 WhisperSprint 原始碼...")
            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/thc1006/whispersprint.git", repo_dir],
                check=True,
            )
        sys.path.insert(0, os.path.join(repo_dir, "src"))

        try:
            import whispersprint

            print("⚡ 載入 WhisperSprint 國際核心模組...")
            if hasattr(whispersprint, "transcribe_file"):
                segments = whispersprint.transcribe_file(target_wav)
            else:
                raise NotImplementedError("使用相容管線處理")
        except Exception as e:
            print(f"ℹ️ WhisperSprint 引擎載入提示: {e}，啟用 Faster-Whisper 多語系管線...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper"], check=False)
            from faster_whisper import WhisperModel

            device = "cuda" if shutil.which("nvidia-smi") else "cpu"
            compute = "float16" if device == "cuda" else "int8"
            print(f"⚡ 啟動 Faster-Whisper large-v3 ({device}, {compute})...")
            model = WhisperModel("large-v3", device=device, compute_type=compute)
            raw_segs, info = model.transcribe(target_wav, language="en")
            print(f"🎙️ [即時串流] 開始多語系語音轉錄 (總時長: {info.duration:.1f} 秒)...", flush=True)
            for s in raw_segs:
                seg = {"start": s.start, "end": s.end, "text": s.text}
                segments.append(seg)
                pct = min(100.0, (s.end / info.duration * 100)) if info.duration > 0 else 0
                print(f"[{format_srt_time(s.start)} --> {format_srt_time(s.end)}] ({pct:5.1f}%) {s.text.strip()}", flush=True)

    # 3. 產出標準化字幕檔與純文字 (支援以影音檔名/標題命名)
    cache_key = normalize_url_key(audio_url)
    custom_title = os.environ.get("TRANSCRIPTION_TITLE") or ""
    title_base = sanitize_title_for_filename(custom_title, fallback_key=cache_key) if custom_title else cache_key

    srt_file = os.path.join(output_dir, f"{title_base}.srt")
    txt_file = os.path.join(output_dir, f"{title_base}.txt")

    srt_content = generate_srt_content(segments)
    txt_content = "\n".join(seg["text"].strip() for seg in segments if seg["text"].strip())

    with open(srt_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(txt_content)

    # 4. 生成 Manifest
    lang_code = "zh" if engine_type == "breezesprint25" else "en"
    manifest = generate_manifest(
        output_dir=output_dir,
        url=audio_url,
        model_name=engine_type,
        language=lang_code,
        title=custom_title or title_base,
    )

    print("==================================================")
    print("🎉 [TRANSCRIPTION_COMPLETED]")
    print(f"SRT: {srt_file} ({len(segments)} 個片段)")
    print(f"TXT: {txt_file}")
    print(f"Manifest: {json.dumps(manifest, ensure_ascii=False)}")
    print("==================================================")
    return manifest


if __name__ == "__main__":
    url_arg = os.environ.get("TRANSCRIPTION_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    engine_arg = os.environ.get("TRANSCRIPTION_ENGINE") or (sys.argv[2] if len(sys.argv) > 2 else "breezesprint25")
    out_arg = os.environ.get("TRANSCRIPTION_OUTPUT") or "/content/output"

    if not url_arg:
        print("❌ 錯誤：未提供音訊網址！")
        sys.exit(1)

    run_transcription(url_arg, engine_arg, out_arg)
