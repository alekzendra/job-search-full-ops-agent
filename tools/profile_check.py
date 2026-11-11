#!/usr/bin/env python3
"""Job Search Full-Ops Agent: profile quality gate (the onboarding "stop factor").

Checks user_profile.json against the quality criteria in config.json -> profile_quality and prints a JSON report:
which checks pass, which fail, and a suggested question for each gap. Onboarding asks ONLY about failed checks and
stops interviewing once the gate passes.

This script checks what can be counted (bullets, metrics, dates, fields, sentence count). Claude additionally judges
the qualitative criteria: whether each bullet is in XYZ style with a real result, and whether the last role makes it
clear what the person did and achieved.

Usage:
  python tools/profile_check.py user_profile.json [--config config.json]
Exit codes: 0 = gate passed, 1 = gaps remain, 2 = usage problem.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv_rules import achievement_has_metric, plural  # noqa: E402

DEFAULTS = {
    "min_bullets_per_role": 3,
    "min_metric_bullets_per_role": 1,
    "min_responsibilities_last_role": 3,
    "about_me_sentences": {"min": 5, "max": 6},
    "min_core_skills": 5,
    "roles_checked": 4,
}


def sentences(text: str) -> int:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if len(p.split()) >= 3]
    return len(parts)


def has_metric(a: dict) -> bool:
    """A measured result (change, share, money, scale), not just any digit. See tools/cv_rules.py."""
    return achievement_has_metric(a)


def role_label(r: dict) -> str:
    return f"{r.get('title') or '?'} at {r.get('company') or '?'}"


def check(profile: dict, q: dict) -> list[dict]:
    out = []

    def add(cid, ok, message, question, scope="profile", required=True):
        out.append({"id": cid, "scope": scope, "ok": bool(ok), "required": required,
                    "message": message, "question": None if ok else question})

    p = profile.get("personal", {})
    loc = p.get("location", {}) or {}
    add("personal.name", p.get("full_name"), "Full name", "What is your full name as it should appear on CVs?")
    add("personal.email", p.get("email"), "Email for the CV header", "Which email should go on your CV?")
    add("personal.location", loc.get("city") and loc.get("country"), "Current city and country",
        "Which city and country do you live in?")
    add("personal.languages", p.get("languages"), "Languages with CEFR levels",
        "Which languages do you speak, and at what level (A1-C2 or native)?")
    add("personal.work_authorization", p.get("work_authorization"), "Work authorisation",
        "Where are you allowed to work (EU citizen, permit, needs sponsorship)?", required=False)

    n = sentences(profile.get("master_summary", ""))
    rng = q["about_me_sentences"]
    add("about_me", rng["min"] <= n <= rng["max"],
        f"'About me' has {n} sentences (needed {rng['min']}-{rng['max']})",
        f"Please write {rng['min']}-{rng['max']} sentences about yourself: what you do, your strongest results, your "
        f"domain, how you work, and what you're looking for.")

    roles = sorted(profile.get("experience", []), key=lambda r: r.get("start") or "", reverse=True)
    add("experience.any", roles, "At least one role", "Please share your work experience, starting with your latest role.")
    for i, r in enumerate(roles[: q["roles_checked"]]):
        rid, lbl = r.get("id") or f"role{i}", role_label(r)
        cc = r.get("company_context", {}) or {}
        scope = f"role:{rid}"
        add(f"{rid}.basics", r.get("title") and r.get("company") and r.get("start") and "end" in r,
            f"{lbl}: title, company, start and end dates", f"{lbl}: what were your exact start and end month?", scope)
        add(f"{rid}.company_type", cc.get("type"), f"{lbl}: type of company (agency, corporate, startup…)",
            f"{lbl}: what kind of company was it: agency, corporate, startup, scale-up, public sector…?", scope)
        add(f"{rid}.industry", cc.get("industry"), f"{lbl}: industry",
            f"{lbl}: which industry was the company in?", scope)
        add(f"{rid}.work_mode", r.get("work_mode"), f"{lbl}: remote / hybrid / onsite",
            f"{lbl}: was the role remote, hybrid or onsite?", scope)
        bullets = [a for a in r.get("achievements", []) if a.get("allowed_in_cv", True)]
        need = q["min_bullets_per_role"]
        add(f"{rid}.bullets", len(bullets) >= need, f"{lbl}: {plural(len(bullets), 'achievement')} (needed {need})",
            f"{lbl}: please describe {plural(need - len(bullets), 'more achievement')}: the situation, what you did, and "
            f"what changed afterwards.", scope)
        metric = sum(1 for a in bullets if has_metric(a))
        mneed = q["min_metric_bullets_per_role"]
        add(f"{rid}.metrics", metric >= mneed, f"{lbl}: {plural(metric, 'achievement')} with a measured result (needed {mneed})",
            f"{lbl}: can you put a number on one of your results (%, time, money, users, volume), ideally before → "
            f"after?", scope)
        add(f"{rid}.tools", r.get("tools"), f"{lbl}: tools used hands-on",
            f"{lbl}: which tools and methods did you use hands-on?", scope, required=False)
        if i == 0:
            resp = len(r.get("responsibilities", []))
            rneed = q["min_responsibilities_last_role"]
            add(f"{rid}.responsibilities", resp >= rneed,
                f"{lbl} (latest role): {resp} responsibilit{'y' if resp == 1 else 'ies'} (needed {rneed}) so it's clear what you did",
                f"{lbl}: walk me through a typical week. What were you responsible for?", scope)

    edu = profile.get("education", [])
    full = [e for e in edu if e.get("institution") and e.get("degree") and e.get("field") and e.get("start")
            and e.get("end")]
    add("education", full, "Education: university, degree, faculty/field and years",
        "Please share your education: university, degree (e.g. BSc/MSc), faculty or field (e.g. Business Management), "
        "and start-end years.")
    add("courses", profile.get("certifications"), "Courses and certifications",
        "Have you completed any courses or certifications worth listing?", required=False)
    core = len(profile.get("skills", {}).get("core", []))
    add("skills.core", core >= q["min_core_skills"], f"{plural(core, 'core skill')} (needed {q['min_core_skills']})",
        "Which 5-8 skills best describe your work?")
    return out


def run(profile_path: str, config_path: str | None) -> tuple[dict, int]:
    try:
        profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"usage_error": f"cannot read profile {profile_path}: {e}"}, 2
    q = dict(DEFAULTS)
    if config_path and Path(config_path).exists():
        q.update(json.loads(Path(config_path).read_text(encoding="utf-8")).get("profile_quality", {}))
    return run_profile(profile, q)


def run_profile(profile: dict, q: dict) -> tuple[dict, int]:
    checks = check(profile, q)
    accepted = set(profile.get("quality_gate", {}).get("accepted_gaps", []))
    for c in checks:
        c["accepted_gap"] = (not c["ok"]) and c["id"] in accepted
    blocking = [c for c in checks if c["required"] and not c["ok"] and not c["accepted_gap"]]
    report = {
        "passed": not blocking,
        "covered": [c["message"] for c in checks if c["ok"]],
        "gaps": [{"id": c["id"], "message": c["message"], "question": c["question"], "required": c["required"]}
                 for c in checks if not c["ok"] and not c["accepted_gap"]],
        "accepted_gaps": [c["id"] for c in checks if c["accepted_gap"]],
        "note": "Claude also checks that bullets are XYZ-style with real results and that the latest role is clear.",
    }
    return report, (0 if report["passed"] else 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Profile quality gate.")
    ap.add_argument("profile", nargs="?", default="user_profile.json")
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args(argv)
    report, code = run(args.profile, args.config)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
