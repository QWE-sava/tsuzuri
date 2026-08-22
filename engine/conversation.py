from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

from models.backend import GenParams, ModelBackend

from .background import BackgroundWorker
from .config import TsuzuriConfig
from .context import ContextManager
from .jsonparse import extract_json_object
from .memory import Memory, extract_facts, summarize_turns
from .prompt import FALLBACK_NOTE, build_messages, state_update_prompt
from .rulebook import Rulebook
from .self_guard import AsyncGuard, GuardResult, SyncGuard
from .story_state import StoryState
from .validator import validate_output

EMPTY_REPLY_PLACEHOLDER = "（応答を生成できませんでした。もう一度お試しください。）"

_EVENT_PATTERN = re.compile(r"(行った|来た|会った|起きた|出会った|買った|見つかった|壊れた|約束し|引っ越)")


class ConversationCore:
    def __init__(
        self,
        config: TsuzuriConfig,
        backend: ModelBackend,
        rulebook: Rulebook,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.backend = backend
        self.rulebook = rulebook
        if session_id:
            config.session_id = session_id
        self.session_dir = Path(config.saves_dir) / config.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        state_path = self._path("state.json")
        memory_path = self._path("memory.json")
        self.state = StoryState.load(state_path) if state_path.exists() else StoryState()
        self.memory = Memory.load(memory_path) if memory_path.exists() else Memory()
        self.history: list[dict] = self._load_log()
        self.context_manager = ContextManager(config.context)
        self.sync_guard = SyncGuard(config.guard)
        self.async_guard = AsyncGuard(backend, config.guard)
        self.background = BackgroundWorker(max_workers=2)
        self.gen_params = GenParams(
            temperature=config.gen.temperature,
            top_p=config.gen.top_p,
            max_tokens=config.gen.max_tokens,
            repeat_penalty=config.gen.repeat_penalty,
        )
        self.last_flags: list[str] = []
        self.last_sync_issues: list[str] = []

    def _path(self, name: str) -> Path:
        return self.session_dir / name

    def _load_log(self) -> list[dict]:
        log_path = self._path("log.jsonl")
        if not log_path.exists():
            return []
        entries: list[dict] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and "role" in item and "content" in item:
                entries.append({"role": str(item["role"]), "content": str(item["content"])})
        return entries

    def _append_log(self, entry: dict) -> None:
        record = dict(entry)
        record["ts"] = datetime.now().isoformat(timespec="seconds")
        with open(self._path("log.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _rewrite_log(self) -> None:
        lines = [json.dumps({**entry, "ts": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) for entry in self.history]
        self._path("log.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def set_escalation(self, wanted: bool) -> None:
        self.state.user_wants_escalation = bool(wanted)
        self.state.save(self._path("state.json"))

    def start_new_session(self, session_id: str | None = None) -> None:
        new_id = session_id or datetime.now().strftime("session-%Y%m%d-%H%M%S")
        self.config.session_id = new_id
        self.session_dir = Path(self.config.saves_dir) / new_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.state = StoryState()
        self.memory = Memory()
        self.history = []
        self.last_flags = []
        self.last_sync_issues = []

    def send(self, user_input: str) -> Iterator[str]:
        user_input = (user_input or "").strip()
        if not user_input:
            return
        self.background.wait_for("state_update", timeout=30)
        entry = {"role": "user", "content": user_input}
        self.history.append(entry)
        self._append_log(entry)
        yield from self._generate_reply(user_input, pre_corrections=list(self.last_flags))

    def regenerate(self) -> Iterator[str]:
        while self.history and self.history[-1]["role"] != "user":
            self.history.pop()
        if not self.history:
            return
        self._rewrite_log()
        user_input = self.history[-1]["content"]
        yield from self._generate_reply(user_input, pre_corrections=list(self.last_flags))

    def _generate_reply(self, user_input: str, pre_corrections: list[str] | None = None) -> Iterator[str]:
        bundle = self.context_manager.build(
            state=self.state,
            memory=self.memory,
            rulebook=self.rulebook,
            history=self.history[:-1],
            user_input=user_input,
        )
        corrections = [c for c in (pre_corrections or []) if c]
        guard_enabled = self.config.guard.enabled
        attempt = 0
        final_text = ""
        issues: list[str] = []
        while True:
            if attempt > 0:
                yield "\n\n（Self Guard: 問題を検出したため再生成します）\n\n"
            messages = build_messages(bundle, corrections or None)
            chunks: list[str] = []
            for chunk in self.backend.stream(messages, self.gen_params):
                chunks.append(chunk)
                yield chunk
            final_text = "".join(chunks).strip()
            guard_result = (
                self.sync_guard.check(final_text, self.state, self.rulebook, user_input)
                if guard_enabled
                else GuardResult()
            )
            ok, issues = validate_output(final_text, guard_result)
            if ok or attempt >= self.config.guard.max_retry:
                break
            attempt += 1
            corrections = list(issues)
            if attempt >= self.config.guard.max_retry:
                corrections.append(FALLBACK_NOTE)
        if not final_text:
            final_text = EMPTY_REPLY_PLACEHOLDER
            yield final_text
        entry = {"role": "assistant", "content": final_text}
        self.history.append(entry)
        self._append_log(entry)
        self.state.turn += 1
        self.state.save(self._path("state.json"))
        self.memory.save(self._path("memory.json"))
        self.last_sync_issues = issues
        self._schedule_background(user_input, final_text)

    def _schedule_background(self, user_input: str, reply: str) -> None:
        exchange = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": reply},
        ]
        if self.config.guard.async_judge:
            self.background.submit("async_guard", self._job_async_guard, user_input, reply)
        if self.config.memory.facts_enabled:
            self.background.submit("facts", self._job_facts, exchange)
        self.background.submit("state_update", self._job_state_update, user_input, reply)
        self.background.submit("summary", self._job_summary)

    def _job_state_update(self, user_input: str, reply: str) -> None:
        content = state_update_prompt(self.state.to_dict(), user_input, reply)
        messages = [
            {"role": "system", "content": "あなたはJSONのみを出力する状態管理アシスタントです。"},
            {"role": "user", "content": content},
        ]
        params = GenParams(temperature=0.2, max_tokens=350)
        raw = self.backend.generate(messages, params)
        patch = extract_json_object(raw) or {}
        self.state.apply_patch(patch)
        self.state.save(self._path("state.json"))

    def _job_summary(self) -> None:
        window = self.config.memory.recent_window
        trigger = self.config.memory.summarize_trigger
        pending = len(self.history) - self.memory.summarized_until
        cut_point = len(self.history) - window
        if pending < trigger or cut_point <= self.memory.summarized_until:
            return
        older = self.history[self.memory.summarized_until : cut_point]
        new_summary = summarize_turns(self.backend, self.memory.summary, older)
        if new_summary:
            self.memory.summary = new_summary
            self.memory.summarized_until = cut_point
            self.memory.save(self._path("memory.json"))

    def _job_facts(self, exchange: list[dict]) -> None:
        texts = extract_facts(self.backend, exchange)
        for text in texts:
            kind = "event" if _EVENT_PATTERN.search(text) else "fact"
            self.memory.add_fact(text, kind=kind, turn=self.state.turn)
        self.memory.save(self._path("memory.json"))

    def _job_async_guard(self, user_input: str, reply: str) -> None:
        result = self.async_guard.analyze(user_input, reply, self.state, self.rulebook)
        flags = [f"{issue.type}: {issue.detail}" for issue in result.issues]
        self.last_flags = flags
        payload = {
            "turn": self.state.turn,
            "ok": result.ok,
            "flags": flags,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._path("flags.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def wait_background(self, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        for name in ("state_update", "summary", "facts", "async_guard"):
            remaining = max(deadline - time.time(), 0.1)
            self.background.wait_for(name, timeout=remaining)

    def shutdown(self) -> None:
        self.background.shutdown(wait=False)
        self.backend.unload()
