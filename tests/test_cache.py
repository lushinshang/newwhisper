import json
import os
import tempfile
import pytest

from scripts.cache_manager import (
    normalize_url_key,
    get_cache_file_paths,
    is_cache_hit,
    generate_manifest,
    verify_manifest,
)


def test_normalize_url_key_youtube():
    # 同一影片的不同變體 URL 應產生相同的快取鍵
    u1 = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
    u2 = "https://youtu.be/mnDNJSopb6Q?t=45"
    u3 = "https://m.youtube.com/watch?v=mnDNJSopb6Q&feature=share"

    assert normalize_url_key(u1) == "yt_mnDNJSopb6Q"
    assert normalize_url_key(u2) == "yt_mnDNJSopb6Q"
    assert normalize_url_key(u3) == "yt_mnDNJSopb6Q"


def test_normalize_url_key_gdrive():
    g1 = "https://drive.google.com/file/d/1A2B3C4D5E/view?usp=sharing"
    g2 = "https://drive.google.com/open?id=1A2B3C4D5E"
    assert normalize_url_key(g1) == "gdrive_1A2B3C4D5E"
    assert normalize_url_key(g2) == "gdrive_1A2B3C4D5E"


def test_is_cache_hit_and_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
        srt_path, txt_path, manifest_path = get_cache_file_paths(test_url, tmpdir)

        # 初始狀態：未命中快取
        assert is_cache_hit(test_url, tmpdir) is False

        # 寫入空白檔案：依然未命中 (防殘留空檔)
        with open(srt_path, "w") as f:
            f.write("")
        assert is_cache_hit(test_url, tmpdir) is False

        # 寫入有效字幕內容與文字檔
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\n你好世界\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("你好世界\n")

        # 產生 Manifest
        manifest = generate_manifest(
            output_dir=tmpdir,
            url=test_url,
            model_name="breezesprint25",
            language="zh",
        )
        assert os.path.exists(manifest_path)
        assert manifest["language"] == "zh"
        assert manifest["model"] == "breezesprint25"

        # 驗證快取命中
        assert is_cache_hit(test_url, tmpdir) is True
        assert verify_manifest(manifest_path) is True


def test_sanitize_title_for_filename():
    from scripts.cache_manager import sanitize_title_for_filename

    # Google Drive 案例：去除副檔名
    gd_name = "sample_chinese_lecture_audio.mp3"
    assert sanitize_title_for_filename(gd_name) == "sample_chinese_lecture_audio"

    # YouTube 案例：特殊字元清理 (: 轉為 _)
    yt_title = "Full Course: Spec-Driven Development with Coding Agents"
    assert sanitize_title_for_filename(yt_title) == "Full Course_ Spec-Driven Development with Coding Agents"

    # 特殊字元多重清理
    assert sanitize_title_for_filename('A/B\\C:D*E?F"G<H>I|J') == "A_B_C_D_E_F_G_H_I_J"


def test_title_based_cache_and_manifest():
    from scripts.cache_manager import sanitize_title_for_filename

    with tempfile.TemporaryDirectory() as tmpdir:
        url = "https://drive.google.com/file/d/1SampleDriveFileIdForTesting000/view"
        raw_title = "sample_chinese_lecture_audio.mp3"
        safe_title = sanitize_title_for_filename(raw_title)

        srt_path, txt_path, manifest_path = get_cache_file_paths(url, tmpdir, title=raw_title)
        assert os.path.basename(srt_path) == f"{safe_title}.srt"
        assert os.path.basename(txt_path) == f"{safe_title}.txt"

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:02,000\n測試內容\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("測試內容\n")

        manifest = generate_manifest(
            output_dir=tmpdir,
            url=url,
            model_name="breezesprint25",
            language="zh",
            title=raw_title,
        )
        assert manifest["srt_file"] == f"{safe_title}.srt"
        assert is_cache_hit(url, tmpdir, title=raw_title) is True
        assert verify_manifest(manifest_path) is True


def test_verify_manifest_sha256_mismatch():
    """驗證當產物內容遭到等長竄改時，SHA-256 比對必須攔截並返回 False"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
        srt_path, txt_path, manifest_path = get_cache_file_paths(test_url, tmpdir)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\n原始正版內容\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("原始正版內容\n")

        generate_manifest(output_dir=tmpdir, url=test_url, model_name="breezesprint25", language="zh")
        assert verify_manifest(manifest_path) is True

        # 惡意等長竄改 (大小相同但字節不同)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\n惡意等長竄改\n")
        assert verify_manifest(manifest_path) is False, "SHA-256 不吻合時必須拒絕通過！"


def test_verify_manifest_path_traversal_blocked():
    """驗證 Manifest 包含路徑跳躍 (../) 時必須直接阻擋"""
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        test_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
        srt_path, txt_path, manifest_path = get_cache_file_paths(test_url, tmpdir)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\n測試\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("測試\n")

        generate_manifest(output_dir=tmpdir, url=test_url, model_name="breezesprint25", language="zh")

        # 篡改 manifest 讓其指向父目錄
        with open(manifest_path, "r", encoding="utf-8") as f:
            mdata = json.load(f)
        mdata["files"]["srt"]["name"] = "../../etc/passwd"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(mdata, f)

        assert verify_manifest(manifest_path) is False, "路徑越界時必須拒絕通過！"


def test_is_cache_hit_rejects_corrupted_or_missing_manifest():
    """驗證當本地檔案存在但缺少合法 Manifest 或 SHA-256 損壞時，is_cache_hit 必須返回 False"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"
        srt_path, txt_path, manifest_path = get_cache_file_paths(test_url, tmpdir)

        # 模擬未經授權的壞檔或測試污染殘留
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("這是一段沒有 manifest 的殘留檔案內容，長度大於 10 bytes\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("殘留檔案\n")

        # 沒有 manifest，必須 MISS
        assert is_cache_hit(test_url, tmpdir) is False

        # 建立了 Manifest 但內容遭到修改 (SHA-256 mismatch)，必須 MISS
        generate_manifest(output_dir=tmpdir, url=test_url, model_name="breezesprint25", language="zh")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("內容被損壞或遭意外截斷\n")
        assert is_cache_hit(test_url, tmpdir) is False


def test_sanitize_title_long_chinese_bytes_limit():
    """驗證超長中文標題（>200 bytes）能被安全截斷且不產生多位元組截斷亂碼"""
    from scripts.cache_manager import sanitize_title_for_filename, MAX_NAME_BYTES

    long_title = "這是一個非常非常長的中文字串用來測試檔案系統長度上限" * 10  # 超過 300 bytes
    safe_name = sanitize_title_for_filename(long_title)

    raw_bytes = safe_name.encode("utf-8")
    assert len(raw_bytes) <= MAX_NAME_BYTES
    # 確保能被完整解碼，未切斷中文字
    decoded = raw_bytes.decode("utf-8")
    assert decoded == safe_name


