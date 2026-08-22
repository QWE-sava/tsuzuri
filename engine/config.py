from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    server_url: str = ""
    llama_bin: str = ""
    model_path: str = ""
    repo_id: str = "unsloth/gemma-4-E4B-it-GGUF"
    gguf_file: str = "gemma-4-E4B-it-Q4_K_M.gguf"
    host: str = "127.0.0.1"
    port: int = 8321
    ctx_size: int = 8192
    n_gpu_layers: int = 99
    startup_timeout: float = 600.0


@dataclass
class GenConfig:
    temperature: float = 0.85
    top_p: float = 0.95
    max_tokens: int = 600
    repeat_penalty: float = 1.05


@dataclass
class MemoryConfig:
    recent_window: int = 8
    summarize_trigger: int = 14
    facts_enabled: bool = True


@dataclass
class GuardConfig:
    enabled: bool = True
    async_judge: bool = True
    max_retry: int = 2
    tension_threshold: float = 0.35
    intruder_markers: list[str] = field(default_factory=lambda: [
        "見知らぬ",
        "謎の",
        "第三者",
        "もう一人の客",
        "他の客",
        "別の客",
        "知らない男",
        "知らない女",
        "見たこともない人物",
        "突然現れた",
        "いきなり現れ",
        "不意に現れ",
    ])
    escalation_keywords: list[str] = field(default_factory=lambda: [
        "銃声",
        "爆発",
        "悲鳴",
        "襲撃",
        "刺さ",
        "血まみれ",
        "誘拐",
        "強盗",
        "地震",
        "火事",
        "火災",
        "救急車",
        "戦争",
        "怪物",
        "魔物",
    ])


@dataclass
class ContextConfig:
    token_budget: int = 6144
    chars_per_token: float = 1.5
    max_facts_in_context: int = 10


@dataclass
class TsuzuriConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    gen: GenConfig = field(default_factory=GenConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    guard: GuardConfig = field(default_factory=GuardConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    saves_dir: Path = Path("saves")
    session_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _apply_overrides(target: Any, data: dict[str, Any] | None) -> None:
    if not data:
        return
    for key, value in data.items():
        if not hasattr(target, key):
            continue
        current = getattr(target, key)
        if isinstance(current, Path):
            setattr(target, key, Path(value))
        elif isinstance(current, bool):
            setattr(target, key, bool(value))
        elif isinstance(current, list):
            setattr(target, key, [str(v) for v in value])
        elif isinstance(current, float):
            setattr(target, key, float(value))
        elif isinstance(current, int):
            setattr(target, key, int(value))
        else:
            setattr(target, key, "" if value is None else str(value))


_ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "TSUZURI_SERVER_URL": ("model", "server_url"),
    "TSUZURI_LLAMA_BIN": ("model", "llama_bin"),
    "TSUZURI_MODEL_PATH": ("model", "model_path"),
}


def load_config(path: str | Path | None = None) -> TsuzuriConfig:
    cfg = TsuzuriConfig()
    if path is not None and Path(path).exists():
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for section in ("model", "gen", "memory", "guard", "context"):
            _apply_overrides(getattr(cfg, section), raw.get(section))
        top_level = {k: v for k, v in raw.items() if k not in {"model", "gen", "memory", "guard", "context"}}
        _apply_overrides(cfg, top_level)
    for env_key, (section_name, attr_name) in _ENV_OVERRIDES.items():
        value = os.environ.get(env_key)
        if value:
            setattr(getattr(cfg, section_name), attr_name, value)
    return cfg
