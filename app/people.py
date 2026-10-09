"""친구 이름·별명 → Discord ID. 목록은 data/people.json (커밋하지 않음)."""
import json
import os
import re
from pathlib import Path

PEOPLE_FILE = Path(os.environ.get("PEOPLE_FILE", "data/people.json"))


def load() -> list[dict]:
    if not PEOPLE_FILE.exists():
        return []
    return json.loads(PEOPLE_FILE.read_text(encoding="utf-8"))["people"]


def names_for_prompt() -> str:
    return ", ".join(f"{p['name']}({', '.join(p.get('aliases', []))})" for p in load()) or "없음"


def resolve(who: str) -> str | None:
    """'<@123>' 멘션이나 등록된 이름·별명을 Discord ID로 바꾼다. 모르면 None."""
    mention = re.fullmatch(r"<@!?(\d+)>", who.strip())
    if mention:
        return mention.group(1)
    who = who.strip().removesuffix("님")
    for person in load():
        if who == person["name"] or who in person.get("aliases", []):
            return person["discord_id"]
    return None
