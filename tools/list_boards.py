#!/usr/bin/env python3
"""Job Search Full-Ops Agent: which job boards are searched for a country.

Onboarding uses this to show the user the default boards per target country before asking which local boards to
add. The run pipeline uses the same rules (SKILL.md Step 3).

Usage:
  .venv/bin/python tools/list_boards.py PT [DE ...] [--config config.json] [--remote] [--languages en pt]
--languages accepts ISO codes or English names, separated by spaces or commas, in any case: "en pt", "en,pt",
"EN, PT" and "English Portuguese" all work. An unknown language is an error (exit 2), never a silent filter.
Prints JSON per country: always-on boards, local boards for that country (catalog + user-added), pan-European
boards, and remote boards (only with --remote).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ISO 639-1 codes and English names of the languages used by European job boards.
LANGUAGES = {
    "en": "english", "de": "german", "fr": "french", "es": "spanish", "pt": "portuguese", "it": "italian",
    "nl": "dutch", "pl": "polish", "cs": "czech", "sk": "slovak", "hu": "hungarian", "ro": "romanian",
    "bg": "bulgarian", "hr": "croatian", "sl": "slovenian", "sr": "serbian", "el": "greek", "da": "danish",
    "sv": "swedish", "no": "norwegian", "nb": "norwegian bokmal", "fi": "finnish", "et": "estonian", "lv": "latvian",
    "lt": "lithuanian", "uk": "ukrainian", "ru": "russian", "tr": "turkish", "ga": "irish", "mt": "maltese",
    "lb": "luxembourgish", "is": "icelandic", "ca": "catalan",
}
_BY_NAME = {name: code for code, name in LANGUAGES.items()}
_BY_NAME.update({"czech": "cs", "norwegian": "no", "bokmal": "nb", "castilian": "es", "flemish": "nl"})


class UsageError(Exception):
    pass


def parse_languages(values: list[str] | None) -> set[str] | None:
    """Turn ["en,pt"], ["EN", "PT"], ["English Portuguese"] … into {"en", "pt"}. Unknown values raise UsageError."""
    if not values:
        return None
    out, unknown = set(), []
    for raw in values:
        for token in re.split(r"[\s,;/]+", raw.strip()):
            tok = token.strip().lower()
            if not tok:
                continue
            if tok in LANGUAGES:
                out.add(tok)
            elif tok in _BY_NAME:
                out.add(_BY_NAME[tok])
            else:
                unknown.append(token)
    if unknown:
        raise UsageError(f"unknown language(s): {', '.join(unknown)}. Use ISO codes like 'en pt' or names like "
                         f"'English Portuguese'.")
    return out or None


def load_boards(config_path: str | None) -> list[dict]:
    path = Path(config_path) if config_path and Path(config_path).exists() else ROOT / "config.example.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    s = cfg["search"]
    return [b for b in s.get("boards", []) + s.get("custom_boards", []) if b.get("enabled")]


def boards_for(country: str, boards: list[dict], remote: bool = False, languages: set[str] | None = None) -> dict:
    country = country.upper()
    out = {"country": country, "always_on": [], "local": [], "pan_european": [], "remote": [],
           "skipped_language": []}
    for b in boards:
        entry = {"id": b["id"], "name": b["name"], "added_by": b.get("added_by", "catalog")}
        langs = set(b.get("listing_languages") or ["en"])
        if b.get("always_on"):
            out["always_on"].append(entry)
            continue
        if languages and not (langs & languages):
            if country in b.get("countries", []) or "*" in b.get("countries", []):
                out["skipped_language"].append(entry)
            continue
        cov, countries = b.get("coverage"), b.get("countries", [])
        if cov == "country" and country in countries:
            out["local"].append(entry)
        elif cov == "pan_eu" and ("*" in countries or country in countries):
            out["pan_european"].append(entry)
        elif cov in ("remote_eu", "remote_global") and remote:
            out["remote"].append(entry)
    if not out["local"] and not out["pan_european"]:
        reason = (f"{len(out['skipped_language'])} board(s) skipped because none of their listing languages is in "
                  f"{sorted(languages)}" if out["skipped_language"] else "the catalog has no boards for this country")
        out["warning"] = (f"{country}: only the always-on sources (LinkedIn, web search) will be searched; {reason}. "
                          f"Check the languages, or ask the user for local job sites.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List the job boards searched for each country.")
    ap.add_argument("countries", nargs="+", help="ISO country codes, e.g. PT DE")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--remote", action="store_true", help="include remote-first boards")
    ap.add_argument("--languages", nargs="*", help="ISO 639-1 languages the user works in (skips other boards)")
    args = ap.parse_args(argv)
    boards = load_boards(args.config)
    try:
        langs = parse_languages(args.languages)
    except UsageError as e:
        print(json.dumps({"usage_error": str(e)}))
        return 2
    print(json.dumps([boards_for(c, boards, args.remote, langs) for c in args.countries], ensure_ascii=False,
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
