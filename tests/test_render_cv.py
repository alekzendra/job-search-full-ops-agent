"""Tests for tools/render_cv.py. Run: python -m unittest discover -s tests"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render_cv as rc  # noqa: E402

CONFIG = ROOT / "config.example.json"
PROFILE = ROOT / "user_profile.example.json"
CONTENT = json.loads((ROOT / "examples" / "cv_content.example.json").read_text(encoding="utf-8"))


def run_cli(content, *extra, profile=True):
    """Run the CLI on a content dict; return (exit code, report)."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cv.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        args = [str(path), "--config", str(CONFIG), *extra]
        if profile:
            args += ["--profile", str(PROFILE)]
        if "--out" not in extra and "--check" not in extra:
            args += ["--check"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main(args)
        return code, json.loads(out.getvalue())


class RenderTests(unittest.TestCase):
    def test_example_renders_one_page_and_passes_fact_checks(self):
        code, r = run_cli(CONTENT)
        self.assertEqual(code, 0, r["errors"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["pages"], 1)

    def test_pdf_text_is_ats_readable_in_order(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cv.pdf"
            code, r = run_cli(CONTENT, "--out", str(out))
            self.assertEqual(code, 0, r["errors"])
            self.assertNotIn("docx", r)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["cv.pdf"])  # PDF only, no DOCX
            reader = PdfReader(str(out))
            self.assertEqual(len(reader.pages), 1)
            text = reader.pages[0].extract_text()
        order = ["Alex Example", "Professional Summary", "Skills", "Experience", "Acme Analytics", "Beta Logistics",
                 "Education", "Certifications", "Languages"]
        positions = [text.find(x) for x in order]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_overflow_is_reported_not_hidden(self):
        big = copy.deepcopy(CONTENT)
        big["experience"] = big["experience"] * 5
        code, r = run_cli(big, profile=False)
        self.assertEqual(code, 1)
        self.assertFalse(r["fits_one_page"])
        self.assertTrue(any("does not fit on one page" in e for e in r["errors"]))

    def test_measurement_matches_real_page_count(self):
        cv = rc.load_cv_config(str(CONFIG))
        fonts, _ = rc.load_fonts(cv, rc.visible_text(CONTENT))
        _, width, height = rc.page_geometry(cv)
        seen = {"fits": 0, "overflows": 0}
        for copies in (2, 3):
            content = copy.deepcopy(CONTENT)
            content["experience"] = content["experience"] * copies
            for s in (0.7, 1.0, 1.3, 1.6, 2.0, 2.5):
                measured = rc.measure(rc.build_story(content, cv, fonts, 10, s)[0], width)
                pages = rc.render_pdf(content, cv, fonts, 10, s, io.BytesIO())
                if measured <= rc.SAFETY * height:
                    seen["fits"] += 1
                    self.assertEqual(pages, 1, f"s={s}: measured {measured:.0f} <= {height:.0f} but {pages} pages")
                elif measured > 1.01 * height:
                    seen["overflows"] += 1
                    self.assertGreater(pages, 1, f"s={s}: measured {measured:.0f} > {height:.0f} but 1 page")
        self.assertTrue(seen["fits"] and seen["overflows"], seen)

    def test_unicode_names_render(self):
        c = copy.deepcopy(CONTENT)
        c["header"]["name"] = "Łukasz Żółć-Øster"
        cv = rc.load_cv_config(str(CONFIG))
        try:
            rc.load_fonts(cv, "Ł")
        except rc.UsageError:
            self.skipTest("no Unicode TTF font on this machine")
        code, r = run_cli(c, profile=False)
        self.assertEqual(r["pages"], 1)

    def test_never_overwrites_output_folder(self):
        cv = rc.load_cv_config(str(CONFIG))
        with tempfile.TemporaryDirectory() as d:
            first = rc.default_out(CONTENT, cv, Path(d))
            first.parent.mkdir(parents=True)
            second = rc.default_out(CONTENT, cv, Path(d))
            self.assertNotEqual(first.parent, second.parent)
            self.assertTrue(second.parent.name.endswith("_2"))


class FactLintTests(unittest.TestCase):
    def _bullet(self, text, role=0):
        c = copy.deepcopy(CONTENT)
        c["experience"][role]["bullets"][-1] = text
        return c

    def test_invented_number_is_blocked(self):
        code, r = run_cli(self._bullet("Cut onboarding time by 41% for new enterprise customers."))
        self.assertEqual(code, 1)
        self.assertTrue(any("numbers not found" in e and "41" in e for e in r["errors"]))

    def test_derived_number_is_allowed_but_listed(self):
        c = self._bullet("Brought 41 months of B2B logistics product experience to the dispatcher console.", role=1)
        c["derived_numbers"] = [{"value": "41", "basis": "Beta Logistics 2020-01 to 2023-02 (approx.)"}]
        code, r = run_cli(c)
        self.assertFalse(any("numbers not found" in e for e in r["errors"]), r["errors"])
        self.assertIn("derived_numbers_to_review", r)

    def test_changed_title_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["experience"][1]["title"] = "Head of Product"
        code, r = run_cli(c)
        self.assertTrue(any("title 'Head of Product' differs" in e for e in r["errors"]))

    def test_unknown_employer_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["experience"][1].pop("role_id")
        c["experience"][1]["company"] = "Gamma Corp"
        code, r = run_cli(c)
        self.assertTrue(any("'Gamma Corp' is not in the profile" in e for e in r["errors"]))

    def test_budget_claim_without_budget_ownership_is_blocked(self):
        code, r = run_cli(self._bullet("Managed the product budget for 3 squads and 9 engineers."))
        self.assertTrue(any("budget" in e for e in r["errors"]))

    def test_never_claim_phrase_is_blocked(self):
        code, r = run_cli(self._bullet("Held P&L ownership for the billing area across 3 squads."))
        self.assertTrue(any("never claim 'P&L ownership'" in e for e in r["errors"]), r["errors"])

    def test_uncertified_certification_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["certifications"].append({"name": "PMP", "issuer": "PMI"})
        code, r = run_cli(c)
        self.assertTrue(any("'PMP' is not in the profile" in e for e in r["errors"]))

    def test_min_quantified_bullets(self):
        c = copy.deepcopy(CONTENT)
        for role in c["experience"]:
            role["bullets"] = [b for b in role["bullets"] if not any(ch.isdigit() for ch in b)] or ["Owned delivery."]
        code, r = run_cli(c)
        self.assertTrue(any("measured result" in e for e in r["errors"]), r["errors"])

    def test_number_normalisation(self):
        self.assertEqual(rc.norm_number("4,000"), "4000")
        self.assertEqual(rc.norm_number("4.000"), "4000")
        self.assertEqual(rc.norm_number("1,5"), "1.5")
        self.assertEqual(rc.norm_number("03"), "3")


class KeywordLintTests(unittest.TestCase):
    def _kw(self, **changes):
        c = copy.deepcopy(CONTENT)
        c["target_keywords"].append({"priority": "must", **changes})
        return c

    def test_example_has_full_must_coverage(self):
        code, r = run_cli(CONTENT)
        self.assertEqual(code, 0, r["errors"])
        cov = r["keyword_coverage"]
        must_done, must_total = map(int, cov["must"].split("/"))
        self.assertEqual(must_done, must_total)
        self.assertIn("dbt", cov["not_supported_by_profile"])
        self.assertIn("Looker", cov["on_learning_line"])

    def test_supported_must_keyword_absent_from_cv_is_an_error(self):
        code, r = run_cli(self._kw(keyword="Mixpanel", status="matched", evidence="Mixpanel"))
        self.assertEqual(code, 0, "Mixpanel is in the tools line, so this one should pass")
        code, r = run_cli(self._kw(keyword="Kanban", status="matched", evidence="Kanban"))
        self.assertEqual(code, 1)
        self.assertTrue(any("must keyword 'Kanban'" in e for e in r["errors"]))

    def test_missing_keyword_on_cv_is_an_error(self):
        c = self._kw(keyword="Looker Studio", status="missing")
        c["tools"].append("Looker Studio")
        code, r = run_cli(c)
        self.assertTrue(any("'Looker Studio' is marked missing" in e for e in r["errors"]))

    def test_evidence_must_exist_in_profile(self):
        code, r = run_cli(self._kw(keyword="SQL", status="matched", evidence="10 years of PostgreSQL tuning"))
        self.assertTrue(any("evidence" in e and "not found" in e for e in r["errors"]))

    def test_matched_keyword_without_evidence_is_an_error(self):
        code, r = run_cli(self._kw(keyword="SQL", status="matched"))
        self.assertEqual(code, 2)
        self.assertIn("evidence", r["usage_error"])

    def test_keyword_match_ignores_case_hyphens_and_spacing(self):
        pat = rc._kw_pattern("usage based  pricing")
        self.assertTrue(pat.search("moved to Usage-Based pricing"))
        self.assertFalse(rc._kw_pattern("SQL").search("PostgreSQLish"))
        self.assertFalse(rc._kw_pattern("go").search("go-to-market"))

    def test_keyword_stuffing_is_warned(self):
        c = copy.deepcopy(CONTENT)
        c["skills"] += ["SQL reporting", "SQL dashboards", "SQL audits"]
        code, r = run_cli(c)
        self.assertTrue(any("'SQL' appears" in w and "stuffing" in w for w in r["warnings"]))

    def test_must_keyword_only_in_skills_is_warned(self):
        c = self._kw(keyword="Figma", status="matched", evidence="Figma")
        code, r = run_cli(c)
        self.assertTrue(any("'Figma' appears only in the skills/tools lines" in w for w in r["warnings"]))


class LearningLineTests(unittest.TestCase):
    def test_learning_line_is_rendered_in_pdf(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cv.pdf"
            code, r = run_cli(CONTENT, "--out", str(out))
            self.assertEqual(code, 0, r["errors"])
            text = PdfReader(str(out)).pages[0].extract_text()
        self.assertIn("Learning: Looker", text)
        self.assertLess(text.find("Tools:"), text.find("Learning:"))
        self.assertLess(text.find("Learning:"), text.find("Experience"))
        self.assertEqual(r["keyword_coverage"]["on_learning_line"], ["Looker"])

    def test_learning_item_not_in_profile_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["learning"].append("Kubernetes")
        code, r = run_cli(c)
        self.assertTrue(any("'Kubernetes' is not in the profile's skills.learning" in e for e in r["errors"]))

    def test_learning_keyword_used_as_experience_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["experience"][0]["bullets"][2] = c["experience"][0]["bullets"][2].replace(
            "Stripe Billing", "Stripe Billing and Looker")
        code, r = run_cli(c)
        self.assertTrue(any("'Looker' is only being learned" in e for e in r["errors"]))

    def test_too_many_learning_items_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["learning"] = ["Looker"] * 4
        code, r = run_cli(c)
        self.assertTrue(any("max_learning_items" in e for e in r["errors"]))

    def test_missing_keyword_on_learning_line_is_blocked(self):
        c = copy.deepcopy(CONTENT)
        c["learning"].append("dbt")
        code, r = run_cli(c)
        self.assertTrue(any("'dbt' is marked missing" in e for e in r["errors"]))
        self.assertTrue(any("'dbt' is not in the profile's skills.learning" in e for e in r["errors"]))

    def test_learning_line_can_be_switched_off(self):
        cv = rc.load_cv_config(str(CONFIG))
        cv["show_learning_line"] = False
        fonts, _ = rc.load_fonts(cv, "")
        story, tracked = rc.build_story(CONTENT, cv, fonts, 10, 1.0)
        self.assertNotIn("learning", [key for _, key, _ in tracked])


class TrialRunFixTests(unittest.TestCase):
    """Regression tests for the problems found in the 2026-11 trial run (fictional data)."""

    def test_bad_input_gives_clear_exit_2_not_a_crash(self):
        c = copy.deepcopy(CONTENT)
        c["derived_numbers"] = [{"value": 6, "basis": "role dates"}]
        code, r = run_cli(c)
        self.assertEqual(code, 2)
        self.assertIn("derived_numbers/0/value", r["usage_error"])

    def test_metric_rule_adapts_to_what_the_profile_can_supply(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        for role in profile["experience"]:
            for a in role["achievements"][1:]:
                a["metrics"], a["cv_bullet"] = [], "Worked with stakeholders on the roadmap."
        c = copy.deepcopy(CONTENT)
        c["experience"][0]["bullets"][1:] = ["Worked with stakeholders on the roadmap."] * 3
        c["experience"][1]["bullets"][1:] = ["Worked with stakeholders on the roadmap."] * 2
        cv = rc.load_cv_config(str(CONFIG))
        errors, _, info = rc.lint_facts(c, profile, cv)
        self.assertEqual(info["metric_bullets_available_in_profile"], 2)
        self.assertFalse(any("measured result" in e for e in errors), errors)
        self.assertIn("metric_note", info)
        c["experience"][1]["bullets"][0] = "Worked with stakeholders on the roadmap."
        errors, _, _ = rc.lint_facts(c, profile, cv)
        self.assertTrue(any("1 bullet with a measured result" in e and "has 2" in e for e in errors), errors)

    def test_team_size_is_not_a_result(self):
        cv = rc.load_cv_config(str(CONFIG))
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        c = copy.deepcopy(CONTENT)
        for role in c["experience"]:
            role["bullets"] = ["Coordinated work across 2 teams in Q3 2023."] * len(role["bullets"])
        errors, _, info = rc.lint_facts(c, profile, cv)
        self.assertEqual(info["quantified_bullets"], 0)

    def test_never_claim_matches_meaning(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile["guardrails"]["never_claim"] = ["people management"]
        c = copy.deepcopy(CONTENT)
        c["experience"][1]["bullets"][1] = "Lead a team of 5 engineers to rebuild the dispatcher console."
        errors, _, _ = rc.lint_facts(c, profile, rc.load_cv_config(str(CONFIG)))
        self.assertTrue(any("never claim 'people management'" in e for e in errors), errors)

    def test_years_must_match_role_dates(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        c = copy.deepcopy(CONTENT)
        c["summary"] = c["summary"].replace("6+ years", "6 years")
        errors, _, _ = rc.lint_facts(c, profile, rc.load_cv_config(str(CONFIG)))
        self.assertTrue(any("years of experience" in e for e in errors), errors)

    def test_short_cv_with_every_bullet_used_passes_without_warning(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile["experience"] = profile["experience"][:1]
        profile["experience"][0]["achievements"] = profile["experience"][0]["achievements"][:3]
        c = copy.deepcopy(CONTENT)
        c["experience"] = c["experience"][:1]
        c["experience"][0]["bullets"] = c["experience"][0]["bullets"][:3]
        c["target_keywords"] = [k for k in c["target_keywords"] if k["keyword"] in ("pricing", "A/B testing")]
        c.pop("certifications")
        with tempfile.TemporaryDirectory() as d:
            pp = Path(d) / "p.json"
            pp.write_text(json.dumps(profile), encoding="utf-8")
            cp = Path(d) / "c.json"
            cp.write_text(json.dumps(c), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc.main([str(cp), "--config", str(CONFIG), "--profile", str(pp), "--check"])
            r = json.loads(out.getvalue())
        self.assertFalse(any("page only" in w for w in r["warnings"]), r["warnings"])
        self.assertIn("short_cv", r)
        self.assertGreater(r["font_size_pt"], 10, "short CVs grow the font a little")

    def test_role_title_counts_as_experience_for_keywords(self):
        c = copy.deepcopy(CONTENT)
        self.assertIn("Senior Product Manager", rc.section_texts(c)["experience"])

    def test_pdf_file_name_has_no_spaces(self):
        cv = rc.load_cv_config(str(CONFIG))
        with tempfile.TemporaryDirectory() as d:
            self.assertNotIn(" ", rc.default_out(CONTENT, cv, Path(d)).name)


class NumberCheckTests(unittest.TestCase):
    """Figures are checked with their unit; numbers written as words count too (fictional data)."""

    def _errors(self, bullet):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        c = copy.deepcopy(CONTENT)
        c["experience"][1]["bullets"][1] = bullet
        errors, _, _ = rc.lint_facts(c, profile, rc.load_cv_config(str(CONFIG)))
        return [e for e in errors if "numbers not found" in e]

    def test_invented_money_multiple_and_word_numbers_are_blocked(self):
        for bullet in ("Generated €7M in new ARR.", "Lifted NRR 18x.", "Grew activation by sixty-five percent.",
                       "Reached 49 markets.", "Raised conversion by 73%."):
            self.assertTrue(self._errors(bullet), bullet)

    def test_same_number_with_a_different_unit_is_blocked(self):
        # The profile has 18% NRR and 27% conversion: "18x" and "€27k" are different claims.
        self.assertTrue(self._errors("Lifted NRR 18x in 12 months."))
        self.assertTrue(self._errors("Saved €27k through checkout work."))

    def test_profile_figures_pass_in_digits_or_words(self):
        self.assertEqual(self._errors("Cut late deliveries by 22% within 6 months for 40 carriers."), [])
        self.assertEqual(self._errors("Cut invoice disputes by seventy percent."), [])

    def test_phone_digits_and_dates_are_not_evidence(self):
        from cv_rules import profile_quantities
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        values = {(q["kind"], q["value"]) for q in profile_quantities(profile)}
        self.assertNotIn(("plain", 49.0), values, "country code of the phone number")
        self.assertIn(("year", 2023.0), values)
        self.assertNotIn(("plain", 2023.0), values)

    def test_quantity_parsing(self):
        from cv_rules import quantities
        kinds = lambda s: [(q["kind"], q["value"]) for q in quantities(s)]
        self.assertEqual(kinds("€7M"), [("money", 7000000.0)])
        self.assertEqual(kinds("300 000 users"), [("plain", 300000.0)])
        self.assertEqual(kinds("B2B, C2, Q3"), [])
        self.assertEqual(kinds("in one quarter"), [])
        self.assertEqual(kinds("three times faster"), [("multiple", 3.0)])


if __name__ == "__main__":
    unittest.main()
