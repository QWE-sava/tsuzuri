from __future__ import annotations

from engine.rulebook import Character, Rulebook


RULEBOOK_YAML = """
characters:
  - name: Alice
    personality:
      - 優しい
      - 人見知り
    relationships:
      user: 恋人
    notes: 猫が苦手
  - name: Bob
    personality:
      - 明るい
world:
  technology: modern
  supernatural: false
rules:
  - 明示されていない第三者を勝手に登場させない
  - キャラクターの性格を変更しない
"""


def test_load_yaml(tmp_path):
    path = tmp_path / "rulebook.yaml"
    path.write_text(RULEBOOK_YAML, encoding="utf-8")
    rulebook = Rulebook.load_yaml(path)
    assert rulebook.character_names == ["Alice", "Bob"]
    assert rulebook.characters[0].relationships["user"] == "恋人"
    assert len(rulebook.rules) == 2
    assert rulebook.world["supernatural"] is False


def test_mentioned_characters(tmp_path):
    path = tmp_path / "rulebook.yaml"
    path.write_text(RULEBOOK_YAML, encoding="utf-8")
    rulebook = Rulebook.load_yaml(path)
    found = rulebook.mentioned_characters("公園でAliceと会った")
    assert [c.name for c in found] == ["Alice"]
    assert rulebook.mentioned_characters("誰も登場しない") == []


def test_render_characters_filter(tmp_path):
    path = tmp_path / "rulebook.yaml"
    path.write_text(RULEBOOK_YAML, encoding="utf-8")
    rulebook = Rulebook.load_yaml(path)
    text_all = rulebook.render_characters()
    assert "Alice" in text_all and "Bob" in text_all
    text_filtered = rulebook.render_characters(["Alice"])
    assert "Alice" in text_filtered and "Bob" not in text_filtered


def test_from_dict_tolerates_missing_keys():
    rulebook = Rulebook.from_dict({"characters": [{"name": "Solo"}]})
    assert rulebook.character_names == ["Solo"]
    assert rulebook.rules == []
    empty = Rulebook.from_dict(None)
    assert empty.characters == []


def test_character_render_includes_notes():
    character = Character(name="Alice", personality=["優しい"], relationships={"user": "恋人"}, notes="猫が苦手")
    text = character.render()
    assert "優しい" in text and "猫が苦手" in text
