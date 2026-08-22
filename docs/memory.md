# Memory / 要約保持アーキテクチャ

過去ログ全件を毎回LLMへ入力しない。TSUZURIのメモリ階層:

```text
L0 現在のユーザー入力
L1 直近会話        → ContextManager が予算内で最新側から採用
L2 Story State     → engine/story_state.py
L3 長期記憶(fact)  → engine/memory.py
L4 重要イベント    → memory.facts の kind="event"
L5 Rulebook/世界設定
```

## 構成要素

### ローリング要約 (`memory.summary`)

- 直近 `recent_window`(初期8) メッセージより古い部分は生ログのまま保持しない
- 未要約メッセージが `summarize_trigger`(初期14) を超えると、バックグラウンドで古い区間を既存要約へ統合
- 統合後 `summarized_until` インデックスが進み、同じ区間を二度要約しない

### 長期記憶 (`memory.facts`)

- 各エントリ: `{id, text, kind: fact|event, turn, tags}`
- バックグラウンドジョブが直近やり取りから重要事実のみをJSON配列で抽出
- 重複テキストは登録されない

### 检索（MVP）

- 文字ユニグラム+バイグラム+分かち書き風トークンの重み付き一致スコア + 新しさボーナス
- 埋め込み検索は後続フェーズで差し替え可能（`Memory.relevant_facts()` を置換するだけ）

## 永続化

`saves/<session>/memory.json`

```json
{
  "summary": "二人は初めて出会ったカフェで…",
  "summarized_until": 24,
  "facts": [{"id": "a1b2c3d4", "text": "Aliceは猫が苦手", "kind": "fact", "turn": 3, "tags": []}]
}
```
