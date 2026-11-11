#!/usr/bin/env python3
"""Job Search Full-Ops Agent: privacy check before you publish or commit.

Reads YOUR personal data from local files (user_profile.json, config.json, .env, an old CV, any JSON/text file you
pass), builds a list of personal terms (name, email, phone, LinkedIn/GitHub URLs, employers, city, API keys,
Drive IDs, plus anything in .privacy_terms), and searches every file that would be published for them.

Nothing is sent anywhere, and findings are printed masked (e.g. "ol***") unless you pass --show.

Usage:
  python tools/privacy_check.py                       # uses user_profile.json, config.json, .env, .privacy_terms
  python tools/privacy_check.py --source ~/old/profile.json --source ~/old/.env --source ~/old/CV.txt
  python tools/privacy_check.py --allow "LICENSE,README.md:Jane Doe"   # a term that is public on purpose

Exit codes: 0 = clean, 1 = personal data found, 2 = usage problem.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
PROFILE_URL_RE = re.compile(r"(?:https?://)?(?:[\w-]+\.)?(?:linkedin\.com/in|github\.com|gitlab\.com)/[\w%.-]+", re.I)

# Keys whose values identify the person (matched at any depth unless listed in TOP_LEVEL_ONLY).
PERSONAL_KEYS = {"full_name", "email", "phone", "contact", "linkedin", "linkedin_url", "github", "portfolio",
                 "company", "city", "recipients", "address", "root_folder_id", "cv_subfolder_id",
                 "tracking_spreadsheet_id", "drive_folder_id", "institution", "university", "school"}
ORG_KINDS = {"company", "institution", "university", "school"}
LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:sp\.?\s*z\s*o\.?\s*o\.?|sp\.?\s*j\.?|s\.?\s*a\.?|gmbh(?:\s*&\s*co\.?\s*kg)?|ag|kg|se|ltd\.?|limited|llc|"
    r"inc\.?|corp\.?|plc|b\.?\s*v\.?|n\.?\s*v\.?|sas|sarl|s\.?\s*r\.?\s*o\.?|s\.?\s*r\.?\s*l\.?|s\.?\s*p\.?\s*a\.?|lda|oy|ab|"
    r"a/s|aps|kft|co\.?|group|holding)\.?$", re.I)
GENERIC_WORDS = {"global", "international", "digital", "software", "solutions", "services", "technologies", "technology",
                 "consulting", "polska", "poland", "europe", "group", "systems", "business", "university", "college",
                 "school", "institute", "national", "academy", "faculty", "bank", "agency", "partners", "company"}
TOP_LEVEL_ONLY = {"name"}            # "name" is personal at the top of a profile, generic elsewhere (board names)
SEPARATORS = re.compile(r"\s*(?:•|\||;|·)\s*")
EXAMPLE_VALUES = {"you@example.com", "alex example", "alex.example@example.com", "example gmbh"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".gs", ".js", ".ts", ".yml", ".yaml", ".toml", ".cfg", ".ini",
                 ".html", ".csv", ".tsv", ".example", ".gitignore", ""}


def fold(s: str) -> str:
    """Lower-case and strip accents so 'München' matches 'munchen'."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ł", "l")


def short_names(name: str) -> list[str]:
    """'Northwind Sp. z o.o.' -> ['Northwind']; 'Fabrikam Electric' -> ['Fabrikam']. Short forms are how
    employers and universities are usually written in CVs and READMEs."""
    out, cur = [], name.strip()
    while True:
        new = LEGAL_SUFFIX.sub("", cur).strip(" ,.")
        if new == cur or not new:
            break
        cur = new
    if cur != name.strip():
        out.append(cur)
    words = re.findall(r"[^\W\d_][\w'&-]*", cur)
    if len(words) > 1 and len(words[0]) >= 6 and fold(words[0]) not in GENERIC_WORDS:
        out.append(words[0])
    return out


def _add(terms: dict, value: str, kind: str):
    value = (value or "").strip().strip(",.")
    if len(value) < 4 or fold(value) in EXAMPLE_VALUES:
        return
    terms.setdefault(value, kind)
    if kind in ORG_KINDS:
        for short in short_names(value):
            if len(short) >= 4 and fold(short) not in EXAMPLE_VALUES:
                terms.setdefault(short, f"{kind} (short name)")


def harvest_text(text: str, terms: dict):
    for m in EMAIL_RE.findall(text):
        _add(terms, m, "email")
    for m in PHONE_RE.findall(text):
        if len(re.sub(r"\D", "", m)) >= 9:
            _add(terms, m, "phone")
            _add(terms, re.sub(r"\D", "", m), "phone")
    for m in PROFILE_URL_RE.findall(text):
        _add(terms, re.sub(r"^https?://(www\.)?", "", m).rstrip("/"), "profile url")


def harvest_json(obj, terms: dict, depth=0, parent=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = k.lower()
            # "api_key_env": "FIRECRAWL_API_KEY" names an environment variable - that is not a secret.
            if re.search(r"token|secret|password|api[_-]?key|authorization", key) and isinstance(v, str) \
                    and len(v) >= 8 and not key.endswith("_env"):
                terms.setdefault(v.replace("Bearer ", "").strip(), f"secret ({k})")
            personal = key in PERSONAL_KEYS or (key in TOP_LEVEL_ONLY and (depth == 0 or parent in
                                                                          ("personal", "header")))
            if personal:
                values = v if isinstance(v, list) else [v]
                for val in values:
                    if isinstance(val, str):
                        if key == "contact":          # "City, Country • phone • email • LinkedIn"
                            parts = SEPARATORS.split(val)
                            if parts:
                                _add(terms, parts[0].split(",")[0], "city")
                        else:
                            _add(terms, val, key)
            harvest_json(v, terms, depth + 1, key)
    elif isinstance(obj, list):
        for v in obj:
            harvest_json(v, terms, depth + 1, parent)
    elif isinstance(obj, str):
        harvest_text(obj, terms)


def harvest_env(text: str, terms: dict):
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        if len(val) >= 8 and val.lower() not in ("smtp.gmail.com",) and not val.isdigit():
            terms.setdefault(val, f"secret ({key.strip()})")
        harvest_text(val, terms)


def load_terms(sources: list[Path], terms_file: Path | None) -> dict:
    terms: dict = {}
    for src in sources:
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise SystemExit(f"cannot read {src}: {e}")
        if src.suffix == ".json":
            try:
                harvest_json(json.loads(text), terms)
            except json.JSONDecodeError:
                harvest_text(text, terms)
        elif src.name.startswith(".env") and not src.name.endswith(".example"):
            harvest_env(text, terms)
        else:
            harvest_text(text, terms)
    if terms_file and terms_file.exists():
        for line in terms_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                _add(terms, line.strip(), "custom term")
    return terms


# --- files that would be published ------------------------------------------------------------------------------
def gitignore_patterns(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.exists():
        return []
    return [l.strip() for l in gi.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def is_ignored(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    for p in patterns:
        p = p.lstrip("/")
        if p.endswith("/"):
            if p.rstrip("/") in parts[:-1] or any(fnmatch.fnmatch(x, p.rstrip("/")) for x in parts[:-1]):
                return True
        elif fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(parts[-1], p):
            return True
    return False


def publishable_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, check=True).stdout
        return [root / l for l in out.splitlines() if l]
    except (OSError, subprocess.CalledProcessError):
        pass
    patterns = gitignore_patterns(root)
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if not is_ignored(p.relative_to(root).as_posix(), patterns):
                files.append(p)
    return files


def mask(term: str) -> str:
    return term[:2] + "***" + (f"({len(term)} chars)" if len(term) > 6 else "")


DIGIT_RUN = re.compile(r"\+?\d[\d\s().\-/]{5,}\d")


def phone_keys(term: str) -> set[str]:
    """Digits of a phone number, with and without the country code, so '600-100-200' matches '+48 600 100 200'."""
    d = re.sub(r"\D", "", term)
    return {k for k in (d, d[-9:], d[-8:] if len(d) >= 10 else "") if len(k) >= 7}


def scan(root: Path, terms: dict, allow: dict[str, set[str]], show: bool) -> list[str]:
    findings = []
    folded = {t: fold(t) for t in terms}
    phones = {t: phone_keys(t) for t, kind in terms.items() if kind.startswith("phone")}
    for path in sorted(publishable_files(root)):
        if path.suffix.lower() not in TEXT_SUFFIXES and not path.name.startswith(".") and path.name != "LICENSE":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            fl = fold(line)
            runs = [re.sub(r"\D", "", r) for r in DIGIT_RUN.findall(line)] if phones else []
            seen_line = set()
            for term, ft in folded.items():
                if term in phones:
                    hit = any(k in r for r in runs for k in phones[term])
                elif len(ft) < 6:
                    hit = re.search(rf"(?<![\w]){re.escape(ft)}(?![\w])", fl)
                else:
                    hit = ft in fl
                if hit and rel not in allow.get(term, set()):
                    shown = term if show and not terms[term].startswith("secret") else mask(term)
                    entry = f"{rel}:{n}: {terms[term]}: {shown}"
                    if (terms[term], shown) not in seen_line:
                        seen_line.add((terms[term], shown))
                        findings.append(entry)
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find your personal data in files that would be published.")
    ap.add_argument("--root", default=".", help="repository to scan (default: current folder)")
    ap.add_argument("--source", action="append", default=[], help="file holding personal data (repeatable)")
    ap.add_argument("--terms", default=".privacy_terms", help="extra terms, one per line (gitignored)")
    ap.add_argument("--allow", action="append", default=[], help='"FILE1,FILE2:term" that is public on purpose')
    ap.add_argument("--show", action="store_true", help="print matched terms in full (never secrets)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    sources = [Path(s).expanduser() for s in args.source]
    if not sources:
        sources = [root / f for f in ("user_profile.json", "config.json", ".env") if (root / f).exists()]
    if not sources and not (root / args.terms).exists():
        print("No personal data sources found. Pass --source <file> (your profile, .env, old CV) or create "
              ".privacy_terms.", file=sys.stderr)
        return 2
    terms = load_terms(sources, root / args.terms)
    allow: dict[str, set[str]] = {}
    for a in args.allow:
        files, _, term = a.partition(":")
        allow.setdefault(term, set()).update(f.strip() for f in files.split(","))
        terms.setdefault(term, "allowed term")

    findings = scan(root, terms, allow, args.show)
    print(f"Checked {len(terms)} personal terms from {len(sources)} source file(s).")
    if findings:
        print(f"Personal data found in files that would be published ({len(findings)}):")
        print("\n".join("  " + f for f in findings))
        return 1
    print("Clean: no personal data in files that would be published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
