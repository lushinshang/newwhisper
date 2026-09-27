#!/usr/bin/env python3
"""
統一音訊前處理引擎 (Universal Audio Ingest Engine)
支援來源：YouTube、Google Drive、HTTP(S) 直連音訊
功能：URL 解析、多來源下載、標準 WAV 格式轉碼
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


def is_youtube_url(url: str) -> bool:
    """檢查是否為 YouTube 連結"""
    if not url or not isinstance(url, str):
        return False
    youtube_regex = r"(youtube\.com|youtu\.be)"
    return bool(re.search(youtube_regex, url))


def is_gdrive_url(url: str) -> bool:
    """檢查是否為 Google Drive 連結"""
    if not url or not isinstance(url, str):
        return False
    return "drive.google.com" in url


def extract_gdrive_file_id(url: str) -> str | None:
    """從 Google Drive 連結中提取檔案 ID (支援 open?id=, /file/d/, uc?id= 等格式)"""
    if not url or not is_gdrive_url(url):
        return None
    try:
        parsed_url = urlparse(url)
        # 格式 1: open?id=FILE_ID
        if "open?id=" in url:
            return parse_qs(parsed_url.query).get("id", [None])[0]
        # 格式 2: /file/d/FILE_ID/...
        elif "/file/d/" in url:
            parts = url.split("/file/d/")[1].split("/")
            return parts[0].split("?")[0]
        # 格式 3: uc?id=FILE_ID
        elif "id=" in url:
            return parse_qs(parsed_url.query).get("id", [None])[0]
        return None
    except Exception:
        return None


def parse_source_type(url: str) -> str:
    """辨識音訊來源類型：youtube, gdrive, direct, invalid"""
    if not url or not isinstance(url, str):
        return "invalid"
    if not url.startswith(("http://", "https://")):
        return "invalid"
    if is_youtube_url(url):
        return "youtube"
    if is_gdrive_url(url):
        return "gdrive"
    return "direct"


def extract_filename_from_cd(content_disposition: str | None) -> str | None:
    """從 Content-Disposition 標頭解析檔案名稱"""
    if not content_disposition:
        return None
    # 支援 filename="abc.mp3" 或 filename=abc.mp3
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, re.IGNORECASE)
    if match:
        name = match.group(1).strip('"\'; ')
        return os.path.basename(name)
    return None


def normalize_audio_extension(content_type: str | None) -> str | None:
    """從 Content-Type 對應標準音訊副檔名"""
    if not content_type:
        return None
    ct = content_type.lower()
    if "audio/mp4" in ct:
        return ".m4a"
    if "audio/mpeg" in ct or "audio/mp3" in ct:
        return ".mp3"
    if "video/mp4" in ct:
        return ".mp4"
    if "audio/wav" in ct or "audio/x-wav" in ct:
        return ".wav"
    if "audio/ogg" in ct or "audio/webm" in ct:
        return ".ogg"
    if "audio/aac" in ct:
        return ".aac"
    return None


def convert_to_wav(filename: str, output_wav: str | None = None) -> str:
    """將音訊檔案強制轉換為標準 16kHz, 單聲道, 16-bit PCM WAV (ASR 最佳格式)"""
    target_wav = output_wav or f"{os.path.splitext(filename)[0]}.16k.wav"
    same_file = os.path.abspath(filename) == os.path.abspath(target_wav)
    actual_target = f"{target_wav}.tmp.wav" if same_file else target_wav

    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", filename, "-vn", "-map", "0:a:0",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", actual_target
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(actual_target) or os.path.getsize(actual_target) <= 44:
        try:
            from pydub import AudioSegment
            ext = os.path.splitext(filename)[1].lower().lstrip(".") or "mp3"
            audio = AudioSegment.from_file(filename, format=ext)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            audio.export(actual_target, format="wav")
        except Exception as e:
            err = res.stderr.strip() if res.returncode != 0 else str(e)
            raise RuntimeError(f"音訊轉檔至 16kHz PCM WAV 失敗: {err}")

    if same_file:
        os.replace(actual_target, target_wav)

    return target_wav


def download_from_gdrive(file_id: str, output_dir: str = ".") -> str:
    """從 Google Drive 下載檔案 (使用 gdown fuzzy 模式)"""
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


def download_from_url(url: str, output_dir: str = ".") -> str:
    """從一般 HTTP(S) 網址串流下載檔案"""
    os.makedirs(output_dir, exist_ok=True)
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)

    # 若 URL path 無有效檔名，發送 HEAD 請求探測
    if not filename or "." not in filename:
        try:
            head = requests.head(url, allow_redirects=True, timeout=10)
            cd = head.headers.get("Content-Disposition")
            filename = extract_filename_from_cd(cd)
            if not filename:
                ext = normalize_audio_extension(head.headers.get("Content-Type")) or ".mp3"
                filename = f"audio_{int(time.time())}{ext}"
        except Exception:
            filename = f"audio_{int(time.time())}.mp3"

    target_path = os.path.join(output_dir, filename)
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    with open(target_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=16384):
            if chunk:
                f.write(chunk)
    return target_path


def download_from_youtube(video_url: str, output_dir: str = ".") -> list[str]:
    """從 YouTube 下載最佳音訊軌並自動透過 ffmpeg 轉換為 16kHz WAV"""
    from yt_dlp import YoutubeDL

    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "extractaudio": True,
        "audioformat": "wav",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        title = info.get("title", f"yt_{int(time.time())}")
        # 清理潛在特殊字元
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        # 尋找輸出之 wav 檔案
        candidate = os.path.join(output_dir, f"{title}.wav")
        if os.path.exists(candidate):
            return [candidate]
        # 遍歷目錄尋找相符檔案
        for f in Path(output_dir).glob("*.wav"):
            if title in f.name:
                return [str(f)]
        return [candidate]


def process_audio_source(url: str, output_dir: str = ".") -> list[str]:
    """總協調入口：解析來源並輸出標準 WAV 檔案清單"""
    stype = parse_source_type(url)
    if stype == "youtube":
        return download_from_youtube(url, output_dir)
    elif stype == "gdrive":
        fid = extract_gdrive_file_id(url)
        if not fid:
            raise ValueError(f"無效的 Google Drive 連結: {url}")
        raw = download_from_gdrive(fid, output_dir)
        wav = convert_to_wav(raw)
        return [wav]
    elif stype == "direct":
        raw = download_from_url(url, output_dir)
        wav = convert_to_wav(raw)
        return [wav]
    else:
        raise ValueError(f"不支援的音訊網址格式: {url}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python universal_download.py <URL> [output_dir]")
        sys.exit(1)
    target_url = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    print(f"🚀 開始處理音訊來源: {target_url}")
    results = process_audio_source(target_url, out_dir)
    print(f"✅ 處理完成，產出 WAV: {results}")
