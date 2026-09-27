import pytest
from unittest.mock import patch, MagicMock

# 從即將實作的 scripts.universal_download 導入
from scripts.universal_download import (
    is_youtube_url,
    is_gdrive_url,
    extract_gdrive_file_id,
    parse_source_type,
    extract_filename_from_cd,
    normalize_audio_extension,
)


def test_is_youtube_url():
    assert is_youtube_url("https://www.youtube.com/watch?v=mnDNJSopb6Q") is True
    assert is_youtube_url("https://youtu.be/AzxoU7kxjig") is True
    assert is_youtube_url("https://m.youtube.com/watch?v=abc") is True
    assert is_youtube_url("https://drive.google.com/file/d/123") is False
    assert is_youtube_url("https://example.com/audio.mp3") is False


def test_is_gdrive_url():
    assert is_gdrive_url("https://drive.google.com/file/d/1A2B3C/view") is True
    assert is_gdrive_url("https://drive.google.com/open?id=1A2B3C") is True
    assert is_gdrive_url("https://drive.google.com/uc?id=1A2B3C") is True
    assert is_gdrive_url("https://www.youtube.com/watch?v=123") is False


def test_extract_gdrive_file_id_various_formats():
    # 格式 1: open?id=
    assert extract_gdrive_file_id("https://drive.google.com/open?id=FILE_ID_111") == "FILE_ID_111"
    # 格式 2: /file/d/FILE_ID/view
    assert extract_gdrive_file_id("https://drive.google.com/file/d/FILE_ID_222/view?usp=sharing") == "FILE_ID_222"
    # 格式 3: uc?id=
    assert extract_gdrive_file_id("https://drive.google.com/uc?id=FILE_ID_333&export=download") == "FILE_ID_333"
    # 非法或不含 ID
    assert extract_gdrive_file_id("https://example.com/not-drive") is None


def test_parse_source_type():
    assert parse_source_type("https://www.youtube.com/watch?v=mnDNJSopb6Q") == "youtube"
    assert parse_source_type("https://drive.google.com/file/d/xyz123/view") == "gdrive"
    assert parse_source_type("https://media.example.com/podcast/ep1.mp3") == "direct"
    assert parse_source_type("ftp://invalid-protocol.com/file.wav") == "invalid"
    assert parse_source_type("not-a-url") == "invalid"


def test_extract_filename_from_cd():
    cd1 = 'attachment; filename="interview_recording.mp3"'
    assert extract_filename_from_cd(cd1) == "interview_recording.mp3"

    cd2 = "attachment; filename=podcast_2026.wav"
    assert extract_filename_from_cd(cd2) == "podcast_2026.wav"

    cd_none = "inline"
    assert extract_filename_from_cd(cd_none) is None


def test_normalize_audio_extension():
    assert normalize_audio_extension("audio/mp4") == ".m4a"
    assert normalize_audio_extension("audio/mpeg") == ".mp3"
    assert normalize_audio_extension("audio/wav") == ".wav"
    assert normalize_audio_extension("audio/x-wav") == ".wav"
    assert normalize_audio_extension("video/mp4") == ".mp4"
    assert normalize_audio_extension("text/html") is None
