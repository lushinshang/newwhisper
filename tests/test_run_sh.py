import os
import subprocess
import tempfile
import pytest
from scripts.cache_manager import generate_manifest


def test_run_sh_cache_hit_simulation():
    # 測試當本地已存在完整字幕與合法 Manifest 時，run.sh 能秒級命中快取退出
    script_path = os.path.abspath("run.sh")
    test_url = "https://www.youtube.com/watch?v=mnDNJSopb6Q"

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_key = "yt_mnDNJSopb6Q"
        srt_path = os.path.join(tmpdir, f"{cache_key}.srt")
        txt_path = os.path.join(tmpdir, f"{cache_key}.txt")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:03,000\n快取測試字幕\n")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("快取測試字幕\n")

        # 產生合法且含真實 SHA-256 簽章的 Manifest
        generate_manifest(output_dir=tmpdir, url=test_url, model_name="breezesprint25", language="zh")

        # 注入隔離環境變數，執行 run.sh
        test_env = os.environ.copy()
        test_env["NEWWHISPER_OUTPUT_DIR"] = tmpdir

        res = subprocess.run([script_path, test_url], capture_output=True, text=True, env=test_env)
        assert res.returncode == 0
        assert "快取秒級命中" in res.stdout
        assert "0 點數消耗" in res.stdout

