"""Config and board-catalog checks. Run: python -m unittest discover -s tests

The sample URLs below were returned by the live board test on 2026-11-07 (docs/board-tests.md).
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
BOARDS = {b["id"]: b for b in CONFIG["search"]["boards"]}

# board id -> (job page URLs that must match, search/listing page URLs that must not)
LIVE_URLS = {
    "linkedin": (["https://www.linkedin.com/jobs/view/project-manager-e-commerce-m-w-d-at-tecracer-4487232415"], []),
    "indeed": (["https://de.indeed.com/viewjob?jk=9305ae0ecacdec67"],
               ["https://de.indeed.com/q-junior-project-manager-l-berlin-jobs.html"]),
    "glassdoor": (["https://www.glassdoor.de/job-listing/jv?jl=1009711154343"],
                  ["https://www.glassdoor.de/Job/deutschland-siemens-international-project-manager-jobs-SRCH_IL.0,11_IN96_KO12,49.htm"]),
    "eurojobs": (["https://www.eurojobs.com/jobs/37139239/project-manager-37139239"], []),
    "wellfound": (["https://wellfound.com/jobs/4897609-product-manager"], []),
    "welcome_to_the_jungle": (["https://www.welcometothejungle.com/en/companies/botify/jobs/senior-product-manager_paris_BOTIF_ZJOm8p6"], []),
    "nofluffjobs": (["https://nofluffjobs.com/pl/job/it-project-manager-makeitright-warszawa-1"], []),
    "landing_jobs": (["https://landing.jobs/at/swisscom/ai-platform-engineer"],
                     ["https://landing.jobs/at/volkswagen-group-digital-solutions-portugal"]),
    "jobriver": (["https://jobriver.de/en/jobs/senior-it-projektmanager-m-w-d-darmstadt-17766"],
                 ["https://jobriver.de/en/job-listings/it-projektmanager"]),
    "the_hub": (["https://thehub.io/jobs/6acd982e8d3189327f9a0a91"], []),
    "remoteok": (["https://remoteok.com/remote-jobs/remote-partner-operations-manager-mecka-1137609"], []),
    "weworkremotely": (["https://weworkremotely.com/remote-jobs/we-are-rosie-media-project-manager"], []),
    "eu_remote_jobs": (["https://euremotejobs.com/job/senior-project-manager-remote-contract-2/"], []),
    "working_nomads": (["https://www.workingnomads.com/jobs/senior-project-manager-captivateiq-2004676"], []),
    "remote_co": (["https://remote.co/job-details/senior-project-manager-9928b3b0-72ee-4677-8420-fc63ad0b29ef"], []),
    "stepstone": (["https://www.stepstone.de/stellenangebote--Projektleiter-in-Projektmanager-in-Berlin-BarMalGas-GmbH--14651394-inline.html"],
                  ["https://www.stepstone.de/jobs/junior-projektmanager-event/in-berlin"]),
    "xing": (["https://www.xing.com/jobs/berlin-projektmanager-power-bi-entscheidungsbefugnis-158798147"],
             ["https://www.xing.com/jobs/junior-projektmanager-jobs-in-hamburg"]),
    "karriere_at": ([], ["https://www.karriere.at/jobs/projektmanager-innovation/wien"]),
    "jobs_ch": (["https://www.jobs.ch/de/stellenangebote/detail/9025d964-d0e7-4520-a23f-619c98eb897d/"], []),
    "reed": (["https://www.reed.co.uk/jobs/infrastructure-project-manager/57501763"],
             ["https://www.reed.co.uk/jobs/project-manager-jobs-in-west-kensington?sid=GzYA"]),
    "cv_library": (["https://www.cv-library.co.uk/job/225444454/project-manager-prime-residential"], []),
    "jobs_ie": (["https://www.jobs.ie/job/project-manager/compass-group-job108095580"], []),
    "nationale_vacaturebank": (["https://www.nationalevacaturebank.nl/vacature/2aa2560f-9176-49e0-83ae-45f8711a7d37/senior-project-manager"], []),
    "jobindex": (["https://www.jobindex.dk/jobannonce/h1709493/er-du-vores-nye-projektleder-i-koebenhavn"],
                 ["https://www.jobindex.dk/jobsoegning/storkoebenhavn?q=projektleder"]),
    "platsbanken": (["https://arbetsformedlingen.se/platsbanken/annonser/31653973"], []),
    "infojobs": (["http://www.infojobs.net/madrid/project-manager-hr-projects/of-i542f272c6c4a4394a19bdd7aab5d84"],
                 ["https://www.infojobs.net/ofertas-trabajo/madrid/digital-project-manager"]),
    "tecnoempleo": (["https://www.tecnoempleo.com/it-project-manager-bertek-trust-systems-espana/agile-scrum/rf-80dc19b982be239a5647"], []),
    "net_empregos": (["https://www.net-empregos.com/16178147/gestor-de-projeto-8211-real-estate-lisboa-m-f/"],
                     ["https://www.net-empregos.com/gestor-projetos/"]),
    "jobs_cz": ([], ["https://www.jobs.cz/prace/praha/project-manager/?locality%5Bradius%5D=10"]),
    "profesia": ([], ["https://www.profesia.sk/praca/projektovy-manazer/?cat_pos=5019453"]),
    "ejobs": (["https://www.ejobs.ro/user/locuri-de-munca/project-manager/99251348"], []),
}


class ConfigTests(unittest.TestCase):
    def test_example_config_matches_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schemas" / "config.schema.json").read_text(encoding="utf-8"))
        errors = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(CONFIG)]
        self.assertEqual(errors, [])

    def test_board_ids_unique_and_domains_consistent(self):
        ids = [b["id"] for b in CONFIG["search"]["boards"]]
        self.assertEqual(len(ids), len(set(ids)))
        for b in CONFIG["search"]["boards"]:
            for country in b.get("domains", {}):
                self.assertTrue(country == "*" or country in b["countries"] or "*" in b["countries"],
                                f"{b['id']}: domain for {country} not in countries")
            if b["method"] == "firecrawl_search":
                self.assertIn("{domain}", b["query_template"], b["id"])

    def test_job_url_patterns_match_live_urls(self):
        for board_id, (jobs, listings) in LIVE_URLS.items():
            pat = re.compile(BOARDS[board_id]["job_url_pattern"])
            for url in jobs:
                self.assertTrue(pat.search(url), f"{board_id}: job page not matched: {url}")
            for url in listings:
                self.assertFalse(pat.search(url), f"{board_id}: listing page matched as a job: {url}")

    def test_every_enabled_board_has_a_job_url_pattern_and_verification(self):
        for b in CONFIG["search"]["boards"]:
            if b["enabled"]:
                self.assertTrue(b.get("verified"), b["id"])
                if b["method"] != "firecrawl_web_search":     # open web search classifies hits by page content
                    self.assertIn("job_url_pattern", b, b["id"])

    def test_linkedin_and_web_search_are_always_on_everywhere(self):
        always = {b["id"] for b in CONFIG["search"]["boards"] if b.get("always_on")}
        self.assertEqual(always, {"linkedin", "web_search"})
        for bid in always:
            self.assertEqual(BOARDS[bid]["countries"], ["*"])
            self.assertTrue(BOARDS[bid]["enabled"])
        self.assertIn("linkedin.com", BOARDS["web_search"]["exclude_domains"])

    def test_user_boards_are_added_to_catalog_boards_not_instead(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import list_boards as lb
        boards = [b for b in CONFIG["search"]["boards"] if b["enabled"]]
        default = lb.boards_for("PT", boards)
        user = [{"id": f"pt_site_{i}", "name": f"PT site {i}", "enabled": True, "added_by": "user",
                 "category": "national", "coverage": "country", "countries": ["PT"], "method": "firecrawl_search",
                 "domains": {"PT": f"site{i}.example.pt"}, "query_template": "site:{domain} \"{title}\""}
                for i in range(5)]
        withuser = lb.boards_for("PT", boards + user)
        ids = {b["id"] for b in withuser["local"]}
        self.assertTrue({b["id"] for b in default["local"]} <= ids, "catalog boards stay")
        self.assertTrue({u["id"] for u in user} <= ids, "user boards are added")
        self.assertEqual({b["id"] for b in withuser["always_on"]}, {"linkedin", "web_search"})
        self.assertEqual(lb.boards_for("DE", boards + user)["local"], lb.boards_for("DE", boards)["local"],
                         "a Portuguese site isn't searched for Germany")

    def test_indeed_provider_countries_are_on_the_board(self):
        b = BOARDS["indeed"]
        self.assertEqual(b["method"], "firecrawl_provider")
        self.assertTrue(set(b["provider"]["countries"]) <= set(b["countries"]))

    def test_sheet_structure_matches_tracking_config(self):
        sheet = json.loads((ROOT / "templates" / "google_sheet_structure.json").read_text(encoding="utf-8"))
        self.assertEqual([c["name"] for c in sheet["columns"]], CONFIG["tracking"]["columns"])
        self.assertEqual(sheet["row_key"], "Job ID")
        status = next(c for c in sheet["columns"] if c["name"] == "Application Status")
        self.assertEqual(status["owner"], "user")
        self.assertIn(status["default"], CONFIG["tracking"]["statuses"])
        colored = {r["value"] for r in status["conditional_formatting"]}
        self.assertEqual(colored, set(CONFIG["tracking"]["statuses"]))

    def test_search_window_rules(self):
        s = CONFIG["search"]
        self.assertLessEqual(s["max_lookback_days"], 21, "later runs cover at most 3 weeks")
        self.assertTrue(1 <= s["first_run_lookback_days"] <= 30)

    def test_linkedin_uses_apify_with_firecrawl_fallback(self):
        b = BOARDS["linkedin"]
        self.assertEqual(b["method"], "apify_actor")
        self.assertEqual(b["fallback_method"], "firecrawl_search")
        self.assertIn("{domain}", b["query_template"])
        self.assertTrue(CONFIG["integrations"]["apify"]["fallback_to_firecrawl"])

    def test_results_go_to_google_sheet_or_chat_only(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schemas" / "config.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["tracking"]["properties"]["storage"]["enum"], ["google_sheets", "chat"])
        self.assertNotIn("attach_tracking_sheet", CONFIG["notifications"]["email"])

    def test_list_boards_language_forms_all_work(self):
        """Trial-run bug: '--languages en,pt' was read as one unknown language and dropped every board."""
        import contextlib, io, sys
        sys.path.insert(0, str(ROOT / "tools"))
        import list_boards as lb
        cfg = str(ROOT / "config.example.json")
        expected = {"indeed", "landing_jobs", "net_empregos"}
        for form in (["en", "pt"], ["en,pt"], ["EN, PT"], ["English", "Portuguese"], ["en pt"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = lb.main(["PT", "--config", cfg, "--languages", *form])
            self.assertEqual(code, 0, form)
            res = json.loads(out.getvalue())[0]
            self.assertEqual({b["id"] for b in res["local"]}, expected, form)
            self.assertEqual([b["id"] for b in res["pan_european"]], ["eurojobs"], form)
            self.assertNotIn("warning", res, form)

    def test_list_boards_unknown_language_is_an_error_not_an_empty_list(self):
        import contextlib, io, sys
        sys.path.insert(0, str(ROOT / "tools"))
        import list_boards as lb
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = lb.main(["PT", "--config", str(ROOT / "config.example.json"), "--languages", "en,portugese"])
        self.assertEqual(code, 2)
        self.assertIn("portugese", json.loads(out.getvalue())["usage_error"])

    def test_list_boards_warns_when_a_country_is_left_with_only_always_on(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import list_boards as lb
        boards = [b for b in CONFIG["search"]["boards"] if b["enabled"]]
        res = lb.boards_for("PT", boards, languages={"de"})
        self.assertIn("warning", res)
        self.assertIn("LinkedIn", res["warning"])


if __name__ == "__main__":
    unittest.main()
