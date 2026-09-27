import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from scripts.cache_manager import generate_manifest
from scripts.sync_artifacts import sync_artifacts_from_colab


def test_sync_artifacts_success():
    import shutil
    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remotedir:
        cache_key = "test_sample_01"
        test_url = "https://example.com/audio.mp3"

        # 模擬遠端產生之檔案
        srt_file = os.path.join(remotedir, f"{cache_key}.srt")
        txt_file = os.path.join(remotedir, f"{cache_key}.txt")
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:02,000\n測試成功\n")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("測試成功\n")
        generate_manifest(remotedir, test_url, "breezesprint25", "zh", key=cache_key)

        def mock_subprocess_run(cmd, *args, **kwargs):
            # cmd: ["colab", "download", "-s", session, remote_path, local_path]
            remote_fname = os.path.basename(cmd[4])
            local_dest = cmd[5]
            src = os.path.join(remotedir, remote_fname)
            if os.path.exists(src):
                shutil.copyfile(src, local_dest)
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="File not found")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            ok = sync_artifacts_from_colab("mock-session", cache_key, tmpdir)
            assert ok is True
            assert os.path.exists(os.path.join(tmpdir, f"{cache_key}.srt"))
            assert os.path.exists(os.path.join(tmpdir, f"{cache_key}.txt"))
            assert os.path.exists(os.path.join(tmpdir, f"{cache_key}.manifest.json"))


def test_sync_artifacts_failure_on_command_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_key = "test_fail_01"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Session not found")
            ok = sync_artifacts_from_colab("mock-session", cache_key, tmpdir)
            assert ok is False


def test_sync_artifacts_blocks_path_traversal():
    """驗證 Manifest 含有惡意路徑遍歷時，必須立刻中斷並回傳 False"""
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_key = "test_evil_traversal"
        manifest_file = os.path.join(tmpdir, f"{cache_key}.manifest.json")

        # 模擬惡意 Manifest
        evil_manifest = {
            "cache_key": cache_key,
            "srt_file": "../../evil.srt",
            "txt_file": "evil.txt",
        }
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(evil_manifest, f)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ok = sync_artifacts_from_colab("mock-session", cache_key, tmpdir)
            assert ok is False, "偵測到 ../ 越界檔名時必須直接拒絕下載！"


def test_validate_artifact_filename():
    from scripts.sync_artifacts import validate_artifact_filename
    with tempfile.TemporaryDirectory() as tmpdir:
        assert validate_artifact_filename("safe_video.srt", ".srt", tmpdir) is True
        assert validate_artifact_filename("safe_video.txt", ".txt", tmpdir) is True
        # 解鎖省略號正常放行
        assert validate_artifact_filename("Wait... what.srt", ".srt", tmpdir) is True
        assert validate_artifact_filename("Lesson 1... Part 2.txt", ".txt", tmpdir) is True
        # 惡意檔名
        assert validate_artifact_filename("../safe_video.srt", ".srt", tmpdir) is False
        assert validate_artifact_filename("sub/safe_video.srt", ".srt", tmpdir) is False
        assert validate_artifact_filename("/tmp/evil.srt", ".srt", tmpdir) is False
        assert validate_artifact_filename("safe_video.exe", ".srt", tmpdir) is False
        assert validate_artifact_filename("", ".srt", tmpdir) is False
        assert validate_artifact_filename("..", ".srt", tmpdir) is False


def test_atomic_sync_failure_preserves_original_files():
    """驗證當同步驗證失敗時，本地既有的良好產物絕對不受污染或覆蓋"""
    import shutil
    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remotedir:
        cache_key = "test_atomic_preserve"
        orig_srt = os.path.join(tmpdir, f"{cache_key}.srt")
        with open(orig_srt, "w", encoding="utf-8") as f:
            f.write("原始完整無缺的正版字幕內容\n")

        # 模擬遠端產生壞檔 (損壞的 manifest)
        bad_manifest = os.path.join(remotedir, f"{cache_key}.manifest.json")
        with open(bad_manifest, "w", encoding="utf-8") as f:
            f.write("Corrupted JSON content")

        def mock_subprocess_run(cmd, *args, **kwargs):
            remote_fname = os.path.basename(cmd[4])
            local_dest = cmd[5]
            src = os.path.join(remotedir, remote_fname)
            if os.path.exists(src):
                shutil.copyfile(src, local_dest)
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            ok = sync_artifacts_from_colab("mock-session", cache_key, tmpdir)
            assert ok is False
            # 原始正版內容依然完好無損
            with open(orig_srt, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == "原始完整無缺的正版字幕內容\n"


