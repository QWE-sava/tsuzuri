from __future__ import annotations

from dataclasses import dataclass, field

from .config import ContextConfig
from .memory import Memory
from .rulebook import Rulebook
from .story_state import StoryState

LAYER_SUMMARY = "summary"
LAYER_INPUT = "input"
LAYER_RECENT = "recent"
LAYER_STATE = "state"
LAYER_MEMORY = "memory"
LAYER_EVENTS = "events"
LAYER_RULES = "rules"

PROMPT_OVERHEAD_TOKENS = 256


def estimate_tokens(text: str, chars_per_token: float = 1.5) -> int:
    return max(1, round(len(text or "") / max(chars_per_token, 0.1)))


@dataclass
class ContextBundle:
    blocks: list[tuple[str, str]] = field(default_factory=list)
    recent_messages: list[dict] = field(default_factory=list)
    user_input: str = ""
    total_tokens: int = 0

    def block_text(self, layer: str) -> str:
        for name, text in self.blocks:
            if name == layer:
                return text
        return ""


class ContextManager:
    def __init__(self, config: ContextConfig | None = None) -> None:
        self.config = config or ContextConfig()

    def _relevant_names(self, rulebook: Rulebook, recent_messages: list[dict], user_input: str) -> list[str]:
        scan = user_input + "\n" + "\n".join(m["content"] for m in recent_messages[-6:])
        names = [character.name for character in rulebook.mentioned_characters(scan)]
        if not names:
            names = rulebook.character_names[:4]
        return names

    def build(
        self,
        state: StoryState,
        memory: Memory,
        rulebook: Rulebook,
        history: list[dict],
        user_input: str,
    ) -> ContextBundle:
        cfg = self.config
        est = lambda text: estimate_tokens(text, cfg.chars_per_token)

        rules_parts: list[str] = []
        world_text = rulebook.render_world()
        if world_text:
            rules_parts.append("【世界設定】\n" + world_text)
        rules_list = rulebook.render_rules()
        if rules_list:
            rules_parts.append("【物語ルール】\n" + rules_list)
        characters_text = rulebook.render_characters(self._relevant_names(rulebook, history[-8:], user_input))
        if characters_text:
            rules_parts.append("【キャラクター設定】\n" + characters_text)
        rules_text = "\n\n".join(rules_parts)

        state_text = state.to_prompt()

        query = user_input + "\n" + state.current_activity
        relevant = memory.relevant_facts(query, k=cfg.max_facts_in_context)
        memory_text = "\n".join(f"- {fact.text}" for fact in relevant)
        events_text = "\n".join(f"- {event}" for event in memory.events()[-5:])
        summary_text = memory.summary

        used = est(user_input) + est(state_text) + est(rules_text) + PROMPT_OVERHEAD_TOKENS
        remaining = cfg.token_budget - used

        bundle = ContextBundle(recent_messages=[], user_input=user_input)

        optional: list[tuple[str, str]] = []
        if summary_text:
            optional.append((LAYER_SUMMARY, "【これまでのあらすじ】\n" + summary_text))
        if memory_text:
            optional.append((LAYER_MEMORY, "【長期記憶】\n" + memory_text))
        if events_text:
            optional.append((LAYER_EVENTS, "【重要な過去イベント】\n" + events_text))

        for layer, text in optional:
            cost = est(text)
            if cost <= max(remaining, 150):
                remaining -= cost
                bundle.blocks.append((layer, text))

        bundle.blocks.append((LAYER_RULES, rules_text))
        bundle.blocks.append((LAYER_STATE, state_text))

        window_messages: list[dict] = []
        pool = [m for m in history if m["role"] in ("user", "assistant")]
        for message in reversed(pool):
            cost = est(message["content"])
            if cost > remaining:
                break
            remaining -= cost
            window_messages.insert(0, message)
        bundle.recent_messages = window_messages

        ordered_blocks: list[tuple[str, str]] = []
        layer_order = (LAYER_SUMMARY, LAYER_EVENTS, LAYER_MEMORY, LAYER_RULES, LAYER_STATE)
        for layer in layer_order:
            for item in bundle.blocks:
                if item[0] == layer:
                    ordered_blocks.append(item)
        bundle.blocks = ordered_blocks

        bundle.total_tokens = (
            sum(est(text) for _, text in bundle.blocks)
            + sum(est(m["content"]) for m in window_messages)
            + est(user_input)
        )
        return bundle
