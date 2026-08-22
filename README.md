# TSUZURI

**忘れない。壊さない。勝手に進めない。**

TSUZURIは、小型LLMでも長時間の物語会話において「記憶喪失・設定崩壊・不要な乱入・急激な展開」を抑制し、ストーリー継続性を安定させるOSS AI Story Engineです。

> 巨大なモデルにすべてを記憶させるのではなく、モデルの外側に「記憶・状態・ルール・自警」を構築する。

## 解決する問題

| 優先度 | 問題 |
|---|---|
| P0 | キャラクター設定・人間関係・現在状況の忘却 / 過去イベントの再発 / 不要な第三者の乱入 / 平穏への事件投入 / 意図しない急展開 |
| P1 | 性格崩壊 / 世界設定矛盾 / 時系列矛盾 / コンテキスト肥大化による情報埋没 |

## アーキテクチャ

```text
Gradio UI
   │
Conversation Core ── Background Jobs（State更新/要約/Memory整理/自警分析）
   │
Memory │ Rulebook │ Story State
   │
Context Manager（トークン予算内で必要情報だけ選別）
   │
Prompt Builder → Model Backend（llama-server / OpenAI互換）
   │
Output Validator + Self Guard（同期: ルール / 非同期: LLM判定）
```

設計原則の要点:

- 過去ログを無条件に全投入しない（L0〜L5のレイヤで必要部分のみ）
- **平穏＝停滞ではない。** 活動度が低いことを理由に事件を発生させない
- ユーザーが要求していない展開加速をブロックする（`user_wants_escalation` 分離管理）
- モデルは交換可能（OpenAI互換APIなら何でも接続可）

## クイックスタート

### Google Colab（推奨）

`notebooks/colab.ipynb` を開き、ランタイムを **T4 GPU** に変更してすべてのセルを実行するだけです。
中身は次の1セルのみ:

```python
REPO_URL = "https://github.com/QWE-sava/tsuzuri.git"
!git clone -q $REPO_URL tsuzuri
%cd tsuzuri
!pip install -q -r requirements.txt
!python app/server.py --share --auto-setup --rulebook examples/modern.yaml
```

`--auto-setup` が llama-server バイナリ（GitHubリリース取得、無ければソースビルド）と
GGUFモデルを自動準備します。初回は数分〜10分程度かかります。

### ローカル（既存サーバーに接続）

```bash
pip install -r requirements.txt

# llama-server 等の OpenAI互換サーバーを起動済みの場合
export TSUZURI_SERVER_URL=http://127.0.0.1:8080
python app/server.py --rulebook examples/modern.yaml
```

### ローカル（llama-server を TSUZURI から起動）

```bash
export TSUZURI_LLAMA_BIN=/path/to/llama-server
python app/server.py --gguf /path/to/gemma-4-E4B-it-Q4_K_M.gguf --rulebook examples/fantasy.yaml --share
```

`--gguf` 未指定の場合は `unsloth/gemma-4-E4B-it-GGUF` の `Q4_K_M` を自動ダウンロードします。

## 推奨モデル

**Gemma 4 E4B Q4_K_M**（約3GB VRAM）— T4 16GB で余裕を持って動作。`ModelBackend` 抽象により任意のOpenAI互換モデルへ交換可能です。

## Self Guard（二層構造）

| 層 | タイミング | 手法 |
|---|---|---|
| 同期ガード | 出力直前 | 乱入マーカー検出・不穏キーワード検出・書式検査。違反時は `max_retry`（初期2）回まで修正指示付きで再生成 |
| 非同期ガード | 表示後の裏側 | 同一LLMにJSON判定させ、性格矛盾・設定矛盾・時系列矛盾などを事後検査。結果はUI警告＋次ターンの制約として反映 |

ユーザーが読んでいる間にGPUを使って Story State 更新・要約圧縮・記憶抽出を行うため、次ターンの生成が高速に始まります（Background Processing）。

## 設定

`config.yaml`（例: `config.example.yaml`）または環境変数で上書きできます。

| 環境変数 | 内容 |
|---|---|
| `TSUZURI_SERVER_URL` | 接続先OpenAI互換サーバーURL |
| `TSUZURI_LLAMA_BIN` | llama-server バイナリパス |
| `TSUZURI_MODEL_PATH` | GGUFファイルパス |

セッションデータは `saves/<session_id>/` に保存されます（`state.json` / `memory.json` / `log.jsonl` / `flags.json`）。UIの「新規セッション」ボタンでリセットできます。

## 開発

```bash
pip install -r requirements.txt
pytest tests -q
```

テストはGPU不要（MockBackend使用）です。

詳細ドキュメント: [docs/architecture.md](docs/architecture.md) / [memory.md](docs/memory.md) / [rulebook.md](docs/rulebook.md) / [self_guard.md](docs/self_guard.md)

## ロードマップ

- [x] Phase 1 — Core（Conversation Core / Gradio / Backend / Story State）
- [x] Phase 2 — Memory（要約保持 / 長期Memory / Context Manager）
- [x] Phase 3 — Rulebook
- [x] Phase 4 — Self Guard（同期ルール+非同期LLM判定 / 再生成）
- [x] Phase 5 — Background Processing
- [ ] Phase 6 — Benchmark（Memory Retention / Intrusion Rate 等の定量比較）
- [ ] 埋め込み検索 / 自動Rulebook生成 / Webサービス化

## License

MIT
