"""Tests for tools/privacy_check.py, with made-up personal data only."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import privacy_check as pc  # noqa: E402

PROFILE = {
    "personal": {"full_name": "Zofia Testowa", "email": "zofia.testowa@mail.test", "phone": "+48 600 100 200",
                 "location": {"city": "Łódź", "country": "PL"},
                 "links": {"linkedin": "https://www.linkedin.com/in/zofia-testowa-123/"}},
    "experience": [{"company": "Kwiatek Software"}, {"company": "Northwind Sp. z o.o."}],
    "education": [{"degree": "MSc", "institution": "Uniwersytet Zielonogórski"}],
}
CONFIG = {"search": {"boards": [{"name": "LinkedIn Jobs"}]},
          "notifications": {"email": {"recipients": ["inbox@mail.test"]}},
          "mcp": {"env": {"APIFY_TOKEN": "apify_api_SECRETVALUE123"}},
          "integrations": {"firecrawl": {"api_key_env": "FIRECRAWL_API_KEY"}}}


class PrivacyCheckTests(unittest.TestCase):
    def run_check(self, files: dict, *extra):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".gitignore").write_text("user_profile.json\nconfig.json\n.env\n", encoding="utf-8")
            (root / "user_profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
            (root / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
            (root / ".env").write_text("FIRECRAWL_API_KEY=fc-1234567890abcdef\n", encoding="utf-8")
            for name, text in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = pc.main(["--root", str(root), *extra])
            return code, out.getvalue()

    def test_clean_repo_passes_and_private_files_are_not_scanned(self):
        code, out = self.run_check({"README.md": "A job agent for LinkedIn Jobs and others."})
        self.assertEqual(code, 0, out)

    def test_finds_name_email_phone_url_company_city_and_secrets(self):
        leaks = {
            "a.md": "Contact Zofia Testowa", "b.md": "mail zofia.testowa@mail.test", "c.md": "call 48600100200",
            "d.md": "linkedin.com/in/zofia-testowa-123", "e.md": "worked at Kwiatek Software",
            "f.md": "based in Lodz", "g.md": "key fc-1234567890abcdef", "h.md": "token apify_api_SECRETVALUE123",
            "i.md": "send to inbox@mail.test",
        }
        code, out = self.run_check(leaks)
        self.assertEqual(code, 1)
        for name in leaks:
            self.assertIn(f"{name}:1:", out, f"{name} not flagged:\n{out}")

    def test_env_variable_names_are_not_secrets(self):
        code, out = self.run_check({"README.md": "export FIRECRAWL_API_KEY=... before the first run"})
        self.assertEqual(code, 0, out)

    def test_secrets_are_never_printed_even_with_show(self):
        code, out = self.run_check({"g.md": "key fc-1234567890abcdef"}, "--show")
        self.assertNotIn("1234567890abcdef", out)

    def test_findings_are_masked_by_default(self):
        code, out = self.run_check({"a.md": "Contact Zofia Testowa"})
        self.assertNotIn("Zofia Testowa", out)

    def test_allow_list_is_per_file(self):
        files = {"LICENSE": "Copyright (c) 2026 Zofia Testowa", "notes.md": "Zofia Testowa wrote this"}
        code, out = self.run_check(files, "--allow", "LICENSE:Zofia Testowa")
        self.assertEqual(code, 1)
        self.assertNotIn("LICENSE:1:", out)
        self.assertIn("notes.md:1:", out)

    def test_generic_board_names_are_not_personal(self):
        code, out = self.run_check({"README.md": "Search LinkedIn Jobs"})
        self.assertEqual(code, 0, out)

    def test_finds_reformatted_phone_short_employer_and_university(self):
        leaks = {"p1.md": "tel 600-100-200", "p2.md": "call (600) 100 200 now", "n.md": "I worked at Northwind",
                 "u.md": "Studied at Uniwersytet Zielonogorski", "u2.md": "Graduated from Zielonogórski"}
        code, out = self.run_check(leaks)
        self.assertEqual(code, 1)
        for name in ("p1.md", "p2.md", "n.md", "u.md"):
            self.assertIn(f"{name}:1:", out, f"{name} not flagged:\n{out}")

    def test_short_names(self):
        self.assertEqual(pc.short_names("Northwind Sp. z o.o."), ["Northwind"])
        self.assertIn("Fabrikam", pc.short_names("Fabrikam Electric"))
        self.assertEqual(pc.short_names("Digital Solutions GmbH"), ["Digital Solutions"])

    def test_ordinary_numbers_are_not_phone_hits(self):
        code, out = self.run_check({"r.md": "Run 1200 tests in 2026-11-08 with 3 boards"})
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
