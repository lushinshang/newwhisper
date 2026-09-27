import pytest
from scripts.run_transcribe import format_srt_time, generate_srt_content


def test_format_srt_time():
    assert format_srt_time(0.0) == "00:00:00,000"
    assert format_srt_time(1.234) == "00:00:01,234"
    assert format_srt_time(65.5) == "00:01:05,500"
    assert format_srt_time(3661.05) == "01:01:01,050"


def test_generate_srt_content():
    segments = [
        {"start": 0.0, "end": 2.5, "text": "第一段測試文字"},
        {"start": 2.6, "end": 5.0, "text": "第二段測試文字"},
    ]
    srt = generate_srt_content(segments)
    expected = (
        "1\n00:00:00,000 --> 00:00:02,500\n第一段測試文字\n\n"
        "2\n00:00:02,600 --> 00:00:05,000\n第二段測試文字\n"
    )
    assert srt.strip() == expected.strip()
