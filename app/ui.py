from __future__ import annotations

import json

import gradio as gr
import yaml

from engine.conversation import ConversationCore
from engine.rulebook import Rulebook


def _warning_markdown(core: ConversationCore) -> str:
    lines: list[str] = []
    for issue in core.last_sync_issues:
        lines.append(f"⚠️ 同期ガード: {issue}")
    for flag in core.last_flags:
        lines.append(f"⚠️ 非同期ガード: {flag}")
    if not lines:
        return ""
    return "\n".join(f"- {line}" for line in lines)


def _history_messages(core: ConversationCore) -> list[dict]:
    return [
        {"role": entry["role"], "content": entry["content"]}
        for entry in core.history
        if entry["role"] in ("user", "assistant")
    ]


def build_ui(core: ConversationCore) -> gr.Blocks:
    with gr.Blocks(title="TSUZURI") as demo:
        gr.Markdown("# TSUZURI\n**忘れない。壊さない。勝手に進めない。**")

        warning_box = gr.Markdown(label="Self Guard")

        chatbot = gr.Chatbot(height=460)

        with gr.Row():
            message = gr.Textbox(
                placeholder="メッセージを入力…",
                show_label=False,
                scale=10,
            )
            send_button = gr.Button("送信", variant="primary", scale=1)

        with gr.Row():
            regenerate_button = gr.Button("再生成")
            escalation_checkbox = gr.Checkbox(value=False, label="展開加速をリクエスト")
            new_session_button = gr.Button("新規セッション")

        with gr.Accordion("設定", open=False):
            with gr.Tabs():
                with gr.Tab("Story State"):
                    state_box = gr.Textbox(lines=14, label="state.json")
                    with gr.Row():
                        state_refresh = gr.Button("再読込")
                        state_apply = gr.Button("適用", variant="primary")
                with gr.Tab("Memory"):
                    memory_box = gr.Textbox(lines=14, label="memory.json")
                    with gr.Row():
                        memory_refresh = gr.Button("再読込")
                        memory_apply = gr.Button("適用", variant="primary")
                with gr.Tab("Rulebook"):
                    rulebook_box = gr.Textbox(lines=16, label="Rulebook YAML")
                    with gr.Row():
                        rulebook_refresh = gr.Button("再読込")
                        rulebook_apply = gr.Button("適用", variant="primary")
                with gr.Tab("生成パラメータ"):
                    temperature_slider = gr.Slider(0.0, 2.0, value=core.gen_params.temperature, step=0.05, label="temperature")
                    top_p_slider = gr.Slider(0.0, 1.0, value=core.gen_params.top_p, step=0.01, label="top_p")
                    max_tokens_slider = gr.Slider(64, 2048, value=core.gen_params.max_tokens, step=32, label="max_tokens")
                    repeat_penalty_slider = gr.Slider(1.0, 2.0, value=core.gen_params.repeat_penalty, step=0.01, label="repeat_penalty")
                with gr.Tab("Self Guard"):
                    guard_enabled = gr.Checkbox(value=core.config.guard.enabled, label="同期ガード有効")
                    async_guard_enabled = gr.Checkbox(value=core.config.guard.async_judge, label="非同期ガード有効")
                    max_retry_slider = gr.Slider(0, 5, value=core.config.guard.max_retry, step=1, label="max_retry")

        def respond(text: str, history: list, escalate: bool):
            text = (text or "").strip()
            if not text:
                yield history, _warning_markdown(core)
                return
            core.set_escalation(bool(escalate))
            history = list(history) + [{"role": "user", "content": text}]
            working_history = history + [{"role": "assistant", "content": ""}]
            buffer = ""
            for chunk in core.send(text):
                buffer += chunk
                working_history[-1]["content"] = buffer
                yield working_history, _warning_markdown(core)
            yield working_history, _warning_markdown(core)

        def do_regenerate(history: list):
            if not any(entry["role"] == "user" for entry in core.history):
                yield history, _warning_markdown(core)
                return
            buffer = ""
            for chunk in core.regenerate():
                buffer += chunk
                yield _history_messages(core)[:-1] + [{"role": "assistant", "content": buffer}], _warning_markdown(core)
            yield _history_messages(core), _warning_markdown(core)

        def start_new_session():
            core.start_new_session()
            return [], ""

        def load_state_json() -> str:
            return json.dumps(core.state.to_dict(), ensure_ascii=False, indent=2)

        def apply_state_json(text: str) -> str:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                return f"JSONエラー: {exc}"
            from engine.story_state import StoryState

            core.state = StoryState.from_dict(data)
            core.state.save(core._path("state.json"))
            return "Story State を更新しました。"

        def load_memory_json() -> str:
            return json.dumps(core.memory.to_dict(), ensure_ascii=False, indent=2)

        def apply_memory_json(text: str) -> str:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                return f"JSONエラー: {exc}"
            from engine.memory import Memory

            core.memory = Memory.from_dict(data)
            core.memory.save(core._path("memory.json"))
            return "Memory を更新しました。"

        def load_rulebook_yaml() -> str:
            data: dict = {
                "characters": [],
                "world": core.rulebook.world,
                "rules": core.rulebook.rules,
            }
            for character in core.rulebook.characters:
                item: dict = {"name": character.name}
                if character.personality:
                    item["personality"] = character.personality
                if character.relationships:
                    item["relationships"] = character.relationships
                if character.notes:
                    item["notes"] = character.notes
                data["characters"].append(item)
            return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

        def apply_rulebook_yaml(text: str) -> str:
            try:
                data = yaml.safe_load(text)
                core.rulebook = Rulebook.from_dict(data)
            except yaml.YAMLError as exc:
                return f"YAMLエラー: {exc}"
            return "Rulebook を更新しました。"

        send_button.click(
            respond,
            inputs=[message, chatbot, escalation_checkbox],
            outputs=[chatbot, warning_box],
        ).then(lambda: "", inputs=None, outputs=[message])

        message.submit(
            respond,
            inputs=[message, chatbot, escalation_checkbox],
            outputs=[chatbot, warning_box],
        ).then(lambda: "", inputs=None, outputs=[message])

        regenerate_button.click(do_regenerate, inputs=[chatbot], outputs=[chatbot, warning_box])
        new_session_button.click(start_new_session, inputs=None, outputs=[chatbot, warning_box])

        state_refresh.click(load_state_json, inputs=None, outputs=[state_box])
        state_apply.click(apply_state_json, inputs=[state_box], outputs=None)
        memory_refresh.click(load_memory_json, inputs=None, outputs=[memory_box])
        memory_apply.click(apply_memory_json, inputs=[memory_box], outputs=None)
        rulebook_refresh.click(load_rulebook_yaml, inputs=None, outputs=[rulebook_box])
        rulebook_apply.click(apply_rulebook_yaml, inputs=[rulebook_box], outputs=None)

        temperature_slider.change(lambda v: setattr(core.gen_params, "temperature", float(v)), inputs=[temperature_slider], outputs=None)
        top_p_slider.change(lambda v: setattr(core.gen_params, "top_p", float(v)), inputs=[top_p_slider], outputs=None)
        max_tokens_slider.change(lambda v: setattr(core.gen_params, "max_tokens", int(v)), inputs=[max_tokens_slider], outputs=None)
        repeat_penalty_slider.change(lambda v: setattr(core.gen_params, "repeat_penalty", float(v)), inputs=[repeat_penalty_slider], outputs=None)
        guard_enabled.change(lambda v: setattr(core.config.guard, "enabled", bool(v)), inputs=[guard_enabled], outputs=None)
        async_guard_enabled.change(lambda v: setattr(core.config.guard, "async_judge", bool(v)), inputs=[async_guard_enabled], outputs=None)
        max_retry_slider.change(lambda v: setattr(core.config.guard, "max_retry", int(v)), inputs=[max_retry_slider], outputs=None)

    return demo
