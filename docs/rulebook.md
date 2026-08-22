# Rulebook

世界設定・キャラクター設定・物語ルールをYAMLで管理する。

```yaml
characters:
  - name: Alice
    personality:
      - 優しい
      - 人見知り
    relationships:
      user: 恋人
    notes: 猫が苦手

world:
  technology: modern
  supernatural: false

rules:
  - 明示されていない第三者を勝手に登場させない
  - キャラクターの性格を変更しない
  - 平穏な展開を停滞と判断しない
  - ユーザーの意図しない急展開を発生させない
```

サンプル: `examples/school.yaml` / `examples/fantasy.yaml` / `examples/modern.yaml`

## プロンプトへの投入

`ContextManager` が毎ターン以下を選別して投入する:

- **キャラクター設定**: 直近会話とユーザー入力に名前が登場したキャラのみ（未検出時は主要4名）
- **世界設定・物語ルール**: 常時（小型のため）

## 優先順位

System > Safety > Story State > Rulebook > Memory > Conversation > 自由生成

システム指示（乱入禁止・平穏維持等のアーキテクチャ原則）は常に最上位。Rulebookはそれに次ぐ拘束力でプロンプトに埋め込まれる。

## 実行中の編集

Gradio UI「設定 → Rulebook」タブからYAMLを直接編集・適用できる。次のターンから即反映される。
