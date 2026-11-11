"""Tests for tools/profile_check.py (the onboarding quality gate). Fictional data only."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import profile_check as pc  # noqa: E402

EXAMPLE = json.loads((ROOT / "user_profile.example.json").read_text(encoding="utf-8"))
Q = {**pc.DEFAULTS, **json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))["profile_quality"]}

# What a thin imported CV typically gives: one role, two bullets without numbers, short summary, partial education.
THIN = {
    "personal": {"full_name": "Sam Sample", "email": "sam@mail.test", "location": {"city": "Porto", "country": "PT"},
                 "languages": [{"language": "English", "level": "C1"}]},
    "master_summary": "Project manager. Agile fan.",
    "experience": [{"id": "r1", "title": "Project Manager", "company": "Example Lda", "start": "2022-01", "end": None,
                    "responsibilities": ["Managed projects"],
                    "achievements": [{"id": "a1", "statement": "Improved processes", "source": "imported_cv",
                                      "allowed_in_cv": True},
                                     {"id": "a2", "statement": "Led a team", "source": "imported_cv",
                                      "allowed_in_cv": True}]}],
    "education": [{"degree": "BSc", "institution": "Example University"}],
    "skills": {"core": ["Agile"]},
}


def gaps(profile):
    checks = pc.check(profile, Q)
    return {c["id"] for c in checks if c["required"] and not c["ok"]}


class ProfileGateTests(unittest.TestCase):
    def test_example_profile_passes(self):
        self.assertEqual(gaps(EXAMPLE), set())

    def test_thin_cv_fails_on_each_user_criterion(self):
        g = gaps(THIN)
        for cid in ("about_me",            # 5-6 sentence 'about me'
                    "r1.bullets",          # at least 3 bullets per role
                    "r1.metrics",          # a real result with a number
                    "r1.company_type",     # agency / corporate / startup...
                    "r1.industry",
                    "r1.work_mode",        # remote / onsite / hybrid
                    "r1.responsibilities", # clear what they did in the latest role
                    "education",           # university, degree, faculty, years
                    "skills.core"):
            self.assertIn(cid, g)

    def test_every_gap_comes_with_a_question(self):
        report, code = pc.run_profile(THIN, Q)
        self.assertEqual(code, 1)
        self.assertTrue(all(x["question"] for x in report["gaps"]))

    def test_accepted_gaps_let_the_gate_pass(self):
        p = copy.deepcopy(EXAMPLE)
        p["experience"][0]["achievements"] = p["experience"][0]["achievements"][:2]
        report, code = pc.run_profile(p, Q)
        self.assertEqual(code, 1)
        p["quality_gate"] = {"accepted_gaps": ["acme_pm.bullets"]}
        report, code = pc.run_profile(p, Q)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["accepted_gaps"], ["acme_pm.bullets"])

    def test_metric_found_in_bullet_text(self):
        a = {"cv_bullet": "Cut costs by 20% by renegotiating vendor contracts."}
        self.assertTrue(pc.has_metric(a))
        self.assertFalse(pc.has_metric({"cv_bullet": "Improved processes."}))

    def test_sentence_count(self):
        self.assertEqual(pc.sentences("One two three. Four five six! Seven eight nine?"), 3)

    def test_only_recent_roles_are_checked(self):
        p = copy.deepcopy(EXAMPLE)
        old = copy.deepcopy(THIN["experience"][0])
        old.update({"id": "old", "start": "2005-01", "end": "2006-01"})
        p["experience"].append(old)
        q = {**Q, "roles_checked": 2}
        checks = pc.check(p, q)
        self.assertEqual({c["id"] for c in checks if c["required"] and not c["ok"]}, set(),
                         "a role older than the newest roles_checked roles is not required to pass")
        self.assertIn("old.bullets", gaps(p), "...but it is checked when it is within roles_checked")


if __name__ == "__main__":
    unittest.main()
