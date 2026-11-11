# Job Search Full-Ops Agent

A configurable European job-search agent that runs inside **Claude Code**. It searches 30+ European job boards,
scores each job against your full work history, writes a **1-page ATS CV for every good match without inventing
facts**, tracks everything in a Google Sheet and emails you a digest on your schedule, or shows the results in the
chat.

> Claude does the reasoning (fit scoring, keyword extraction, CV writing) in your Claude session. No LLM API key is
> needed. The Python tool in this repo does only deterministic work: page fitting, rendering and fact checks.

---

## Features

- **Pan-European search.** LinkedIn and an open web search in every country, plus 31 catalog boards (Indeed,
  Glassdoor, tech/startup and remote-first boards, and national leaders across DACH, UK & Ireland, Benelux, the
  Nordics, Southern Europe and CEE). **You can add your own local boards per country** during onboarding; they're
  searched alongside the defaults. National boards are also
  searched with local job titles (e.g. "Projektmanager").
- **CV-first onboarding with a quality gate.** Share your CV or describe your experience. The agent checks it
  against clear criteria:
  - per role: 3+ achievement bullets, at least one XYZ-style result with a number, company type, industry,
    remote/onsite, and what you did in your latest role;
  - overall: a 5–6 sentence "About me", and education with university, degree, faculty and years.

  It then asks **only about the gaps**, and stops as soon as the profile passes. Every CV line traces back to this
  profile.
- **Your job goal, five questions.** Title, seniority, location, format (remote/hybrid/onsite) and salary. Everything
  else is optional "advanced settings".
- **Honest fit scoring.** A 0–100 score with strict calibration (years of experience, seniority, languages, people
  management), plus pre-filters for geography, work mode, residency/visa, language, salary and deal-breakers.
- **One tailored CV per vacancy.** Every job that matches you gets its own 1-page CV, built for that job post.
- **ATS keywords inside the CV.** Each job post's keywords are written into the headline, summary, skills and
  bullets in the post's exact wording. Keywords you're learning go on a separate **Learning:** line. Keywords
  your profile doesn't support are never added; the digest asks you about them instead.
- **Strict 1-page PDF.** `tools/render_cv.py` fits the CV to exactly one page and blocks it if it breaks a rule:
  a figure that isn't in your profile with the same unit (a percentage, multiple or amount of money; numbers written
  as words are checked too), a changed employer, title or certification, a never-claim statement in any wording,
  a "years of experience" claim that doesn't match your dates, a missing must-have keyword, or keyword stuffing.
  Plain counts (e.g. "40 carriers") are checked against all numbers in your profile, not their context, so read
  every CV before you send it.
- **Tracking and digest.** Weekly tabs in a Google Sheet (status dropdowns preserved, nothing you set is
  overwritten), PDFs in your Drive folder, and an email digest with keyword coverage and "do you have X?" questions.
  No Google or no email? The same report and results table appear in the chat.
- **Search window.** You choose how far back the first search goes (e.g. 2 weeks). After that, each run covers the
  time since the previous one, up to 3 weeks.
- **Scheduled runs**, for example Mon/Wed/Fri at 21:00, or manual runs only.

---

## System architecture

```
 ┌───────────────────────── Claude Code session ──────────────────────────┐
 │                                                                         │
 │  .claude/skills/job-search-full-ops-agent/  SKILL.md · onboarding.md    │
 │        │                                                                │
 │        ├─ 1-2  read tracker, set search window ──────────► Google MCP   │
 │        ├─ 3    collect jobs  ─────────────────────────────► Firecrawl   │
 │        │         search / structured providers / scrape    (Apify opt.) │
 │        ├─ 4    pre-filters (geo, work mode, language, residency, salary)│
 │        ├─ 5-6  fit score + ATS keywords        (Claude)                 │
 │        ├─ 7    tailor CV content → runs/cv_<job>.json (Claude)          │
 │        ├─ 8    tools/render_cv.py → fit 1 page, lint facts, PDF         │
 │        ├─ 9    tracking sheet + PDF upload ───────────────► Google MCP   │
 │        └─ 10   digest email ──────────────────────────────► Gmail (MCP)  │
 │                                                                         │
 │  config.json  ·  user_profile.json  ·  .env   (local, never committed)  │
 └─────────────────────────────────────────────────────────────────────────┘
        ▲ scheduled task (Claude Code) or Apify schedule triggers the run
```

| Component | Role |
|---|---|
| **Firecrawl MCP** (required) | Web search across boards, full job-description scraping, careers pages; structured Indeed provider |
| **Apify MCP** (recommended) | LinkedIn search (structured jobs with date and location filters); Firecrawl takes over when Apify is unavailable or out of credit |
| **Google MCP** (recommended) | Drive folder and PDF CVs, Google Sheet, Gmail digest. Without it, results are shown in the chat |
| **Claude** | Onboarding, fit scoring, keyword extraction, CV writing, digest |
| **`tools/profile_check.py`** | Profile quality gate: the onboarding "stop factor" |
| **`tools/render_cv.py`** | 1-page fitting, PDF rendering, fact and keyword linting |
| **`templates/`** | Tracking sheet structure (columns, dropdowns, colours) and the digest email structure |

---

## Prerequisites

- **Claude Code** (CLI or desktop app) with a Claude subscription.
- **Python 3.9+** for the CV renderer and profile check.
- **Node.js** (LTS, from [nodejs.org](https://nodejs.org)). The Firecrawl and Apify connectors start with `npx`.
- The connectors below. The agent checks them during onboarding (read-only) and tells you what's missing.

### 1. Firecrawl (required)

1. Create an account at [firecrawl.dev](https://www.firecrawl.dev) and copy your API key.
2. Add the Firecrawl MCP server to Claude Code, for example:
   ```bash
   claude mcp add firecrawl -e FIRECRAWL_API_KEY=fc-YOUR-KEY -- npx -y firecrawl-mcp
   ```
   Or enable Firecrawl as a connector in the Claude app. With MCP, the key stays in the connector; leave
   `FIRECRAWL_API_KEY` in `.env` empty.
3. **Credits.** A search costs about 2 credits, a page scrape 1, and an Indeed provider call 5. One run uses roughly
   `titles × locations × matching boards × 2` + `jobs scraped`. Example: 3 titles × 2 locations × 12 boards ≈ 144
   credits for search, plus up to `max_scrapes_per_run` (default 80) for scraping. Cut titles or boards to spend
   less.

### 2. Apify (recommended for LinkedIn)

**Do I need Apify if I have Firecrawl?** Firecrawl alone works, but LinkedIn is the biggest job source, and Apify
searches it much better:

| | Through Apify | Through Firecrawl only |
|---|---|---|
| Results | Structured LinkedIn jobs, up to 50 per search | A few search hits per query, some only "similar jobs" |
| Date filter | Exact (24 h / week / month) | Approximate |
| Location | Precise | A bare city can match namesakes (Berlin, NJ) |
| Cost | About $0.002 per job (≈ $0.10 per 50-job search) | About 2 Firecrawl credits per search |

**How it runs:** when Apify is connected, LinkedIn goes through Apify. If an Apify run fails, or Apify's monthly free
credit is used up, the agent **automatically switches LinkedIn to Firecrawl** for the rest of that run and notes it in
the digest. All other boards always use Firecrawl. Apify's free plan includes a small monthly usage credit (see
[apify.com/pricing](https://apify.com/pricing) for the current amount).

```bash
claude mcp add apify -e APIFY_TOKEN=YOUR-TOKEN -- npx -y @apify/actors-mcp-server
```
To skip Apify entirely, set `integrations.apify.mode` to `"disabled"`.

### 3. Google MCP: Drive, Sheets, Gmail

Enable the Google Drive connector (for the Google Sheet and CV PDFs) and the Gmail connector (for the email) in
Claude: Settings → Connectors. During onboarding the agent:
- **asks for permission** before creating anything. It creates one folder, `Job Search Full-Ops Agent`, with a
  `Tailored CVs` subfolder and an `Job Search Full-Ops Tracker` spreadsheet, and writes only inside that folder;
- never sends email without your yes. A test email is optional.

**No Google Drive?** Results are shown in the chat in the same table format as the sheet (`tracking.storage:
"chat"`). CV PDFs stay in `output_resumes/`, and job history is kept in `runs/tracker.json`, so jobs aren't shown
twice. Tell the agent your statuses in the chat (*"I applied to Northwind"*). **No email?** The digest is shown in
the chat.

---

## Quickstart

```bash
git clone https://github.com/alekzendra/job-search-full-ops-agent.git && cd job-search-full-ops-agent
```
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

1. Connect Firecrawl, plus Apify and Google if you want them, as described above.
2. Open the folder in Claude Code and type **`/job-search-full-ops-agent`** or say **"set up my job agent"**. Onboarding
   takes **about 20–40 minutes**. The agent tells you this up front, and you can stop and resume any time. The time
   goes into getting your experience right, which is what makes the CVs high quality:
   1. Share your CV or describe your experience.
   2. The agent checks it against the quality criteria and asks only about what's missing.
   3. Your job goal: title, seniority, location, format and salary (advanced settings are optional).
   4. How far back the first search should go (e.g. 2 weeks).
   5. Google Sheet or chat results, and email or no email.
   6. Auto-run: days and time, or manual only.
   7. Read-only connector checks, then permissions for Drive, a test email and the schedule.
3. The first search runs right after onboarding. Later, say **"run my job search"**, or let the schedule run it.
4. Read the digest, apply, and set `Application Status` in the sheet (or tell the agent in the chat). The agent
   never resets statuses you set.

Useful phrases: *"update my profile: add a new role"*, *"change my target countries"*, *"I'm learning Looker"*,
*"tailor a CV for this link: …"*.

---

## Configuration

Three local files hold all personal data. They are in `.gitignore`; only the `.example` versions are committed.

| File | Contents | Schema |
|---|---|---|
| `user_profile.json` | Your deep profile: roles, achievements with metrics, projects, tools, guardrails (`never_claim`, excluded terms), skills you're learning, job preferences | `schemas/user_profile.schema.json` |
| `config.json` | Boards, scoring thresholds, CV layout, tracking columns, integrations, email and schedule | `schemas/config.schema.json` |
| `.env` | Secrets, only when you don't use MCP connectors (Firecrawl/Apify API mode, SMTP) | `.env.example` |

Onboarding writes these for you. Defaults worth knowing:

| Setting | Default | Meaning |
|---|---|---|
| `scoring.min_fit_score` | 75 | Jobs below this are logged but not tailored |
| `scoring.original_cv_ok_threshold` | 88 | "Strong match" level, highlighted in the sheet and digest (strong matches still get their own tailored CV) |
| `cv.page_size` / `margins_inch` | A4 / 0.5" | Layout of the 1-page PDF |
| `cv.min_quantified_bullets` | 3 | Bullets with numbers that every CV must keep |
| `cv.show_learning_line` / `max_learning_items` | true / 3 | The "Learning:" line for keywords you're learning |
| `search.first_run_lookback_days` | 14 | How far back the first search goes (asked in onboarding; up to 30) |
| `search.max_lookback_days` | 21 | Later runs cover the time since the previous run, up to 3 weeks |
| `profile_quality.*` | 3 bullets / 1 metric per role, 5–6 sentence "About me" | The onboarding quality gate |
| `tracking.storage` | `google_sheets` | Or `chat`: results shown in the chat |
| `notifications.schedule` | Mon/Wed/Fri 21:00 | Claude Code scheduled task |

### Adding a job board

Add an entry to `search.custom_boards` in `config.json`:
```json
{
  "id": "my_board", "name": "My Board", "enabled": true,
  "category": "national", "region": "cee", "coverage": "country", "countries": ["PL"],
  "method": "firecrawl_search", "domains": { "PL": "example-board.pl/job" },
  "listing_languages": ["pl", "en"],
  "query_template": "site:{domain} \"{title}\" \"{location}\"",
  "job_url_pattern": "/job/\\d+"
}
```
Run one test search, check which URLs are single job pages, and set `job_url_pattern` to match those.

---

## Job boards

All boards were live-tested on 2026-11-07. Results and fixes are in [docs/board-tests.md](docs/board-tests.md).

| Group | Boards |
|---|---|
| Aggregators | LinkedIn · Indeed (structured provider for 11 countries, site search elsewhere) · Glassdoor · Eurojobs |
| Public employment services | Platsbanken (SE) · EURES (*disabled: not reachable by scraping*) |
| Tech & startup | Wellfound · Welcome to the Jungle (incl. former Otta) · No Fluff Jobs · Landing.Jobs · Jobriver (DE) · The Hub (Nordics) · Tecnoempleo (ES) |
| Remote-first | RemoteOK · We Work Remotely · EU Remote Jobs · Working Nomads · Remote.co |
| DACH | StepStone (DE/AT/BE/NL) · XING · karriere.at · jobs.ch |
| UK & Ireland | Reed · CV-Library · Jobs.ie |
| Benelux | Nationale Vacaturebank · StepStone.be |
| Nordics | Jobindex (DK) · Platsbanken (SE) · The Hub |
| Southern Europe | InfoJobs · Tecnoempleo · Net-Empregos |
| CEE | No Fluff Jobs · Jobs.cz · Profesia · eJobs |

### Boards per country

**In every country, always:** LinkedIn and an open web search (finds employer career pages and smaller boards).
**Europe-wide:** Eurojobs. **For remote roles:** RemoteOK, We Work Remotely, EU Remote Jobs, Working Nomads,
Remote.co, Wellfound.

Local boards included by default:

| Country | Local boards |
|---|---|
| Austria | Indeed · Glassdoor · StepStone · XING Jobs · karriere.at |
| Belgium | Indeed · Welcome to the Jungle · StepStone |
| Czechia | Indeed · Welcome to the Jungle · No Fluff Jobs · Jobs.cz |
| Denmark | Indeed · The Hub · Jobindex |
| Finland | Indeed · The Hub |
| France | Indeed · Glassdoor · Welcome to the Jungle |
| Germany | Indeed · Glassdoor · Welcome to the Jungle · Landing.Jobs · Jobriver · StepStone · XING Jobs |
| Greece | Indeed |
| Hungary | Indeed · No Fluff Jobs |
| Ireland | Indeed · Glassdoor · Jobs.ie |
| Italy | Indeed · Glassdoor |
| Luxembourg | Indeed |
| Netherlands | Indeed · Glassdoor · Landing.Jobs · StepStone · Nationale Vacaturebank |
| Norway | Indeed · The Hub |
| Poland | Indeed · No Fluff Jobs |
| Portugal | Indeed · Landing.Jobs · Net-Empregos |
| Romania | Indeed · eJobs |
| Slovakia | Welcome to the Jungle · No Fluff Jobs · Profesia |
| Spain | Indeed · Glassdoor · Welcome to the Jungle · Landing.Jobs · InfoJobs · Tecnoempleo |
| Sweden | Indeed · The Hub · Platsbanken |
| Switzerland | Indeed · Glassdoor · XING Jobs · jobs.ch |
| United Kingdom | Indeed · Glassdoor · Welcome to the Jungle · Reed · CV-Library |
| Any other country | LinkedIn, web search and the Europe-wide boards only. Add local boards during onboarding |

**Add your own boards.** During onboarding the agent shows this list for each of your target countries and asks
which other local job sites to search. Sites you add are searched **in addition to** the defaults, for that country
only. The agent tests each new site once (about 2 Firecrawl credits) and tells you if search engines don't list its
jobs. Later, say *"search <site> for <country>"* to add more.

The agent never logs in to a board and uses public pages only.

---

## The CV renderer

```bash
# check a CV without writing files (fit, facts, keywords)
.venv/bin/python tools/render_cv.py runs/cv_<job>.json --config config.json --profile user_profile.json --check
```
```bash
# check bullet line breaks while writing
printf '%s\n' "Led migration of 4,000+ accounts…" | .venv/bin/python tools/render_cv.py --lint-bullets --config config.json
```
It prints a JSON report (`ok`, `pages`, `fill_ratio`, `keyword_coverage`, `errors`, `warnings`).
- **Exit 0:** OK.
- **Exit 1:** the CV must be fixed.
- **Exit 2:** a usage or config problem.

On success it writes `output_resumes/<Company>_<date>/<name>.pdf`. It never overwrites; a second CV the same day
goes into `_2`, `_3`, and so on. A sample is in `examples/cv_content.example.json`.

---

## Privacy and safety

- Your profile, config, `.env`, imported CVs, generated PDFs and run logs stay local and are gitignored.
- **Before every commit or fork you publish**, run the privacy check. It reads your personal data from your local
  files and searches every file that would be published for it. Findings are masked, and secrets are never printed:
  ```bash
  .venv/bin/python tools/privacy_check.py
  ```
  - Add `--source <file>` for other files with your data (an old CV, another profile, an `.env`).
  - Put extra private words (employers, target companies, project names) in `.privacy_terms`, one per line.
    That file is gitignored.
  - Allow a term that is public on purpose, such as your name in the license:
    `--allow "LICENSE,README.md:Your Name"`.
- The agent never logs in to job boards, never puts personal data in search queries or URLs, never creates Drive
  files without permission, and sends email only to the recipients you configured.
- The fact linter is a safety net, not a guarantee. Read every CV before you send it.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `npx: command not found` when adding a connector | Node.js not installed | Install Node.js LTS, then add the connector again |
| `/job-search-full-ops-agent` not recognised | The hidden `.claude` folder is missing, or Claude Code was opened in another folder | Check `ls .claude/skills/job-search-full-ops-agent`; open the `job-search-full-ops-agent` folder itself |
| Onboarding keeps asking questions | The profile doesn't pass the quality gate yet | Answer the listed gaps, or say "skip" to accept a gap |
| Digest says "LinkedIn via Firecrawl" | Apify run failed or free credit used up | Expected fallback; top up Apify or wait for the monthly credit |
| Onboarding stops at "Firecrawl missing" | MCP server not connected | `claude mcp list`; re-add Firecrawl; restart Claude Code |
| A board returns 0 jobs | Too narrow a query, or the board's index has no dates | Check `docs/board-tests.md`; set the board's `search_time_filter` to `null`; drop the city from its `query_template` |
| Jobs from the wrong country (e.g. Berlin, NJ) | Bare city name | Keep `{location}` as "City, Country" (default) |
| Mostly search-results pages instead of jobs | Normal for some boards | The agent opens up to 2 per board for job links; tune `job_url_pattern` |
| Firecrawl 429 / credits running out | Rate or plan limit | Lower `rate_limit_per_minute`, `max_scrapes_per_run`, titles or boards |
| `CV does not fit on one page` | Too much content | The agent cuts the weakest bullet first; check `summary_max_lines` and the bullet ranges |
| `numbers not found in user_profile.json` | A metric not in your profile | Add the real number to the profile, or remove it from the CV |
| `must keyword … is not on the CV` | Keyword not woven in | Re-run tailoring; if your profile can't support it, it isn't a real match |
| `No Unicode TTF font found` | Missing Arial / Liberation / DejaVu | Install one, or set `cv.font_files` in `config.json` |
| `reportlab requires 3.10+` | Newest reportlab on Python 3.9 | `pip install -r requirements.txt` (pins a compatible version) |
| Nothing created in Drive | Permission not granted | Say "set up Google Drive for the job agent" to re-run the permission step (sets `create_files_in_drive`) |
| Scheduled run didn't happen | App closed at the scheduled time | It runs at the next launch with a wider window; for runs while offline, use `apify_schedule` |

---

## Development

```bash
.venv/bin/python -m unittest discover -s tests
```
- `tests/test_render_cv.py`: page fitting, PDF text order, fact, keyword and Learning-line checks.
- `tests/test_config.py`: the example config validates against its schema, the board URL patterns match the
  live-tested URLs, and the sheet structure matches the tracking columns.
- `tests/test_tools_misc.py`: validation and duplicate detection (employer vs agency reposts).
- `tests/test_profile_check.py`: the quality gate passes a complete profile and catches every gap in a thin CV.
- `tests/test_privacy_check.py`: the privacy checker finds names, emails, phones, profile URLs, employers, cities and
  secrets (made-up data only).

```
.claude/skills/job-search-full-ops-agent/  SKILL.md (pipeline) · onboarding.md (first run)
schemas/                       config · user_profile · cv_content JSON Schemas
tools/render_cv.py             1-page renderer + linter
tools/privacy_check.py         finds your personal data before you publish
tools/profile_check.py         profile quality gate used by onboarding
tools/cv_rules.py              shared truth rules (measured results, never-claim meaning, years)
tools/validate.py              validates config, profile and CV files against their schemas
tools/dedupe_jobs.py           finds the same job posted on several boards or by agencies
templates/                     Google Sheet structure · digest email structure
examples/                      sample CV content
docs/board-tests.md            live board test results
docs/e2e-test-checklist.md     end-to-end user-flow checklist for testers
config.example.json  user_profile.example.json  .env.example
```

Contributions are welcome, especially new national boards. See [CONTRIBUTING.md](CONTRIBUTING.md) for the board
live-test steps, the privacy rules and the PR checklist.

## License

[MIT](LICENSE) © 2026 Oleksandra Androsiuk. You may use, modify and share this project, including commercially, as long as the license notice is kept. The software is provided as is, without warranty.
