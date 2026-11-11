#!/usr/bin/env python3
"""Job Search Full-Ops Agent: validate config, profile and CV content files against their JSON Schemas.

Onboarding runs this before writing files ("validate before writing"), and the run pipeline runs it at the start.
The schema is picked from the file name, or set it with --kind.

Usage:
  python tools/validate.py                                   # config.json + user_profile.json if present
  python tools/validate.py .onboarding_profile_draft.json --kind user_profile
  python tools/validate.py runs/cv_*.json --kind cv_content
Exit codes: 0 = all valid, 1 = validation errors, 2 = usage problem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = {
    "config": ROOT / "schemas" / "config.schema.json",
    "user_profile": ROOT / "schemas" / "user_profile.schema.json",
    "cv_content": ROOT / "schemas" / "cv_content.schema.json",
}


def guess_kind(path: Path) -> str | None:
    name = path.name.lower()
    if "config" in name:
        return "config"
    if "profile" in name:
        return "user_profile"
    if name.startswith("cv_") or "cv_content" in name:
        return "cv_content"
    return None


def validate(path: Path, kind: str) -> list[str]:
    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMAS[kind].read_text(encoding="utf-8"))
    data = json.loads(path.read_text(encoding="utf-8"))
    errs = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '(top level)'}: {e.message}" for e in errs]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate agent files against their JSON Schemas.")
    ap.add_argument("files", nargs="*", help="files to check (default: config.json and user_profile.json)")
    ap.add_argument("--kind", choices=sorted(SCHEMAS), help="schema to use for all files")
    args = ap.parse_args(argv)
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print(json.dumps({"ok": False, "usage_error": "jsonschema is not installed: pip install -r requirements.txt"}))
        return 2
    files = [Path(f) for f in args.files] or [p for p in (Path("config.json"), Path("user_profile.json"))
                                              if p.exists()]
    if not files:
        print(json.dumps({"ok": False, "usage_error": "no files given and no config.json / user_profile.json here"}))
        return 2
    results, ok = {}, True
    for f in files:
        kind = args.kind or guess_kind(f)
        if not kind:
            print(json.dumps({"ok": False, "usage_error": f"can't tell which schema fits {f}; use --kind"}))
            return 2
        try:
            errors = validate(f, kind)
        except (OSError, json.JSONDecodeError) as e:
            errors = [f"cannot read: {e}"]
        results[str(f)] = {"schema": kind, "valid": not errors, "errors": errors[:20]}
        ok = ok and not errors
    print(json.dumps({"ok": ok, "files": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
