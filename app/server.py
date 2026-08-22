from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.config import TsuzuriConfig, load_config
from engine.conversation import ConversationCore
from engine.rulebook import Rulebook
from models.backend import LlamaServerBackend


def ensure_model(config: TsuzuriConfig) -> Path:
    if config.model.model_path:
        path = Path(config.model.model_path)
        if not path.exists():
            raise FileNotFoundError(f"model_path が見つかりません: {path}")
        return path
    from huggingface_hub import hf_hub_download

    print(f"モデルを取得中: {config.model.repo_id} / {config.model.gguf_file}")
    cache_dir = os.environ.get("TSUZURI_HF_CACHE") or None
    downloaded = hf_hub_download(
        repo_id=config.model.repo_id,
        filename=config.model.gguf_file,
        cache_dir=cache_dir,
    )
    return Path(downloaded)


def create_backend(config: TsuzuriConfig) -> LlamaServerBackend:
    model = config.model
    return LlamaServerBackend(
        server_url=model.server_url,
        llama_bin=model.llama_bin,
        model_path=model.model_path or None,
        host=model.host,
        port=model.port,
        ctx_size=model.ctx_size,
        n_gpu_layers=model.n_gpu_layers,
        startup_timeout=model.startup_timeout,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TSUZURI - OSS AI Story Engine")
    parser.add_argument("--config", default=None, help="config.yaml のパス")
    parser.add_argument("--rulebook", default="examples/modern.yaml", help="Rulebook YAML のパス")
    parser.add_argument("--session", default=None, help="セッションID（saves/<id>/ に保存）")
    parser.add_argument("--server-url", default=None, help="既存 OpenAI互換サーバーのURL（例: http://127.0.0.1:8080）")
    parser.add_argument("--llama-bin", default=None, help="llama-server バイナリのパス")
    parser.add_argument("--gguf", default=None, help="GGUF モデルファイルのパス")
    parser.add_argument("--share", action="store_true", help="Gradio 共有URLを発行（Colab用）")
    parser.add_argument("--auto-setup", action="store_true", help="llama-serverバイナリとモデルを自動準備する")
    parser.add_argument("--ui-port", type=int, default=7860)
    args = parser.parse_args(argv)
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    if args.server_url:
        config.model.server_url = args.server_url
    model_thread: threading.Thread | None = None
    model_result: dict = {}

    if not config.model.server_url:
        if args.gguf:
            config.model.model_path = args.gguf
        elif args.auto_setup and not config.model.model_path:
            def _download_model() -> None:
                try:
                    model_result["path"] = str(ensure_model(config))
                except Exception as exc:
                    model_result["error"] = exc

            model_thread = threading.Thread(target=_download_model)
            model_thread.start()

        if args.llama_bin:
            config.model.llama_bin = args.llama_bin
        elif args.auto_setup and not config.model.llama_bin:
            from app.setup import ensure_llama_bin

            config.model.llama_bin = ensure_llama_bin()

        if not config.model.llama_bin:
            raise SystemExit(
                "llama-server バイナリを指定してください。\n"
                "  --auto-setup で自動セットアップ（Colab推奨）\n"
                "  環境変数 TSUZURI_LLAMA_BIN、または --llama-bin <path>\n"
                "  もしくは --server-url で既存のOpenAI互換サーバーに接続してください。"
            )

        if not config.model.model_path:
            if model_thread is not None:
                model_thread.join()
                if "error" in model_result:
                    raise model_result["error"]
                config.model.model_path = model_result["path"]
            else:
                config.model.model_path = str(ensure_model(config))

    rulebook = Rulebook.load_yaml(args.rulebook)
    backend = create_backend(config)
    core = ConversationCore(config, backend, rulebook, session_id=args.session)

    from app.ui import build_ui

    demo = build_ui(core)
    try:
        demo.queue().launch(server_name="0.0.0.0", server_port=args.ui_port, share=args.share)
    finally:
        core.shutdown()


if __name__ == "__main__":
    main()
