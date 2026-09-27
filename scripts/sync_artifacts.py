#!/usr/bin/env python3
"""
轉錄產物同步與校驗模組 (Artifact Synchronization & Verification)
功能：
1. 透過 colab CLI 從遠端下載指定字幕檔、文字檔與 Manifest
2. 比對本地檔案雜湊與 Manifest 規格，確保完整無殘缺交付
3. 支援自適應標題檔名同步
"""

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.cache_manager import verify_manifest


def validate_artifact_filename(fname: str, expected_ext: str, local_output_dir: str) -> bool:
    """檢查產物檔名是否安全（防 Path Traversal、限定副檔名、禁止絕對路徑）"""
    if not fname or not isinstance(fname, str):
        return False
    # 禁止目錄分隔符號、絕對路徑與單獨的 '.' 或 '..'
    if "/" in fname or "\\" in fname or fname in (".", "..") or os.path.basename(fname) != fname:
        return False
    # 檢查預期副檔名
    if not fname.lower().endswith(expected_ext.lower()):
        return False
    # 檢查組合後的路徑是否在 local_output_dir 範圍內
    abs_out = os.path.abspath(local_output_dir)
    target_path = os.path.abspath(os.path.join(abs_out, fname))
    return os.path.commonpath([abs_out, target_path]) == abs_out


def sync_artifacts_from_colab(
    session_name: str, cache_key: str, local_output_dir: str = "output", title: str | None = None
) -> bool:
    """透過 colab download 將遠端產物同步下載至本地"""
    os.makedirs(local_output_dir, exist_ok=True)
    colab_bin = shutil.which("colab") or "colab"

    def download_file(remote_fname: str, local_path: str) -> bool:
        candidates = [
            f"content/output/{remote_fname}",
            f"/content/output/{remote_fname}",
            f"output/{remote_fname}",
        ]
        err_msg = ""
        for remote_path in candidates:
            cmd = [colab_bin, "download", "-s", session_name, remote_path, local_path]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if res.returncode == 0 and os.path.exists(local_path):
                    return True
                err_msg = res.stderr.strip()
            except Exception as e:
                err_msg = str(e)
        print(f"⚠️ 下載 {remote_fname} 失敗: {err_msg}")
        return False

    print(f"📥 正在從雲端會話 [{session_name}] 同步轉錄產物至本地 {local_output_dir}/...")

    # 使用本地 output 同一磁區的暫存 staging 目錄進行原子化同步
    import tempfile
    staging_dir = tempfile.mkdtemp(prefix=".staging-sync-", dir=local_output_dir)

    try:
        # 1. 先下載 manifest.json 到暫存區
        manifest_fname = f"{cache_key}.manifest.json"
        if not validate_artifact_filename(manifest_fname, ".manifest.json", local_output_dir):
            print(f"❌ 錯誤：不合法的 Manifest 檔名: {manifest_fname}")
            return False
        manifest_staging = os.path.join(staging_dir, manifest_fname)
        if not download_file(manifest_fname, manifest_staging):
            return False

        # 2. 解析 manifest 取得真實的 srt 與 txt 檔案名稱並執行安全性檢驗
        srt_fname = f"{cache_key}.srt"
        txt_fname = f"{cache_key}.txt"
        try:
            with open(manifest_staging, "r", encoding="utf-8") as f:
                mdata = json.load(f)
            candidate_srt = (
                mdata.get("srt_file")
                or mdata.get("files", {}).get("srt", {}).get("name")
                or srt_fname
            )
            candidate_txt = (
                mdata.get("txt_file")
                or mdata.get("files", {}).get("txt", {}).get("name")
                or txt_fname
            )
            if not validate_artifact_filename(candidate_srt, ".srt", local_output_dir):
                print(f"❌ 安全性警報：Manifest 中的字幕檔名不合法或存在越界風險: {candidate_srt}")
                return False
            if not validate_artifact_filename(candidate_txt, ".txt", local_output_dir):
                print(f"❌ 安全性警報：Manifest 中的文字檔名不合法或存在越界風險: {candidate_txt}")
                return False
            srt_fname = candidate_srt
            txt_fname = candidate_txt
        except Exception as e:
            print(f"❌ 解析 Manifest 失敗: {e}")
            return False

        # 3. 下載 srt 與 txt 到暫存區
        srt_staging = os.path.join(staging_dir, srt_fname)
        if not download_file(srt_fname, srt_staging):
            return False

        txt_staging = os.path.join(staging_dir, txt_fname)
        if not download_file(txt_fname, txt_staging):
            return False

        # 4. 在暫存區核對 Manifest 與真實 SHA-256 雜湊
        if not verify_manifest(manifest_staging):
            print(f"⚠️ Manifest 完整性檢驗失敗 (暫存區): {manifest_staging}")
            return False

        # 5. 驗證全數通過，原子式發布到正式目錄 (同檔案系統原子替換)
        final_srt = os.path.join(local_output_dir, srt_fname)
        final_txt = os.path.join(local_output_dir, txt_fname)
        final_manifest = os.path.join(local_output_dir, manifest_fname)

        os.replace(srt_staging, final_srt)
        os.replace(txt_staging, final_txt)
        os.replace(manifest_staging, final_manifest)  # Manifest 最後提交

        print(f"✅ 產物完整性核驗通過！字幕檔已原子發布: {local_output_dir}/{srt_fname}")
        return True
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python sync_artifacts.py <SESSION_NAME> <CACHE_KEY> [LOCAL_OUTPUT_DIR] [TITLE]")
        sys.exit(1)
    sname = sys.argv[1]
    ckey = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "output"
    custom_title = sys.argv[4] if len(sys.argv) > 4 else None
    ok = sync_artifacts_from_colab(sname, ckey, out_dir, title=custom_title)
    sys.exit(0 if ok else 1)
