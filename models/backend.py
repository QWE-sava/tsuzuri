from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

Message = dict[str, str]

_SENTINEL = object()

DEFAULT_MOCK_REPLY = "Aliceは静かに微笑んだ。「うん、また一緒に来よう」。窓の外では、まだ雨が音もなく降り続いている。"


@dataclass
class GenParams:
    temperature: float = 0.85
    top_p: float = 0.95
    max_tokens: int = 600
    repeat_penalty: float = 1.05


class ModelBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(self, messages: list[Message], params: GenParams | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: list[Message], params: GenParams | None = None) -> Iterator[str]:
        raise NotImplementedError

    def unload(self) -> None:
        return None

    async def agenerate(self, messages: list[Message], params: GenParams | None = None) -> str:
        return await asyncio.to_thread(self.generate, messages, params)

    async def astream(self, messages: list[Message], params: GenParams | None = None) -> AsyncIterator[str]:
        iterator = self.stream(messages, params)

        def _next_chunk() -> Any:
            try:
                return next(iterator)
            except StopIteration:
                return _SENTINEL

        while True:
            chunk = await asyncio.to_thread(_next_chunk)
            if chunk is _SENTINEL:
                break
            yield chunk


def _normalize_base_url(url: str) -> str:
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class OpenAICompatBackend(ModelBackend):
    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str = "not-needed", model_name: str = "default", timeout: float = 300.0):
        from openai import OpenAI

        self.base_url = _normalize_base_url(base_url)
        self.model_name = model_name
        self._client = OpenAI(base_url=self.base_url, api_key=api_key, timeout=timeout)

    def generate(self, messages: list[Message], params: GenParams | None = None) -> str:
        p = params or GenParams()
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=p.temperature,
            top_p=p.top_p,
            max_tokens=p.max_tokens,
            extra_body={"repeat_penalty": p.repeat_penalty},
            stream=False,
        )
        return response.choices[0].message.content or ""

    def stream(self, messages: list[Message], params: GenParams | None = None) -> Iterator[str]:
        p = params or GenParams()
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=p.temperature,
            top_p=p.top_p,
            max_tokens=p.max_tokens,
            extra_body={"repeat_penalty": p.repeat_penalty},
            stream=True,
        )
        for event in response:
            if event.choices and event.choices[0].delta and event.choices[0].delta.content:
                yield event.choices[0].delta.content


class LlamaServerBackend(OpenAICompatBackend):
    name = "llama-server"

    def __init__(
        self,
        server_url: str = "",
        llama_bin: str = "",
        model_path: str = "",
        host: str = "127.0.0.1",
        port: int = 8321,
        ctx_size: int = 8192,
        n_gpu_layers: int = 99,
        startup_timeout: float = 600.0,
        extra_args: list[str] | None = None,
        log_file: str | None = None,
    ):
        self._proc: subprocess.Popen | None = None
        self._log_handle = None
        if server_url:
            super().__init__(base_url=server_url)
            return
        if not llama_bin or not model_path:
            raise ValueError("server_url を指定するか、llama_bin と model_path の両方を指定してください")
        exe = shutil.which(llama_bin) or llama_bin
        cmd = [
            exe,
            "-m",
            model_path,
            "--host",
            host,
            "--port",
            str(port),
            "-c",
            str(ctx_size),
            "-ngl",
            str(n_gpu_layers),
        ]
        cmd += list(extra_args or [])
        if log_file:
            self._log_handle = open(log_file, "w", encoding="utf-8")
        stdout_target = self._log_handle if self._log_handle else subprocess.DEVNULL
        self._proc = subprocess.Popen(cmd, stdout=stdout_target, stderr=subprocess.STDOUT)
        base_url = f"http://{host}:{port}"
        self._wait_ready(base_url, startup_timeout)
        super().__init__(base_url=base_url)

    def _wait_ready(self, base_url: str, timeout: float) -> None:
        health_url = f"{base_url}/health"
        deadline = time.time() + timeout
        last_error: Exception | str | None = None
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(f"llama-server が起動中に終了しました (code={self._proc.returncode})")
            try:
                with urllib.request.urlopen(health_url, timeout=5) as resp:
                    if resp.status == 200:
                        return
                    last_error = f"HTTP {resp.status}"
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
            except Exception as exc:
                last_error = repr(exc)
            time.sleep(1.0)
        raise TimeoutError(f"llama-server が {timeout} 秒以内に応答しません ({last_error})")

    def unload(self) -> None:
        super().unload()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


class MockBackend(ModelBackend):
    name = "mock"

    def __init__(
        self,
        responses: list[str] | None = None,
        responder=None,
        default: str = DEFAULT_MOCK_REPLY,
    ):
        self.responses = list(responses or [])
        self.responder = responder
        self.default = default
        self.calls: list[list[Message]] = []
        self._cursor = 0

    def _next_reply(self, messages: list[Message]) -> str:
        self.calls.append(list(messages))
        if self.responder is not None:
            return self.responder(messages)
        if self._cursor < len(self.responses):
            reply = self.responses[self._cursor]
            self._cursor += 1
            return reply
        return self.default

    def generate(self, messages: list[Message], params: GenParams | None = None) -> str:
        return self._next_reply(messages)

    def stream(self, messages: list[Message], params: GenParams | None = None) -> Iterator[str]:
        text = self._next_reply(messages)
        step = 4
        for i in range(0, len(text), step):
            yield text[i : i + step]
