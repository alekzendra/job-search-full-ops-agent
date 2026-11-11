"""Shared truthfulness rules used by tools/profile_check.py and tools/render_cv.py.

Keeping them in one place means the onboarding quality gate and the CV renderer always agree on what a "result
with a number" is, how never-claim rules are matched, and how many years of experience a profile shows.
"""
from __future__ import annotations

import re
from datetime import date

# ---------------------------------------------------------------------------------------------------------------------
# Result metrics
# ---------------------------------------------------------------------------------------------------------------------
# A bullet counts as a measured result only when a number is tied to a change, a share, money or scale. Bare digits
# don't count: "Q3 2023", "Python 3", "across 2 teams" and "a team of 5 engineers" are context, not results.
_UNIT = r"(?:%|x|k|m|bn|mln|hours?|hrs?|h|days?|weeks?|months?|min(?:ute)?s?|sec(?:ond)?s?|points?|pp|eur|usd|gbp|pln|chf|€|\$|£)"
_RESULT_PATTERNS = [
    r"\d+(?:[.,]\d+)?\s?%",                                                        # 27%, -67 %
    r"[€$£]\s?\d[\d.,]*\s?(?:k|m|bn|mln)?\b",                                      # €300k, $1.2m
    r"\b\d[\d.,]*\s?(?:k|m|bn|mln)?\s?(?:eur|usd|gbp|pln|chf|sek|dkk|nok|czk|ron)\b",
    r"\b\d+(?:[.,]\d+)?\s?x\b",                                                    # 3x faster
    r"\bfrom\s+[~≈]?\d[\d.,]*\+?(?:\s*\S+){0,3}?\s+to\s+[~≈]?\d",                 # from ~120 to ~35
    r"\d[\d.,]*\+?\s*\S{0,10}\s*(?:→|->)\s*[~≈]?\d",                               # 25 → 150+, 60 -> 20 min
    r"\b\d[\d.,]*\+\s?[a-z]",                                                      # 4,000+ accounts, 150+ users
    r"\b(?:cut|cutting|reduc\w*|decreas\w*|increas\w*|grew|grow\w*|rais\w*|lift\w*|boost\w*|improv\w*|sav(?:e|ed|ing)\w*"
    r"|shorten\w*|accelerat\w*|generat\w*|won|closed|drove|driving)\b[^.;]{0,40}?\b\d[\d.,]*\s*" + _UNIT + r"(?![a-z])",
    r"\b(?:doubled|tripled|quadrupled|halved)\b",
]
_RESULT_RE = re.compile("|".join(f"(?:{p})" for p in _RESULT_PATTERNS), re.IGNORECASE)

RESULT_UNITS = {"%", "eur", "usd", "gbp", "pln", "chf", "€", "$", "£", "x", "hours", "hour", "days", "day", "weeks",
                "week", "months", "month", "minutes", "min", "seconds", "points", "pp"}


def has_result_metric(text: str) -> bool:
    """True when the text states a measured result (change, share, money, scale), not just any digit."""
    return bool(_RESULT_RE.search(text or ""))


def structured_metric_is_result(m: dict) -> bool:
    """A metric entered in the profile counts as a result if it describes a change or share, has a baseline, or
    uses a result unit. Plain headcounts ('5 engineers', direction 'absolute') do not count."""
    if m.get("direction") in ("increase", "decrease", "share") or m.get("baseline") is not None:
        return True
    return str(m.get("unit", "")).strip().lower() in RESULT_UNITS


def achievement_has_metric(a: dict) -> bool:
    if any(structured_metric_is_result(m) for m in a.get("metrics", []) or []):
        return True
    return has_result_metric(a.get("cv_bullet") or a.get("statement") or "")


# ---------------------------------------------------------------------------------------------------------------------
# Never-claim matching: by meaning, not just exact wording
# ---------------------------------------------------------------------------------------------------------------------
_PEOPLE = [
    r"\b(?:lead|led|leading|manag\w*|head\w*|supervis\w*|oversaw|overs\w*|direct\w*|ran|run\w*)\s+(?:a\s+|the\s+|my\s+|"
    r"an?\s+\w+\s+)?team\s+of\s+\d+",
    r"\bteam\s+of\s+\d+\s+(?:direct\s+)?reports?\b",
    r"\bdirect\s+reports?\b",
    r"\bline[- ]manag\w*",
    r"\bpeople[- ]manag\w*",
    r"\bmanag\w*\s+(?:a\s+team\s+of\s+)?\d+\s+(?:engineers|developers|people|employees|staff|designers|analysts|reports"
    r"|specialists|consultants|testers|agents|managers)\b",
    r"\b(?:hired|recruited)\s+(?:and\s+\w+\s+)?(?:a\s+team|\d+)",
    r"\bteam\s+lead(?:er)?\b",
]
_BUDGET = [r"\bbudgets?\b"]
_PNL = [r"\bp\s?&\s?l\b", r"\bprofit\s+(?:and|&)\s+loss\b"]
_CONCEPTS = [
    (re.compile(r"people|line[- ]?manag|direct reports?|managing (?:a )?team|team (?:lead|management)|manag\w* people|"
                r"leading (?:a )?team|headcount|hiring"), _PEOPLE),
    (re.compile(r"budget"), _BUDGET),
    (re.compile(r"p\s?&\s?l|profit and loss"), _PNL),
]
_STOP = {"the", "and", "for", "with", "not", "but", "any", "all", "our", "was", "were", "from", "that", "this", "into",
         "over", "than", "more", "only", "own", "its", "his", "her", "their", "a", "an", "of", "to", "in", "on", "at",
         "or", "as", "by", "be", "is", "it", "did", "didn't", "never", "no"}


def _stems(text: str) -> list[str]:
    return [w[:5] for w in re.findall(r"[a-z&']+", text.lower()) if len(w) >= 3 and w not in _STOP]


def never_claim_hits(text: str, phrases: list[str]) -> list[tuple[str, str]]:
    """Return (phrase, matched text) for every never-claim rule the text breaks. Checks, in order: the exact phrase;
    built-in meanings for people management, budgets and P&L; and all the phrase's words appearing close together in
    any order and form ('people management' also catches 'managed people')."""
    hits = []
    low = (text or "").lower()
    tokens = re.findall(r"[a-z&']+", low)
    for phrase in phrases or []:
        p = (phrase or "").strip().lower()
        if not p:
            continue
        if p in low:
            hits.append((phrase, phrase))
            continue
        found = None
        for trigger, patterns in _CONCEPTS:
            if trigger.search(p):
                for pat in patterns:
                    m = re.search(pat, low)
                    if m:
                        found = m.group(0)
                        break
            if found:
                break
        if not found:
            stems = _stems(p)
            if len(stems) >= 2:
                window = 8
                for i in range(len(tokens)):
                    chunk = [t[:5] for t in tokens[i:i + window]]
                    if all(s in chunk for s in stems):
                        found = " ".join(tokens[i:i + window])
                        break
        if found:
            hits.append((phrase, found))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# Years of experience from role dates
# ---------------------------------------------------------------------------------------------------------------------
def _ym(s: str | None, today: date) -> date:
    if not s:
        return today
    y, m = s.split("-")[:2]
    return date(int(y), int(m), 1)


def experience_years(roles: list[dict], today: date | None = None, role_ids: set[str] | None = None) -> float:
    """Total years covered by the roles' date ranges (overlaps counted once; a missing end date means today)."""
    today = today or date.today()
    spans = []
    for r in roles:
        if role_ids and r.get("id") not in role_ids:
            continue
        if not r.get("start"):
            continue
        a, b = _ym(r["start"], today), _ym(r.get("end"), today)
        if b > a:
            spans.append((a, b))
    spans.sort()
    total, cur_a, cur_b = 0, None, None
    for a, b in spans:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                total += (cur_b - cur_a).days
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        total += (cur_b - cur_a).days
    return total / 365.25


YEARS_RE = re.compile(r"\b(\d+)\s*(\+)?\s*(?:years?|yrs?)\b", re.IGNORECASE)


def check_years_claims(text: str, roles: list[dict], derived: list[dict], today: date | None = None) -> list[str]:
    """'N years' in the summary/headline must match the profile's role dates: plain 'N years' must equal the rounded
    total, 'N+ years' must not exceed it. A derived_numbers basis that names role ids limits the check to those roles."""
    problems = []
    ids = {r.get("id") for r in roles}
    for m in YEARS_RE.finditer(text or ""):
        n, plus = int(m.group(1)), bool(m.group(2))
        basis = next((d.get("basis", "") for d in derived or [] if str(d.get("value")).strip() == str(n)), "")
        subset = {i for i in ids if i and re.search(rf"\b{re.escape(i)}\b", basis)} or None
        total = experience_years(roles, today, subset)
        scope = f"roles {', '.join(sorted(subset))}" if subset else "all roles"
        if plus and n > total + 1e-9:
            problems.append(f"'{m.group(0)}': the profile dates give {total:.1f} years ({scope}); use at most "
                            f"'{int(total)}+ years'")
        elif not plus and n != int(total + 0.5):
            problems.append(f"'{m.group(0)}': the profile dates give {total:.1f} years ({scope}); write "
                            f"'{int(total + 0.5)} years' or '{int(total)}+ years'")
    return problems


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------------------------------------------------------------
# Numbers with their units: every figure on a CV must exist in the profile with the same kind and value
# ---------------------------------------------------------------------------------------------------------------------
_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
_NUMWORD = "|".join(list(_ONES) + list(_TENS) + list(_SCALES))
_WORDSEQ_RE = re.compile(rf"\b(?:{_NUMWORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMWORD}))*\b", re.I)
_AFTER_UNIT_RE = re.compile(r"\s*(?:%|percent|per cent|times|x\b|fold\b)", re.I)


def _words_value(words: str) -> int:
    total, cur = 0, 0
    for w in re.findall(r"[a-z]+", words.lower()):
        if w == "and":
            continue
        if w in _ONES:
            cur += _ONES[w]
        elif w in _TENS:
            cur += _TENS[w]
        elif w == "hundred":
            cur = max(cur, 1) * 100
        elif w in _SCALES:
            total += max(cur, 1) * _SCALES[w]
            cur = 0
    return total + cur


def words_to_digits(text: str) -> str:
    """'seventy percent' -> '70 percent', 'twenty engineers' -> '20 engineers'. Small numbers (< 10) are only
    converted before a unit ('three times'), so phrases like 'one of the' or 'in one quarter' stay as they are."""
    def repl(m):
        val = _words_value(m.group(0))
        after = text[m.end():m.end() + 12]
        if val >= 10 or _AFTER_UNIT_RE.match(after):
            return str(val)
        return m.group(0)
    return _WORDSEQ_RE.sub(repl, text or "")


_CUR = {"€": "EUR", "$": "USD", "£": "GBP", "eur": "EUR", "euro": "EUR", "euros": "EUR", "usd": "USD", "dollars": "USD",
        "gbp": "GBP", "pln": "PLN", "zł": "PLN", "zl": "PLN", "chf": "CHF", "sek": "SEK", "dkk": "DKK", "nok": "NOK",
        "czk": "CZK", "ron": "RON"}
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "mln": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}
QTY_RE = re.compile(
    r"(?P<cur>[€$£])?\s?(?<![\w.,])(?P<num>\d{1,3}(?:[.,\u00a0\u202f ]\d{3})+(?![\d])|\d+(?:[.,]\d+)?)"
    r"(?:\s?(?P<scale>k|mn|mln|m|bn|thousand|million|billion)\b)?"
    r"(?:\s?(?P<unit>%|percent\b|per cent\b|pp\b|x\b|times\b|fold\b|eur\b|euros?\b|usd\b|dollars\b|gbp\b|pln\b|zł|chf\b"
    r"|sek\b|dkk\b|nok\b|czk\b|ron\b))?", re.I)


def _num(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,\u00a0\u202f ]\d{3})+", raw):
        raw = re.sub(r"[.,\u00a0\u202f ]", "", raw)
    return float(raw.replace(",", "."))


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def quantities(text: str) -> list[dict]:
    """Every number in the text with its kind: percent, multiple, money (normalised amount + currency), year or
    plain. Numbers written as words are converted first."""
    out = []
    t = words_to_digits(text)
    for m in QTY_RE.finditer(t):
        val = _num(m.group("num"))
        scale = (m.group("scale") or "").lower()
        unit = (m.group("unit") or "").lower().strip()
        cur = m.group("cur")
        if unit in ("%", "percent", "per cent", "pp"):
            kind, value, currency = "percent", val, None
        elif unit in ("x", "times", "fold"):
            kind, value, currency = "multiple", val, None
        elif cur or unit in _CUR:
            kind, value, currency = "money", val * _SCALE.get(scale, 1), _CUR.get((cur or unit).lower())
        elif not scale and float(val).is_integer() and 1950 <= val <= 2100 and len(m.group("num")) == 4:
            kind, value, currency = "year", val, None
        else:
            kind, value, currency = "plain", val * _SCALE.get(scale, 1), None
        out.append({"kind": kind, "value": round(value, 6), "currency": currency, "text": m.group(0).strip()})
    return out


def metric_quantity(m: dict) -> dict | None:
    """A structured profile metric ({value, unit}) as a quantity."""
    if not isinstance(m.get("value"), (int, float)) or isinstance(m.get("value"), bool):
        return None
    unit = str(m.get("unit") or "").strip().lower()
    v = float(m["value"])
    if unit in ("%", "percent", "pp"):
        return {"kind": "percent", "value": round(v, 6), "currency": None}
    if unit in ("x", "times", "fold"):
        return {"kind": "multiple", "value": round(v, 6), "currency": None}
    cur = next((c for k, c in _CUR.items() if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", unit)), None)
    if cur:
        scale = next((s for k, s in _SCALE.items() if re.search(rf"(?<![a-z]){k}(?![a-z])", unit)), 1)
        return {"kind": "money", "value": round(v * scale, 6), "currency": cur}
    return {"kind": "plain", "value": round(v, 6), "currency": None}


# Profile parts that are not evidence for CV figures: contact data (phone digits), preferences (salary floor),
# bookkeeping fields.
_NOT_EVIDENCE = {"personal", "preferences", "quality_gate", "updated_at", "schema_version", "$schema", "cv_preferences",
                 "guardrails"}
_DATE_KEYS = {"start", "end", "year", "confirmed_at", "passed_at", "granted_at"}


def profile_quantities(profile: dict) -> list[dict]:
    found = []

    def walk(obj, key=""):
        if isinstance(obj, dict):
            if "value" in obj and "unit" in obj:
                q = metric_quantity(obj)
                if q:
                    found.append(q)
                if isinstance(obj.get("baseline"), (int, float)) and not isinstance(obj.get("baseline"), bool):
                    found.append({"kind": "plain", "value": round(float(obj["baseline"]), 6), "currency": None})
            for k, v in obj.items():
                if not (key == "" and k in _NOT_EVIDENCE) and k not in ("value", "baseline"):
                    walk(v, k)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif isinstance(obj, bool) or obj is None:
            return
        elif isinstance(obj, (int, float)):
            found.append({"kind": "year" if key in _DATE_KEYS else "plain", "value": round(float(obj), 6),
                          "currency": None})
        elif isinstance(obj, str):
            if key in _DATE_KEYS:
                for y in re.findall(r"\b(19[5-9]\d|20\d\d)\b", obj):
                    found.append({"kind": "year", "value": float(y), "currency": None})
            else:
                found.extend(quantities(obj))
    walk(profile)
    return found


def _matches(q: dict, known: list[dict]) -> bool:
    for k in known:
        if k["value"] != q["value"]:
            continue
        if k["kind"] == q["kind"]:
            if q["kind"] != "money" or not k["currency"] or not q["currency"] or k["currency"] == q["currency"]:
                return True
        # A year written in a sentence ("since 2019") may also appear as a plain number in the profile text.
        if {k["kind"], q["kind"]} == {"year", "plain"}:
            return True
    return False


def unsupported_quantities(cv_text: str, profile: dict, derived: list[dict] | None = None) -> list[dict]:
    """Figures on the CV that the profile doesn't contain with the same kind and value. Derived numbers are
    accepted as declared (with their unit if they have one)."""
    known = profile_quantities(profile)
    for d in derived or []:
        known.extend(quantities(str(d.get("value", ""))))
    bad, seen = [], set()
    for q in quantities(cv_text):
        key = (q["kind"], q["value"], q["currency"])
        if key in seen:
            continue
        seen.add(key)
        if not _matches(q, known):
            bad.append(q)
    return bad
