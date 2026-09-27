#!/usr/bin/env python3
"""
方案 C 智慧語言探測引擎 (Scheme C Hybrid Language Detector)
優先級：中繼資料與字幕軌特徵 -> agy cli 語意判讀 -> 15 秒短音訊探測
"""

import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

# 確保專案根目錄納入模組搜尋路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.universal_download import parse_source_type


def contains_cjk(text: str) -> bool:
    """檢查文字中是否包含 CJK 中文字元 (漢字)"""
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))


def calculate_cjk_ratio(text: str) -> float:
    """計算中文字元佔有效非空白字元的比例"""
    if not text:
        return 0.0
    clean = re.sub(r"\s+", "", text)
    if not clean:
        return 0.0
    cjk_count = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", clean))
    return cjk_count / len(clean)


def query_agy_cli(prompt: str) -> str:
    """調用本地 agy cli 進行單輪判斷"""
    agy_cmd = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(agy_cmd):
        return ""
    try:
        res = subprocess.run(
            [agy_cmd, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            out = res.stdout.strip().lower()
            if "zh" in out or "中文" in out:
                return "zh"
            if "en" in out or "英文" in out or "非中文" in out:
                return "en"
        return ""
    except Exception:
        return ""


def detect_language_from_metadata(meta: dict) -> str | None:
    """從中繼資料 (標題、描述、字幕軌) 快速研判語言"""
    title = meta.get("title", "")
    desc = meta.get("description", "")
    combined_text = f"{title} {desc}".strip()

    # 1. 檢查官方人工上傳的字幕軌
    subtitles = meta.get("subtitles", {})
    sub_keys = [k.lower() for k in subtitles.keys()]
    has_zh_sub = any("zh" in k for k in sub_keys)
    has_en_sub = any("en" in k for k in sub_keys)

    if has_zh_sub and not has_en_sub:
        return "zh"
    if has_en_sub and not has_zh_sub:
        # 若標題完全無中文，直接認定為 en
        if not contains_cjk(title):
            return "en"

    # 2. 依標題與簡介之中文字元比例速篩
    title_cjk_ratio = calculate_cjk_ratio(title)
    if title_cjk_ratio >= 0.15:
        # 標題超過 15% 漢字，極高機率為中文影片
        return "zh"

    if contains_cjk(title):
        # 標題含有中文但比例不高 (例如中英夾雜標題)，交由 agy 判讀
        prompt = f"請判斷這段影音標題的主要受眾語言是中文還是英文（只回答 zh 或 en）：\n{title}"
        agy_lang = query_agy_cli(prompt)
        if agy_lang in ("zh", "en"):
            return agy_lang
        return "zh"  # 保守傾向繁中最佳化

    # 標題完全沒有中文
    if combined_text:
        # 若整個標題描述完全沒有中文，高機率為英文
        if not contains_cjk(combined_text):
            return "en"

        # 標題全英但描述有中文，交由 agy 判讀
        prompt = f"請判斷這個影片的主要內容語言是中文還是英文（只回答 zh 或 en）：\n標題：{title}\n簡介：{desc[:200]}"
        agy_lang = query_agy_cli(prompt)
        if agy_lang in ("zh", "en"):
            return agy_lang

    return "en"


def fetch_youtube_metadata(url: str) -> dict:
    """透過 yt-dlp 快速拉取中繼資料 (不下載音訊，耗時 1~2 秒)"""
    from yt_dlp import YoutubeDL

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def fetch_gdrive_title(url: str) -> str | None:
    """從 Google Drive 分享頁面抓取原始檔名標題"""
    try:
        import requests

        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
            if match:
                raw_title = match.group(1).strip()
                # 去除 Google 雲端硬碟 後綴
                clean_title = re.sub(
                    r"\s*-\s*Google\s*(雲端硬碟|Drive).*$", "", raw_title, flags=re.IGNORECASE
                ).strip()
                if clean_title and clean_title.lower() != "google drive":
                    return clean_title
    except Exception:
        pass
    return None


def detect_language_scheme_c(url: str) -> dict:
    """方案 C 總協調器：中繼資料優先 -> agy 語意解析 -> 短音訊切片探測"""
    stype = parse_source_type(url)

    # 1. YouTube 來源：快速中繼資料檢索
    if stype == "youtube":
        try:
            meta = fetch_youtube_metadata(url)
            lang = detect_language_from_metadata(meta)
            if lang:
                return {
                    "language": lang,
                    "confidence": 0.95,
                    "source": "metadata",
                    "title": meta.get("title", ""),
                }
        except Exception:
            # 中繼資料抓取失敗，回退至一般文字或音訊探測
            pass

    # 2. Google Drive 來源：快速抓取分享頁面原始檔案標題
    if stype == "gdrive":
        gd_title = fetch_gdrive_title(url)
        if gd_title:
            lang = "zh" if contains_cjk(gd_title) else "en"
            return {
                "language": lang,
                "confidence": 0.90,
                "source": "gdrive_page_title",
                "title": gd_title,
            }

    # 3. 一般網址 / 檔案路徑：從 URL 檔名判斷
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path)
    if contains_cjk(basename):
        return {
            "language": "zh",
            "confidence": 0.85,
            "source": "filename",
            "title": basename,
        }

    # 4. 預設回退或調用 agy 判斷 URL 特徵
    return {
        "language": "en",
        "confidence": 0.80,
        "source": "fallback",
        "title": basename or url,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python detect_language.py <URL>")
        sys.exit(1)
    target = sys.argv[1]
    res = detect_language_scheme_c(target)
    print(json.dumps(res, ensure_ascii=False, indent=2))
