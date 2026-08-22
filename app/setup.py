from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
REPO_URL = "https://github.com/ggml-org/llama.cpp"

_ASSET_KEYWORDS = {
    "linux": "ubuntu",
    "windows": "win",
    "darwin": "macos",
}


def _default_install_root() -> Path:
    cache_env = os.environ.get("TSUZURI_LLAMA_CACHE")
    if cache_env:
        return Path(cache_env)
    if Path("/content").exists():
        return Path("/content/llama-bin")
    return Path.home() / ".tsuzuri" / "llama-bin"


def find_existing() -> str | None:
    candidates: list[str] = []
    env_value = os.environ.get("TSUZURI_LLAMA_BIN")
    if env_value:
        candidates.append(env_value)
    which = shutil.which("llama-server")
    if which:
        candidates.append(which)
    candidates += glob.glob(str(_default_install_root() / "**" / "llama-server*"), recursive=True)
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _pick_asset(assets: list[dict]) -> tuple[str, bool] | None:
    keyword = _ASSET_KEYWORDS.get(platform.system().lower())
    if keyword is None:
        return None
    urls = [asset["browser_download_url"] for asset in assets]

    def find(*needles: str) -> str | None:
        for url in urls:
            lowered = url.lower()
            if keyword in lowered and all(needle in lowered for needle in needles) and lowered.endswith(".zip"):
                return url
        return None

    cuda_url = find("cuda")
    if cuda_url:
        return cuda_url, True
    plain_url = find()
    if plain_url:
        return plain_url, False
    return None


def _extract_and_locate(zip_path: Path, root: Path) -> str | None:
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(root)
    pattern = "llama-server.exe" if platform.system().lower() == "windows" else "llama-server"
    hits = sorted(glob.glob(str(root / "**" / pattern), recursive=True))
    if not hits:
        return None
    binary = Path(hits[-1])
    if platform.system().lower() != "windows":
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    for extra in glob.glob(str(binary.parent / "llama-*")):
        p = Path(extra)
        if p.is_file():
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(binary)


def install_from_release(root: Path) -> tuple[str, bool] | None:
    request = urllib.request.Request(RELEASE_API, headers={"User-Agent": "tsuzuri-setup"})
    release = json.loads(urllib.request.urlopen(request, timeout=60).read())
    picked = _pick_asset(release.get("assets") or [])
    if picked is None:
        return None
    url, is_cuda = picked
    print(f"[setup] downloading {url}")
    zip_path = root / "llama.zip"
    urllib.request.urlretrieve(url, zip_path)
    binary = _extract_and_locate(zip_path, root)
    if binary is None:
        return None
    return binary, is_cuda


def build_from_source(root: Path) -> str:
    source_dir = root / "llama.cpp"
    if not source_dir.exists():
        print(f"[setup] cloning {REPO_URL}")
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(source_dir)], check=True)
    use_cuda = shutil.which("nvcc") is not None
    jobs = max((os.cpu_count() or 2) - 1, 1)
    print(f"[setup] building llama.cpp (GGML_CUDA={'ON' if use_cuda else 'OFF'}, -j{jobs}) ...")
    subprocess.run(
        ["cmake", "-S", str(source_dir), "-B", str(source_dir / "build"), f"-DGGML_CUDA={'ON' if use_cuda else 'OFF'}"],
        check=True,
    )
    subprocess.run(
        ["cmake", "--build", str(source_dir / "build"), "--config", "Release", "-j", str(jobs)],
        check=True,
    )
    pattern = "llama-server.exe" if platform.system().lower() == "windows" else "llama-server"
    hits = sorted(glob.glob(str(source_dir / "build" / "**" / pattern), recursive=True))
    if not hits:
        raise RuntimeError("ビルド完了後も llama-server が見つかりませんでした")
    binary = Path(hits[-1])
    if platform.system().lower() != "windows":
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return str(binary)


def ensure_llama_bin(install_root: str | Path | None = None) -> str:
    existing = find_existing()
    if existing:
        print(f"[setup] llama-server を使用: {existing}")
        return existing

    root = Path(install_root) if install_root else _default_install_root()
    if find_existing() is None:
        print("[setup] llama-server が見つからないため自動セットアップします（初回のみ。次回以降はキャッシュを使用）")
    root.mkdir(parents=True, exist_ok=True)

    try:
        result = install_from_release(root)
    except Exception as exc:
        print(f"[setup] リリース取得に失敗: {exc}")
        result = None

    if result is not None:
        binary, is_cuda = result
        if not is_cuda:
            print("[setup] 注意: CUDA版が見つからなかったためCPU版を使用します（動作は遅くなります）")
        print(f"[setup] llama-server 準備完了: {binary}")
        return binary

    if platform.system().lower() != "linux":
        raise SystemExit(
            "[setup] 自動セットアップに失敗しました。llama.cpp を手動でビルドし、\n"
            "  環境変数 TSUZURI_LLAMA_BIN でパスを指定してください。"
        )

    binary = build_from_source(root)
    print(f"[setup] llama-server ビルド完了: {binary}")
    return binary


if __name__ == "__main__":
    print(ensure_llama_bin())
