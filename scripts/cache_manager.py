#!/usr/bin/env python3
"""
快取與 Manifest 管理模組 (Cache & Manifest Manager)
功能：URL 正規化、快取指紋比對、秒級命中檢驗、Manifest 產生與完整性驗證
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.universal_download import extract_gdrive_file_id, is_gdrive_url, is_youtube_url


def normalize_url_key(url: str) -> str:
    """將不同形式的 URL 正規化為唯一且安全的快取鍵 (Cache Key)"""
    if not url:
        return "unknown"

    url_str = url.strip()

    # YouTube: 提取唯一 Video ID
    if is_youtube_url(url_str):
        # 匹配 youtu.be/ID
        if "youtu.be/" in url_str:
            vid = url_str.split("youtu.be/")[1].split("?")[0].split("&")[0]
            return f"yt_{vid}"
        # 匹配 watch?v=ID
        parsed = urlparse(url_str)
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            return f"yt_{qs['v'][0]}"
        # 其他 youtube URL 匹配
        match = re.search(r"v=([a-zA-Z0-9_-]+)", url_str)
        if match:
            return f"yt_{match.group(1)}"

    # Google Drive: 提取 File ID
    if is_gdrive_url(url_str):
        fid = extract_gdrive_file_id(url_str)
        if fid:
            return f"gdrive_{fid}"

    # 一般 HTTP 直連網址：取網址核心路徑加上 sha256 摘要前 10 碼
    parsed = urlparse(url_str)
    base = os.path.basename(parsed.path) or "audio"
    base_safe = re.sub(r"[^a-zA-Z0-9_-]", "_", base)
    url_hash = hashlib.sha256(url_str.encode("utf-8")).hexdigest()[:10]
    return f"direct_{base_safe}_{url_hash}"


MAX_NAME_BYTES = 200  # 保留副檔名 .manifest.json 與後綴空間


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

    # Unicode NFC 正規化
    import unicodedata
    normalized = unicodedata.normalize("NFC", clean_name)

    # 移除或取代作業系統非法字元: \ / : * ? " < > | 及控制字元
    safe = re.sub(r'[\x00-\x1f\x7f/\\?*"<>|:]', "_", normalized)
    safe = re.sub(r"\s+", " ", safe).strip(" .")

    # 針對 UTF-8 Bytes 進行安全限長，避免切在多字節中間
    raw_bytes = safe.encode("utf-8")
    if len(raw_bytes) > max_bytes:
        safe = raw_bytes[:max_bytes].decode("utf-8", errors="ignore").rstrip(" .")

    return safe or fallback_key


def get_cache_file_paths(
    url: str, output_dir: str = "output", title: str | None = None
) -> tuple[str, str, str]:
    """取得對應 URL 在 output 目錄下的 (srt_path, txt_path, manifest_path)"""
    os.makedirs(output_dir, exist_ok=True)
    key = normalize_url_key(url)
    manifest_path = os.path.join(output_dir, f"{key}.manifest.json")

    # 1. 優先檢查是否已有 manifest 記錄真實檔名
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                mdata = json.load(f)
                srt_name = mdata.get("srt_file") or (mdata.get("files", {}).get("srt", {}).get("name"))
                txt_name = mdata.get("txt_file") or (mdata.get("files", {}).get("txt", {}).get("name"))
                if srt_name and txt_name:
                    srt_p = os.path.join(output_dir, srt_name)
                    txt_p = os.path.join(output_dir, txt_name)
                    if os.path.exists(srt_p) and os.path.exists(txt_p):
                        return srt_p, txt_p, manifest_path
        except Exception:
            pass

    # 2. 若傳入 title，優先以 title 產生安全檔名
    if title:
        title_base = sanitize_title_for_filename(title, fallback_key=key)
        srt_path = os.path.join(output_dir, f"{title_base}.srt")
        txt_path = os.path.join(output_dir, f"{title_base}.txt")
        return srt_path, txt_path, manifest_path

    # 3. 預設以 key 作為檔名基礎
    srt_path = os.path.join(output_dir, f"{key}.srt")
    txt_path = os.path.join(output_dir, f"{key}.txt")
    return srt_path, txt_path, manifest_path


def compute_sha256(path: str) -> str:
    """計算指定檔案的 SHA-256 二進位雜湊值"""
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_manifest(
    output_dir: str,
    url: str,
    model_name: str,
    language: str,
    duration_sec: float | None = None,
    key: str | None = None,
    title: str | None = None,
) -> dict:
    """產生轉錄結果 Manifest 驗證清單"""
    target_key = key or normalize_url_key(url)
    manifest_path = os.path.join(output_dir, f"{target_key}.manifest.json")

    title_base = sanitize_title_for_filename(title, fallback_key=target_key) if title else target_key
    srt_path = os.path.join(output_dir, f"{title_base}.srt")
    txt_path = os.path.join(output_dir, f"{title_base}.txt")

    srt_size = os.path.getsize(srt_path) if os.path.exists(srt_path) else 0
    txt_size = os.path.getsize(txt_path) if os.path.exists(txt_path) else 0
    srt_hash = compute_sha256(srt_path)
    txt_hash = compute_sha256(txt_path)

    manifest_data = {
        "url": url,
        "key": target_key,
        "cache_key": target_key,
        "title": title_base,
        "model": model_name,
        "model_name": model_name,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "duration_sec": duration_sec,
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


def verify_manifest(manifest_path: str) -> bool:
    """驗證 Manifest 與實際檔案的完整性與 SHA-256 雜湊值"""
    if not os.path.exists(manifest_path):
        return False
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        dir_name = os.path.abspath(os.path.dirname(manifest_path))

        def is_safe_relpath(fname: str) -> bool:
            if not fname or os.path.isabs(fname):
                return False
            # 防止路徑越界
            target_p = os.path.abspath(os.path.join(dir_name, fname))
            return os.path.commonpath([dir_name, target_p]) == dir_name

        # 模式 1: 具備 files 嵌套結構
        if "files" in data and isinstance(data["files"], dict):
            for ftype in ("srt", "txt"):
                meta = data["files"].get(ftype)
                if not meta or not isinstance(meta, dict):
                    return False
                fname = meta.get("name")
                if not fname or not is_safe_relpath(fname):
                    return False
                fpath = os.path.join(dir_name, fname)
                if not os.path.exists(fpath) or os.path.getsize(fpath) == 0:
                    return False
                if "size" in meta and meta["size"] > 0 and os.path.getsize(fpath) != meta["size"]:
                    return False
                # 實體 SHA-256 雜湊嚴格比對
                expected_hash = meta.get("sha256")
                if expected_hash:
                    actual_hash = compute_sha256(fpath)
                    if actual_hash.lower() != expected_hash.lower():
                        return False
            return True

        # 模式 2: 扁平欄位結構 (srt_file, txt_file)
        if "srt_file" in data and "txt_file" in data:
            srt_name = data["srt_file"]
            txt_name = data["txt_file"]
            if not is_safe_relpath(srt_name) or not is_safe_relpath(txt_name):
                return False
            srt_p = os.path.join(dir_name, srt_name)
            txt_p = os.path.join(dir_name, txt_name)
            if not os.path.exists(srt_p) or not os.path.exists(txt_p):
                return False
            if os.path.getsize(srt_p) < 10 or os.path.getsize(txt_p) < 2:
                return False
            # 比對 SHA-256
            if "srt_sha256" in data and data["srt_sha256"]:
                if compute_sha256(srt_p).lower() != data["srt_sha256"].lower():
                    return False
            if "txt_sha256" in data and data["txt_sha256"]:
                if compute_sha256(txt_p).lower() != data["txt_sha256"].lower():
                    return False
            return True
        return False
    except Exception:
        return False


def is_cache_hit(url: str, output_dir: str = "output", title: str | None = None) -> bool:
    """檢查本地快取是否命中 (必須具備完整且通過 SHA-256 驗證之 Manifest)"""
    key = normalize_url_key(url)
    manifest_path = os.path.join(output_dir, f"{key}.manifest.json")
    if not os.path.exists(manifest_path):
        return False
    return verify_manifest(manifest_path)



if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        hit = is_cache_hit(test_url)
        print(f"URL: {test_url}")
        print(f"Key: {normalize_url_key(test_url)}")
        print(f"Cache Hit: {hit}")
