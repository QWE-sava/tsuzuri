# Self Guard / 自警アーキテクチャ

生成内容をモデルの外側から検査し、物語の一貫性を守る。

## 二層構造

### 同期ガード（出力前・ブロッキング）

`engine/self_guard.py` `SyncGuard`

| 検査 | 内容 |
|---|---|
| 乱入検出 | 「見知らぬ」「謎の」「突然現れた」等のマーカー（`guard.intruder_markers` で設定可） |
| 不穏化検出 | `user_wants_escalation=false` かつ緊張度 < 閾値 のとき、銃声・爆発等のキーワードを遮断 |
| 書式検査 | 空出力・文字反復・メタ発言 |

違反時は修正指示を添えて再生成。上限は `guard.max_retry`（初期2）。上限到達時はフォールバック指示付きで最終生成を採用する。

同期ガードはルールベースのみ（ミリ秒級）なので、ストリーミング表示の体感速度は劣化しない。

### 非同期ガード（表示後・裏側）

`AsyncGuard` がバックグラウンドスレッドで同一LLMにJSON判定を依頼:

1. キャラクター矛盾
2. 世界設定矛盾
3. 時系列矛盾
4. 場所矛盾
5. 不要な第三者登場
6. 不要なイベント発生
7. 不穏化
8. 既出イベントの重複

```json
{"ok": false, "violations": [{"type": "intrusion", "detail": "Rulebook外の人物が登場"}]}
```

- 判定失敗（JSONパース不能）時はフェイルオープンで通過させる
- 検出結果は UI警告 / `flags.json` / **次ターンのプロンプト制約** に反映され、問題の拡散を防ぐ

## 展開加速の分離管理

Story State は以下を独立して保持する:

```text
story_activity          物語の動きの量
story_tension           緊張度
user_wants_escalation   ユーザーの加速要求（UIチェックボックス）
```

`activity=0.2, tension=0.1, user_wants_escalation=false` のとき、
**「物語が動いていないから事件を起こす」ことをシステム命令とガードの両面で禁止する。**

## 再生成フロー

```text
生成 → SyncGuard
        ├─ OK → 出力確定 → Background（非同期判定へ）
        └─ NG → 修正指示 + 再生成（max_retry 回）
                    └─ 上限到達 → フォールバック指示付き生成
```
