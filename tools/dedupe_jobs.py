#!/usr/bin/env python3
"""Job Search Full-Ops Agent: find the same vacancy posted more than once.

The same job often appears on several boards, sometimes under the employer's name and sometimes under a recruiting
agency's. Matching on company + title misses those, so this script compares the job **title** and the **text of
the description**, independent of the company name.

Input: a JSON list of jobs (or {"candidates": [...]}) with at least title, company and the job text (`text`, as
SKILL.md saves it, or `description`); optional
job_id, url, location, source and posted_date.
Output: {"kept": [...], "duplicates": [{"kept": id, "dropped": id, "reason": ...}]}

When two posts match, the employer's own post is kept over an agency's, then the one with the longer description.

Usage:
  python tools/dedupe_jobs.py runs/candidates_<date>.json [--out runs/candidates_<date>.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Recruiting agencies: explicit agency words or well-known agency names only. Bare words like "talent" or
# "workforce" are left out on purpose: real employers use them too (e.g. Talentsoft, Workforce Software).
AGENCY_RE = re.compile(
    r"\brecruit\w*|\bstaffing\b|\bheadhunt\w*|\bexecutive search\b|\bsearch partners\b|"
    r"\b(?:employment|recruitment|recruiting|staffing|placement) agency\b|\btalent (?:solutions|partners|acquisition partners)\b|"
    r"personal(?:service|dienstleist\w*|vermittlung)|\bzeitarbeit\b|\buitzendbureau\b|\bagencja (?:pracy|rekrutacyjna)\b|"
    r"\bhays\b|\brandstad\b|\badecco\b|\bmichael page\b|\bpage (?:group|personnel)\b|\brobert (?:half|walters)\b|"
    r"\bmanpower\w*|\bgi group\b|\bexperis\b|\bharvey nash\b|\bhuxley\b|\bcpl\b|\bhudson\b", re.I)
GENDER_TAGS = re.compile(r"\((?:[mwfdxhv]\s*/\s*)+[mwfdxhv]\)|\b[mwfdx]/[mwfdx](?:/[mwfdx])?\b|\(all genders?\)|"
                         r"\(alle\)|\*in\b|/in\b|/-in\b", re.I)
TITLE_STOP = {"the", "a", "an", "and", "of", "for", "in", "at", "with", "to", "remote", "hybrid", "onsite", "job",
              "full", "time", "fulltime", "part", "en", "de", "la"}


def job_text(job: dict) -> str:
    """The job description. SKILL.md saves it as `text`; older files and other sources use `description`."""
    for key in ("text", "description", "jd", "body"):
        if job.get(key):
            return str(job[key])
    ld = job.get("jsonLd") or {}
    return str(ld.get("description") or "") if isinstance(ld, dict) else ""


def title_tokens(title: str) -> set[str]:
    t = GENDER_TAGS.sub(" ", (title or "").lower())
    return {w for w in re.findall(r"[a-z0-9äöüßéèàáíóúñçøåæłśżźćń]+", t) if w not in TITLE_STOP}


def shingles(text: str, n: int = 5) -> set[str]:
    words = re.findall(r"\w+", (text or "").lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_agency(job: dict) -> bool:
    return bool(AGENCY_RE.search(job.get("company") or ""))


def _city(loc: str) -> str:
    first = re.split(r"[,(/|·-]", loc.lower())[0]
    return re.sub(r"\b(?:hybrid|onsite|on-site|office|remote)\b", "", first).strip()


def same_place(a: dict, b: dict) -> bool:
    """Same city, or one of them is remote / has no location. Sharing only a country is not enough:
    'Berlin, Germany' and 'Munich, Germany' are different jobs."""
    la, lb = (a.get("location") or "").lower(), (b.get("location") or "").lower()
    if not la or not lb or "remote" in la or "remote" in lb:
        return True
    ca, cb = _city(la), _city(lb)
    if ca and cb:
        return ca == cb or ca in cb or cb in ca
    return bool(set(re.findall(r"\w+", la)) & set(re.findall(r"\w+", lb)))


def duplicate_reason(a: dict, b: dict) -> str | None:
    ta, tb = title_tokens(a.get("title")), title_tokens(b.get("title"))
    t_sim = jaccard(ta, tb)
    if t_sim < 0.6 or not same_place(a, b):
        return None
    sa, sb = shingles(job_text(a)), shingles(job_text(b))
    d_sim = jaccard(sa, sb)
    if d_sim >= 0.35:
        return f"same title ({t_sim:.0%}) and description ({d_sim:.0%} overlap)"
    if (a.get("company") or "").lower() == (b.get("company") or "").lower() and t_sim >= 0.9:
        return f"same company and title ({t_sim:.0%})"
    # Agency repost: the agency's text names the employer, and the titles match closely.
    for x, y in ((a, b), (b, a)):
        emp = (y.get("company") or "").strip().lower()
        if is_agency(x) and len(emp) >= 3 and emp in job_text(x).lower() and t_sim >= 0.8:
            return f"agency repost: '{x.get('company')}' advertises the '{y.get('company')}' role ({t_sim:.0%} title)"
    return None


def preference(job: dict) -> tuple:
    return (0 if is_agency(job) else 1, len(job_text(job)))


def dedupe(jobs: list[dict]) -> dict:
    kept, dups = [], []
    for job in jobs:
        match = None
        for i, k in enumerate(kept):
            reason = duplicate_reason(job, k)
            if reason:
                match = (i, reason)
                break
        if not match:
            kept.append(job)
            continue
        i, reason = match
        winner, loser = (job, kept[i]) if preference(job) > preference(kept[i]) else (kept[i], job)
        kept[i] = winner
        dups.append({"kept": winner.get("job_id") or winner.get("url"), "dropped": loser.get("job_id") or loser.get("url"),
                     "dropped_source": loser.get("source"), "reason": reason})
    return {"kept": kept, "duplicates": dups}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Remove the same vacancy posted on several boards or by agencies.")
    ap.add_argument("candidates")
    ap.add_argument("--out", help="write the de-duplicated list here (same shape as the input)")
    args = ap.parse_args(argv)
    try:
        data = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"usage_error": f"cannot read {args.candidates}: {e}"}))
        return 2
    jobs = data["candidates"] if isinstance(data, dict) else data
    result = dedupe(jobs)
    if args.out:
        out = dict(data, candidates=result["kept"]) if isinstance(data, dict) else result["kept"]
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"input": len(jobs), "kept": len(result["kept"]), "duplicates": result["duplicates"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
