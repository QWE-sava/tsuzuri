# アーキテクチャ

```text
┌──────────────────────────┐
│        Gradio UI         │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│    Conversation Core     │  engine/conversation.py
└────────────┬─────────────┘
             │
      ┌──────┼──────┐
      ▼      ▼      ▼
   Memory  Rulebook Story State
      │      │      │
      └──────┼──────┘
             ▼
      Context Manager          engine/context.py
             │
             ▼
       Prompt Builder           engine/prompt.py
             │
             ▼
       Model Backend            models/backend.py
             │
             ▼
       Output Validator         engine/validator.py
             │
       Self Guard (同期)        engine/self_guard.py
             │
       ┌─────┴─────┐
       ▼           ▼
    ユーザー      Background Jobs    engine/background.py
                State更新 / 要約 / Memory整理 / 自警分析(非同期)
```

## ターンの流れ

1. **待機** — 前ターンの重要バックグラウンドジョブ（Story State更新）が完了するまで最大30秒待つ。完了していれば即座に進む。
2. **Context構築** — `ContextManager` が L0入力/L1直近会話/L2State/L3長期記憶/L4重要イベント/L5Rulebook をトークン予算内で選別する。
3. **生成** — `PromptBuilder` の組んだメッセージで `ModelBackend.stream()` を実行し、UIへ逐次ストリーミング。
4. **検査** — 出力完了後、`Validator` + 同期Self Guardが検査。違反なら修正指示を付けて再生成（`max_retry` 回）。
5. **確定** — 履歴とファイルへ保存し、ユーザーへ表示済みのまま **裏で** バックグラウンドジョブを起動。

## Background Processing

ユーザーが回答を読んでいる間 = GPU遊休時間に:

- `state_update`: 直近やり取りから差分JSONパッチを抽出し Story State へ適用
- `summary`: 未要約部分が閾値を超えると古い会話をローリング要約へ統合
- `facts`: 長期記憶すべき事実をJSON配列で抽出
- `async_guard`: LLM判定による詳細な矛盾検査 → `flags.json` + 次ターンの制約

原則: **次の回答を先読みするのではなく、高速に生成できる状態を事前に作る。**

## モデル抽象化

`ModelBackend` は `generate()` / `stream()` の2メソッドのみを要求する。
`LlamaServerBackend` はOpenAI互換APIを話すため、llama-server 以外（vLLM, LM Studio, Ollama等）にもそのまま接続できる。
