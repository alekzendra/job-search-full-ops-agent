"""Tests for tools/validate.py and tools/dedupe_jobs.py (fictional data)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dedupe_jobs as dj  # noqa: E402
import validate as va  # noqa: E402

DESC = ("Northwind Payments is looking for a Senior Product Manager to own our billing platform. You will run "
        "discovery with customers, define the pricing roadmap, work with engineering and finance, and own "
        "usage-based billing. Requirements: 5+ years of product management in B2B SaaS, SQL, A/B testing, "
        "stakeholder management. We offer hybrid work in Berlin and a learning budget.")


def job(job_id, title, company, desc=DESC, location="Berlin, Germany", source="Board"):
    return {"job_id": job_id, "title": title, "company": company, "description": desc, "location": location,
            "source": source}


class DedupeTests(unittest.TestCase):
    def test_employer_and_agency_post_of_same_job_are_merged_keeping_employer(self):
        agency_desc = "Our client, Northwind Payments, is hiring. " + DESC.replace("our billing", "their billing")
        r = dj.dedupe([job("li-1", "Senior Product Manager (m/w/d)", "TalentBridge Recruitment", agency_desc, source="LinkedIn"),
                       job("sd-9", "Senior Product Manager", "Northwind Payments", source="StepStone")])
        self.assertEqual(len(r["kept"]), 1)
        self.assertEqual(r["kept"][0]["company"], "Northwind Payments")
        self.assertEqual(r["duplicates"][0]["dropped"], "li-1")

    def test_agency_repost_with_rewritten_text_is_caught_when_it_names_the_employer(self):
        rewritten = ("Exciting opportunity with Northwind Payments in Berlin! As Senior PM you'll lead billing "
                     "and pricing. Send your CV today.")
        r = dj.dedupe([job("a", "Senior Product Manager", "Northwind Payments"),
                       job("b", "Senior Product Manager (f/m/d)", "Hays Talent Solutions", rewritten)])
        self.assertEqual(len(r["kept"]), 1)
        self.assertIn("agency repost", r["duplicates"][0]["reason"])

    def test_different_jobs_at_same_company_are_kept(self):
        other = "Contoso is hiring a Data Engineer to build pipelines in Python and dbt for our analytics team."
        r = dj.dedupe([job("a", "Senior Product Manager", "Northwind Payments"),
                       job("b", "Data Engineer", "Northwind Payments", other)])
        self.assertEqual(len(r["kept"]), 2)

    def test_same_title_in_different_cities_is_kept(self):
        r = dj.dedupe([job("a", "Product Manager", "Contoso", "Short text A about Munich office.", "Munich, Germany"),
                       job("b", "Product Manager", "Contoso", "Short text B about Lisbon office.", "Lisbon, Portugal")])
        self.assertEqual(len(r["kept"]), 2)

    def test_job_text_field_from_skill_is_used(self):
        """SKILL.md saves the job description as `text` (trial-run bug: dedupe only read `description`)."""
        emp = job("e", "Senior Product Manager", "Northwind Payments")
        ag = job("h", "Senior Product Manager", "Hays", "Our client Northwind Payments: " + DESC)
        for j in (emp, ag):
            j["text"] = j.pop("description")
        r = dj.dedupe([ag, emp])
        self.assertEqual(len(r["kept"]), 1)
        self.assertEqual(r["kept"][0]["company"], "Northwind Payments")

    def test_same_title_same_country_different_city_is_kept(self):
        r = dj.dedupe([job("a", "Product Manager", "Contoso", "x1 Berlin office", "Berlin, Germany"),
                       job("b", "Product Manager", "Contoso", "x2 Munich office", "Munich, Germany")])
        self.assertEqual(len(r["kept"]), 2)

    def test_employers_with_talent_or_workforce_in_name_are_not_agencies(self):
        for name in ("Talentsoft", "Workforce Software", "TalentLMS"):
            self.assertFalse(dj.is_agency({"company": name}), name)
        for name in ("Hays Talent Solutions", "TalentBridge Recruitment", "Randstad Polska", "Robert Walters"):
            self.assertTrue(dj.is_agency({"company": name}), name)


class ValidateTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = va.main(list(args))
        return code, json.loads(out.getvalue())

    def test_example_files_are_valid(self):
        code, r = self.run_cli(str(ROOT / "config.example.json"), str(ROOT / "user_profile.example.json"),
                               str(ROOT / "examples" / "cv_content.example.json"))
        self.assertEqual(code, 0, r)

    def test_invalid_file_is_reported_with_path(self):
        bad = json.loads((ROOT / "user_profile.example.json").read_text(encoding="utf-8"))
        bad["personal"]["languages"][0]["level"] = "fluent"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            code, r = self.run_cli(str(p), "--kind", "user_profile")
        self.assertEqual(code, 1)
        self.assertIn("personal/languages/0/level", r["files"][str(p)]["errors"][0])


if __name__ == "__main__":
    unittest.main()
