# Contributing to Job Search Full-Ops Agent

Thanks for helping. The most useful contributions are **new or fixed job boards**, better onboarding questions,
renderer and linter improvements, and clearer docs. Please read the privacy rules first: this project handles CVs,
so they are strict.

## Privacy rules (always)

- **Never commit real personal data**: no real CVs, profiles, emails, phone numbers, LinkedIn URLs, employers you
  worked for, run logs, tracking sheets or API keys. This also applies to issues, PR descriptions and screenshots.
- Use **fictional data** in examples and tests (like "Alex Example" and made-up companies such as Northwind or
  Contoso), and `example.com` / `mail.test` addresses.
- `config.json`, `user_profile.json`, `.env`, `.privacy_terms`, `output_resumes/`, `runs/` and imported CVs are
  gitignored. Don't force-add them.
- Before every commit, run the privacy check with your own data as the source:
  ```bash
  .venv/bin/python tools/privacy_check.py --source path/to/your/profile.json --source path/to/your/.env
  ```
  It must print `Clean`.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
.venv/bin/python -m unittest discover -s tests
```
All tests must pass. Code must run on **Python 3.9+**.

## Adding or fixing a job board

1. **Live-test it** with the Firecrawl MCP: one `firecrawl_search` for a common title and a city in one of the
   board's countries (`limit: 3`, `tbs: "qdr:m"`), and one `firecrawl_scrape` (`formats: ["markdown"]`) of a single
   job page to check that the full description comes through without login.
2. **Add the entry** to `search.boards` in `config.example.json`, with every field the schema requires: `id`, `name`,
   `category`, `region`, `coverage`, `countries`, `method`, `domains`, `listing_languages`, `query_template`, plus
   - `job_url_pattern`: a regex that matches single job pages and **not** search-results pages;
   - `verified`: the test date;
   - `search_time_filter: null` if the board returned 0 results with a time filter;
   - `notes` for anything a user should know (low precision, login walls, loose locations).
3. **Add the URLs you saw** to `LIVE_URLS` in `tests/test_config.py`: at least one job page that must match, and
   one search-results page that must not, if the board returned any.
4. **Record the result** in `docs/board-tests.md` (the query, the result type, and what you changed).
5. Never add boards that need a login, break their terms of use for automated access, or require bypassing
   anti-bot measures or CAPTCHAs. Public pages and official or structured APIs only.

Prefer a Firecrawl structured provider (`method: "firecrawl_provider"`) when one exists for the board and covers
European countries. Check with `firecrawl_find_tools` (free).

## Changing the skill (`.claude/skills/job-search-full-ops-agent/`)

- `SKILL.md` is the pipeline; `onboarding.md` is the first-run interview. Keep the steps numbered, and keep every
  `{config.…}` / `{profile.…}` reference pointing to a field that exists in the example files.
- **Truthfulness is the core rule.** A change must never let the agent add facts, numbers, employers, titles,
  certifications or keywords that the profile doesn't support. Keywords that aren't supported stay off the CV; the
  Learning line is only for skills the user confirmed they're learning.
- **Output is PDF only.** Don't add DOCX or Google Doc CV output.
- **Ask before acting.** The agent must ask before creating Drive files, sending email or creating schedules.
  Don't remove those confirmations.
- Scripts never call an LLM API. Claude does the reasoning in the user's session.

## Changing the renderer or schemas

- `tools/cv_rules.py` holds the truth rules shared by the quality gate and the renderer (what counts as a measured
  result, never-claim meaning, years of experience). Change them there, never in one tool only.
- `tools/render_cv.py`: add a test in `tests/test_render_cv.py` for every new check. The page-fit measurement must
  keep matching the real PDF page count (see `test_measurement_matches_real_page_count`).
- `schemas/*.json`: update the matching example file so it still validates. The tests check both.
- `templates/google_sheet_structure.json` must list exactly the columns in `config.example.json` →
  `tracking.columns`, in the same order.

## Pull request checklist

- [ ] `.venv/bin/python -m unittest discover -s tests` passes
- [ ] `tools/privacy_check.py` prints `Clean`
- [ ] Examples and tests use fictional data only
- [ ] Docs updated (`README.md`, `docs/board-tests.md`, or the skill files) where behaviour changed
- [ ] For boards: live-test result and URL samples added

## Reporting bugs

Open an issue with:
- what you ran;
- what you expected and what happened;
- the renderer's JSON report or the board and query, **with personal data removed**.

Don't attach your CV, your profile or a digest email. Reproduce the problem with the fictional example files
instead.

## Conduct

Be respectful and constructive. Contributions are reviewed for correctness, privacy and honesty of the CVs the agent
produces.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
