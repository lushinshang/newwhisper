import pytest
from unittest.mock import MagicMock, patch

from scripts.detect_language import (
    contains_cjk,
    detect_language_from_metadata,
    detect_language_scheme_c,
)


def test_contains_cjk():
    assert contains_cjk("這是一段中文測試") is True
    assert contains_cjk("Anthropic 3万个Agent上岗，狂烧2.1亿token") is True
    assert contains_cjk("Live coding Jev from Scratch | Understanding Qwen architecture") is False
    assert contains_cjk("1234567890 !@#$%^&*()") is False


def test_detect_language_from_metadata():
    # 測試中文中繼資料
    meta_zh = {
        "title": "Anthropic 3万个Agent上岗，狂烧2.1亿token，挖出神秘DNA系统！",
        "description": "今天我們來探討最新大模型技術",
        "subtitles": {},
    }
    assert detect_language_from_metadata(meta_zh) == "zh"

    # 測試英文中繼資料
    meta_en = {
        "title": "Live coding Jev from Scratch | Understanding Qwen architecture",
        "description": "In this video we build an agent framework from scratch in python.",
        "subtitles": {"en": [{"ext": "vtt"}]},
    }
    assert detect_language_from_metadata(meta_en) == "en"


def test_detect_language_real_samples():
    # 實體驗證使用者提供的兩個黃金測試案例
    zh_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
    en_url = "https://www.youtube.com/watch?v=AzxoU7kxjig"

    res_zh = detect_language_scheme_c(zh_url)
    assert res_zh["language"] == "zh"
    assert res_zh["confidence"] >= 0.8

    res_en = detect_language_scheme_c(en_url)
    assert res_en["language"] == "en"
    assert res_en["confidence"] >= 0.8


def test_detect_gdrive_sample(monkeypatch):
    import scripts.detect_language as dl

    gdrive_url = "https://drive.google.com/file/d/1SampleDriveFileIdForTesting000/view?usp=drive_link"
    monkeypatch.setattr(dl, "fetch_gdrive_title", lambda url: "環境專題研討_49min.mp3")
    res = detect_language_scheme_c(gdrive_url)
    assert res["language"] == "zh"
    assert "環境專題研討" in res["title"]
    assert res["source"] == "gdrive_page_title"
