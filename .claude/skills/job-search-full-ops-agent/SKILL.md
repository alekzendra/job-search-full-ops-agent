---
name: job-search-full-ops-agent
description: Configurable European job-search agent. Finds roles on LinkedIn and open web search in every country, plus 31 catalog job boards (Indeed, tech/startup, remote-first and national leaders across Europe) and any local boards the user adds per country via Firecrawl and Apify (LinkedIn), scores fit against the candidate's deep profile, writes a separate tailored 1-page ATS CV for every matching vacancy (job keywords built into the text, no invented facts), tracks everything in Google Sheets/Drive and emails a digest. Use when asked to run a job search, set up the job agent, or update the job-search profile, and on the configured schedule. First-time setup takes 20-40 minutes: always warn the user before starting it.
---

# Job Search Full-Ops Agent: Autonomous Job Search & CV Tailoring

All paths are relative to the repository root (the folder that contains `.claude/`).
`{config.x.y}` means a value from `config.json`; `{profile.x.y}` means a value from `user_profile.json`.

## 1. Principles

- **Claude does the thinking.** Fit scoring, ATS keyword extraction and CV tailoring happen in this Claude session.
  No LLM API keys are needed, and no script calls an LLM.
- **Facts only.** Every statement on a CV must trace back to `user_profile.json`. Never invent tools, numbers,
  employers, titles, dates or scope. Keywords may be adapted to the job description; facts and their meaning may not.
- **The user's data is the user's.** Never reset a status the user set. Never delete or overwrite a generated CV.
  Never write to Google Drive while `{config.integrations.google.permissions.create_files_in_drive}` is `false`.
  Send email only to `{config.notifications.email.recipients}`.
- **Everything is auditable.** Every job collected, dropped or scored gets one line in `runs/run_log_<date>.tsv`
  with the reason.

---

## 2. Phase 0: Configuration gate (always run first)

> **Python tools.** Every command in this skill runs the project's own Python: `.venv/bin/python tools/…`
> (Windows: `.venv\Scripts\python tools\…`). Never use a bare `python` or the system `python3`: macOS has no
> `python` command, and the system Python lacks the tools' packages (reportlab, jsonschema).
> If `.venv/bin/python` doesn't exist, tell the user the CV tools need a one-time install (about 1 minute), ask for
> a yes, then run `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. If `python3` is missing or
> older than 3.9, point to python.org and stop. Do this right after the first-message warning below (for a
> new user) and before any validation or onboarding check.

> **MANDATORY first message for a new user.** If there is no `config.json`, no `user_profile.json` and no
> `.onboarding_state.json`, your **very first reply**, before reading other files, running any check or asking
> anything else, must start with this warning (you may translate it to the user's language):
>
> ⏱ **Heads-up: setting up this agent takes about 20–40 minutes.** That time goes into getting your experience,
> results and job goal right. It's what lets me write a separate, high-quality CV for every matching vacancy,
> using only true facts about you. You can stop at any point and continue later from where we left off.
>
> Then ask whether to start now or later, and continue with `onboarding.md` Phase 0.

1. Check for `config.json`, `user_profile.json` and `.onboarding_state.json` in the repo root.
2. Validate them with `.venv/bin/python tools/validate.py` (checks both files against their schemas).
3. Route:
   - Missing, invalid or partial configuration, or `{config.onboarding.completed}` is not `true` → read
     `onboarding.md` (next to this file) and follow it exactly. Do not search until it completes.
   - The user asks to update their profile or preferences → run the matching section of `onboarding.md`.
   - A required integration (`firecrawl`; `google` when `tracking.storage` is `google_sheets`) has status `missing`
     → re-run onboarding Phase 6 only.
   - `.venv/bin/python tools/profile_check.py user_profile.json --config config.json` doesn't pass (e.g. after a manual edit)
     → run onboarding Phase 1.2–1.4 for the gaps only, then continue.
   - Otherwise → continue with section 3.

---

## 3. Inputs

| Input | Purpose |
|---|---|
| `user_profile.json` | Deep fact base (roles, achievements with metrics, projects, tools), guardrails, target preferences |
| `config.json` | Boards, scoring thresholds, CV layout, tracking columns, integrations, notifications |
| Tracking sheet | Google Sheet `{config.integrations.google.sheets.tracking_spreadsheet_id}` when `{config.tracking.storage}` is `google_sheets`. In `chat` mode, results are shown in the chat instead. |
| `{config.tracking.local_state_file}` | Local job history (`runs/tracker.json`): every job's Job ID, apply link, status and run date, plus `last_run`. Always kept up to date; in `chat` mode it's the only history |
| `runs/` | Per-run working files: candidates, analysis, run log |

Set `D` to today's date (`YYYY-MM-DD`).

---

## 4. Workflow

### Step 1: Status & duplicate check
1. Read `{config.tracking.local_state_file}`. With `google_sheets`, also read every tab of the tracking sheet and
   take each `Job ID` and `Apply Link` with its `Application Status`; the sheet wins when the two differ.
2. In `chat` mode, statuses come from the user telling you (*"I applied to Northwind"*, *"skip the Contoso one"*).
   Update the tracker when they do.
3. Save the merged statuses to `runs/status_$D.json` as `{ "<Job ID or Apply Link>": "<status>" }`.
4. Skip any vacancy that is already known. Never touch rows whose status is in `{config.tracking.closed_statuses}`.

### Step 2: Search window
- **First run** (no `last_run` in the tracker): search the last `{config.search.first_run_lookback_days}` days. If
  that is `null`, ask first (1 week / 2 weeks / 3 weeks / 1 month) and save the answer.
- **Later runs**: search the time since `last_run`, rounded up to whole days, at least 1 day and at most
  `{config.search.max_lookback_days}` (21 days = 3 weeks). If the gap was longer, search the last 21 days and say so
  under Issues in the digest.
- Use the window everywhere: Apify `datePosted` (the smallest of `past24Hours` / `pastWeek` / `pastMonth` that covers
  it), Indeed `posted_within_days`, Firecrawl `tbs` (`qdr:d` / `qdr:w` / `qdr:m`). Then drop jobs whose posting
  date is older than the window.

### Step 3: Collect jobs
Build the search matrix from the profile:
- **Titles:** `{profile.preferences.target_titles}` + `{profile.preferences.adjacent_titles}`
- **Locations:** each entry in `{profile.preferences.locations}` (country, cities, work modes). An entry with
  `country: "*"` means remote anywhere, filtered by `{profile.preferences.remote_scope}`. Fill `{location}` as
  **"City, Country"** in English (e.g. "Berlin, Germany"), or just the country name when no city is set. A bare
  city name matches namesakes elsewhere (live test: "Berlin" returned Berlin, NJ).
- **Boards:** every entry in `{config.search.boards}` + `{config.search.custom_boards}` with `enabled: true`,
  matched to each location as follows (`.venv/bin/python tools/list_boards.py <CC> --config config.json` shows the result):
  - `always_on: true` (LinkedIn and web search): **every** location, in every country;
  - user-added boards (`added_by: "user"`) are searched for their countries **in addition to** the catalog boards,
    never instead of them;
  - `coverage: "pan_eu"` or `"country"`: the location's country must be in `countries` (`"*"` matches all);
  - `coverage: "remote_eu"` / `"remote_global"`: only for locations that allow `remote` work;
  - skip a board when none of its `listing_languages` is a language the candidate can work in
    (`{profile.preferences.work_languages}`). This avoids spending Firecrawl credits on listings the language
    pre-filter would drop anyway.
- **Search terms per board:** national boards are mostly in the local language. For a board whose
  `listing_languages` don't include English, search with the English title **and** the usual local-language title
  (e.g. "Projektmanager" on stepstone.de, "Projectleider" on nationalevacaturebank.nl), but only for languages the
  candidate works in. Keep the local title next to the English one in the run log.
- **Logins:** never log in to a board. If a listing's full text is hidden behind a login
  (`requires_login_for_full_text`), use the public text if it's enough to score the job; otherwise log
  it as `skipped: login required`.

For each title × location × board, use the board's `method`:

| `method` | How |
|---|---|
| `firecrawl_search` | `firecrawl_search` with the board's `query_template` filled in (`{domain}` from `domains[<country>]` or `domains["*"]`). Use `limit: {config.integrations.firecrawl.search_results_per_query}` and `tbs: {config.integrations.firecrawl.search_time_filter}` (`qdr:d` if the window is 1 day). If the board sets `search_time_filter: null`, send no `tbs`, and check the posting date on each job page instead. |
| `firecrawl_web_search` | Open web search (like a Google search) with the board's `query_template`, without `site:`. Pass `excludeDomains` = the board's `exclude_domains` plus the domains of every other board searched for this country, so you only get new sources (employer career pages, smaller boards). Same `limit` and `tbs` as above. There's no `job_url_pattern`: classify each hit by its content (see *Job pages vs search-results pages*). |
| `firecrawl_provider` | For countries in `provider.countries`: `firecrawl_scrape` with `alexandria: {provider, capability, options}`. For Indeed, the options are `country`, `query` = title, `location` = city (or `"Remote"`), `posted_within_days` = the search window, `limit` ≤ 100, and `remote: true` for remote-only locations. The records already hold title, company, location, dates, language and remote/hybrid tags, so fetch the full description only for jobs that pass the pre-filters. For other countries, fall back to `firecrawl_search` with the board's `domains` + `query_template`. |
| `firecrawl_scrape_url` | Fill in `search_url_template` and `firecrawl_scrape` the results page, then collect the job links on it. |
| `apify_actor` | Used for **LinkedIn** when `{config.integrations.apify.mode}` is not `disabled`. Call `call-actor` with `apify_actor` and input = the board's `apify_actor_input` + `keywords` = title, `location` = "City, Country" (or the country name, or `"European Union"` for EU-wide remote), `datePosted` from Step 2, `limitPerSource` = `{config.integrations.apify.max_results_per_search}`. Read the dataset with `get-dataset-items`. Keep title, company, location, posted date, job URL and description. **Fallback:** if Apify isn't connected, the run fails, or the error mentions usage limits, credit or payment (for example, the free monthly credit is used up), switch LinkedIn to the board's `fallback_method` (`firecrawl_search`) for the rest of this run, and say so under Issues in the digest. |
| `public_api` | Call the board's public JSON endpoint directly. |

**Job pages vs search-results pages.** Search hits are a mix of single job ads and search-results pages
(e.g. `/jobs/project-manager-jobs-in-london`). Sort each hit with the board's `job_url_pattern`:
- **matches** → a job page: keep it;
- **no match, same domain** → a search-results page: scrape it once with `formats: ["links"]`, keep the links that
  match `job_url_pattern`, and drop the rest. At most 2 search-results pages per board per run, to protect credits.
- **Board without a `job_url_pattern`** (web search, and user-added boards whose test didn't show a clear pattern):
  scrape the hit (markdown). It's a single job ad if the page has `JobPosting` structured data (`jsonLd`), or one
  job title with a description and an apply button or link. Otherwise it's a search-results page or not a job (a
  salary page, an article): collect at most 10 links on the same domain that look like single ads (their path
  contains a word like job, vacancy, career, position, opening, stelle, vacature, emprego, oferta, praca, or an
  ID), at most 2 such pages per board per run. Drop everything else.

Also check `{config.search.company_watchlist}`: scrape each `careers_url`, and search LinkedIn by company name for
priority A every run, B when credits allow, C once a week.

**Fetch full job descriptions.** `firecrawl_scrape` each job URL with `formats: ["markdown"]` and
`onlyMainContent: true`. Strip `utm_*` and other tracking parameters first. Don't use the `json` format (it costs
several times more). Stay within `{config.integrations.firecrawl.rate_limit_per_minute}` and
`{config.integrations.firecrawl.max_scrapes_per_run}`. Store each page as
`{ "url", "title", "company", "location", "posted_date", "source", "text", "jsonLd" }` (`jsonLd` = the page's
`JobPosting` structured data, if present).

**Fallbacks.** If Apify fails or runs out of credit, use Firecrawl for that board. Never skip a source silently.
Report any source that returned 0 jobs.

**Links the user sends.** Fetch them the same way, mark them `source: "manual"`, and skip the automatic pre-filters
below so they are always scored and reported.

**Deduplicate.** First by canonical URL. Then run
`.venv/bin/python tools/dedupe_jobs.py runs/candidates_$D.json --out runs/candidates_$D.json`. It also catches the same vacancy
under different company names (the employer on one board, a recruiting agency on another) by comparing title and
description text. It keeps the employer's own post, and lists what it dropped and why; add those to the run log.
Assign `Job ID` = `<board id>-<board's job id>`, or a hash of the canonical URL. Cap `runs/candidates_$D.json` at
`{config.search.max_jobs_per_run}` (newest first).

### Step 4: Pre-filters (deterministic, before scoring)
Drop a job and log the reason when any of these apply:
- **Duplicate** or already in the tracking sheet (Step 1).
- **Geography / work mode.** The job's country + work mode must match an entry in `{profile.preferences.locations}`.
  - Decide the work mode from the **job description text**, not from a board's filter label. A board's "remote"
    tag on its own is not proof.
  - "Remote, but must live in <country>" counts as remote **in that country only**. Allow it only if that country
    is in `{profile.preferences.remote_scope.accept_country_locked_remote_in}`, or is a country the candidate
    already targets.
  - Respect `max_timezone_offset_hours_from_home` when the job states working hours or a time zone.
- **Language.** Drop the job if it requires a language the candidate doesn't have at B2 or above, or (when
  `{config.search.drop_if_jd_language_not_in_profile}`) if the description is written in a language outside
  `{profile.preferences.work_languages}`.
- **Industries** in `{profile.preferences.industries_exclude}` and explicit `{profile.preferences.deal_breakers}`.
- **Visa.** Drop the job if the candidate needs sponsorship for that country and the job says it offers none.
- **Residency.** Some remote postings accept only EU/EEA tax residents, or residents of one country ("must be
  based in / tax resident in…"). Check them against `{profile.personal.work_authorization}` and
  `{profile.personal.location}`; drop the job if the candidate doesn't qualify. Treat the UK and Switzerland as
  outside the EU/EEA, unless the posting says otherwise.
- **Salary.** If a salary is stated and is below `{profile.preferences.salary.minimum}`: drop it when
  `drop_below_minimum` is true, otherwise only flag it.

### Step 5: Fit scoring (Claude)
Read **every** remaining full job description (in batches of about 8) and score it with this prompt:

> **Job Match Analysis.** You are an expert recruiter and career advisor. Compare the candidate's full profile
> (`user_profile.json`: roles, responsibilities, achievements, projects, tools, education, certifications,
> languages) with the job description.
>
> Evaluate:
> 1. Role alignment and seniority (weight `{config.scoring.weights.role_and_seniority}`)
> 2. Hard skills and tools overlap (weight `{config.scoring.weights.hard_skills_and_tools}`)
> 3. Domain experience and key responsibilities (weight `{config.scoring.weights.domain_and_responsibilities}`)
>
> Rules:
> - Do NOT inflate scores. Give a Fit Score from 0 to 100.
> - Calculate experience from the role dates in the profile. For each year the job requires beyond that, subtract
>   `{config.scoring.penalties.years_required_gap_per_year}` points. Requirements above
>   `{profile.preferences.max_years_required}` years cap the score at 30.
> - Line-management roles: count direct reports in `experience[].scope` as full evidence; mentoring or informal
>   leadership counts as partial evidence only.
> - A required language the candidate lacks caps the score at `{config.scoring.penalties.missing_required_language_cap}`.
> - A score of `{config.scoring.original_cv_ok_threshold}` or more requires the candidate's existing material to cover
>   essentially every stated requirement.
> - Output: `fit_score`, `work_type` (starting with `Remote`, `Hybrid` or `Onsite`, taken from the job description
>   text), and a 1–2 sentence `notes` explaining the score. Keywords are extracted in Step 6.

Strictness: `balanced` adds about 5 points of leniency on partial matches; `lenient` about 10. Save all results to
`runs/analysis_$D.json`. Only jobs scoring `{config.scoring.min_fit_score}` or more go on to tailoring.

### Step 6: ATS keyword extraction (Claude)
For each job that passed, build the list of keywords that this job's CV must contain:
1. Extract the **ATS keywords**: the exact noun phrases a parser would match, in the job post's own spelling and
   casing (e.g. "stakeholder management", "Jira", "SAFe", "PSPO", "B2B SaaS"). Cover hard skills, tools,
   methodologies, certifications, domain terms and the job title itself. Usually 10–25 keywords per post.
   - `priority: "must"`: stated as a requirement, or repeated in the post
   - `priority: "nice"`: "nice to have", or mentioned once
   - If the post gives both an acronym and the full form, keep the pair as one keyword in the form
     "Search Engine Optimization (SEO)", so both spellings land on the CV.
2. Classify each keyword against `user_profile.json`:
   - `matched`: the profile has it with the same meaning
   - `matched_synonym`: the profile has the same thing under other wording (e.g. profile "customer interviews" ↔
     job "user research"). On the CV, use **the job's wording**.
   - `learning`: not used professionally, but listed in `{profile.skills.learning}` (the user confirmed they are
     learning it)
   - `missing`: nothing in the profile supports it
3. For every `matched` / `matched_synonym` / `learning` keyword, record `evidence`: text copied exactly from
   `user_profile.json` (a skill, a tool, or a phrase from an achievement) that proves it. No evidence means the
   keyword is `missing`.
4. Save the list as `target_keywords` in the analysis. It goes into the CV content file in Step 7.

**Keywords the candidate is learning or doesn't have.**
- `learning` keywords go on the CV's **Learning line** only (Step 7.4), never in the summary, the headline or a bullet,
  because those present skills as experience. This puts the keyword on the CV for the ATS and tells the
  recruiter the truth.
- `missing` keywords stay off the CV. The digest asks about each one (Step 10): *"Looker: have you used it at work, are
  you learning it, or neither?"* The answer updates the profile:
  - used it at work → follow the onboarding profile-update flow to add it with real evidence (skills/tools + where it was used);
  - learning it → add it to `skills.learning` with status, detail and `confirmed_at`;
  - neither → nothing changes. The keyword remains a gap, and the digest lists it as a skill worth learning.

  The next CV for a similar job then embeds it in the right place.

### Step 7: CV decision & tailoring (Claude)
**Questions before tailoring (only when the user started the run themselves and is in the chat).** If any job that
passed scoring has `must` keywords with status `missing`, ask **one** short batch before writing the CVs, at most
5 keywords, the most frequent first: *"Before I write the CVs: Looker: used it at work / learning it / neither?
SAFe: …"*. Update the profile with the answers (see Step 6), then tailor. Use "used it at work" answers only
once the user has said where and how. For scheduled runs, don't wait: tailor with what the profile has and ask in the
digest.

**One CV per vacancy.** Every job with `fit_score ≥ {config.scoring.min_fit_score}` gets **its own** tailored CV,
built from scratch for that job post. Never reuse one general CV across vacancies, and never skip tailoring because
the score is high. Two jobs with similar titles still get separate CVs, because their keywords and priorities differ.
`CV Action = "Tailored CV Generated"`. **The tailored CV must contain the job's supported keywords inside its own
text, not as a separate list:**
  1. **Headline**: the job title from the post if it matches a role the candidate held or a target title in the
     profile, plus 1–2 top `must` keywords.
  2. **Summary** (≤ `{config.cv.summary_max_lines}` lines): start from `{profile.master_summary}` and its tone.
     Rebuild it around the top 3 requirements, using 3–5 `must` keywords in the job's wording, and only true facts.
     State the real scope honestly (part-time, volunteer or contract roles are labelled as such).
  3. **Skills and Tools lines**: up to 8 skills plus a `Tools:` line. Put the job's keywords first, written exactly as
     in the post (e.g. post "Stakeholder Management", profile "managing stakeholders" → write "Stakeholder
     Management"). Include only items backed by `{profile.skills}` or the evidence.
  4. **Learning line** (only when `{config.cv.show_learning_line}`): after the `Tools:` line, write
     `Learning: <item> • <item>`, with up to `{config.cv.max_learning_items}` of this job's `learning` keywords, most
     important first. Use only items from `{profile.skills.learning}`, written in the job's spelling. Leave the
     line out when the job has no `learning` keywords; never fill it with unrelated items.
  5. **Roles**: show up to `{config.cv.max_roles_shown}` roles, most recent first. For each role, choose bullets
     from that role's `achievements[]` where `allowed_in_cv: true`, ranked by how many target keywords their facts
     support, then by whether they include a metric. Use `{config.cv.bullets_most_recent_role}` bullets for the most
     recent role and `{config.cv.bullets_older_roles}` for the others.
  6. **Weave keywords into the bullets**: start from each approved `cv_bullet` and rewrite it so the relevant
     keywords appear naturally in context (e.g. "A/B tested 3 variants" → "ran A/B testing of 3 variants" when the post
     asks for "A/B testing"). Every `must` keyword should appear at least once in the summary or a bullet, not only in
     the skills line, so it reads as used experience. You may change wording and clause order. You may never change
     numbers, scope, ownership or outcomes. Format: `Action verb + task + quantifiable result`.
  7. **Density**: each keyword appears 1–3 times across the CV. More than that reads as keyword stuffing to recruiters
     and some ATS. Never use hidden or white text, keyword blocks, or invisible lists.
  8. Keep at least `{config.cv.min_quantified_bullets}` quantified bullets on the page.
  9. **Certifications**: only those with `show_on_cv: true`, in the order `{profile.cv_preferences.certifications_order}`.
     Put a certification the job requires first.
  10. **Guardrails check before rendering**: nothing that *means* an item from `{profile.guardrails.never_claim}`
     or a role's `never_claim`, in any wording. "Lead a team of 5 engineers" breaks a "people management" rule just
     like the exact phrase does. No `{profile.guardrails.excluded_terms}`, and no budget claims when
     `scope.budget_owned` is null. "N years" in the summary or headline must match the role dates: use the rounded
     total, or "N+ years". If a check fails, rewrite the text. Never lower the bar. (The renderer's `--profile` lint
     checks all of this again.)
  11. Write the result to `runs/cv_<Job ID>.json` following `schemas/cv_content.schema.json` (see
     `examples/cv_content.example.json`). Set `role_id` on every role so the linter can match it to the profile, and
     include the full `target_keywords` list from Step 6, with `placed_in` for each keyword you embedded.

### Step 8: 1-page ATS rendering
**Layout** (all values from `{config.cv}`):
- Page size `page_size`, margins `margins_inch`, font `font_family` at `font_size_body_pt`, headings in `accent_color`.
- Section order: `section_order`. Single column, no tables, text boxes, icons, photos, headers or footers, so ATS
  parsers read it correctly. Section headings use standard names: "Professional Summary", "Skills", "Experience",
  "Education", "Certifications", "Languages".
- Header: name, headline, and a contact line `City, Country • phone • email • LinkedIn` (links clickable).
- Each role: title on one line, then `Company | City or Remote | Mon YYYY – Mon YYYY`, then bullets.
- Education and certifications: one line each.

**Text density:**
- Every bullet is exactly 1 or 2 full lines, with no 1–2-word "widow" lines.
- **Strictly exactly one page.** The page must not end with a large empty area either.

**Renderer: `tools/render_cv.py`.** The layout above is built in. It reads `{config.cv}` and never changes the
content; only you do that.
- While writing bullets, check their line breaks:
  `printf '%s\n' "bullet 1" "bullet 2" | .venv/bin/python tools/render_cv.py --lint-bullets --config config.json`
- Check the whole CV without writing files:
  `.venv/bin/python tools/render_cv.py runs/cv_<Job ID>.json --config config.json --profile user_profile.json --check`
- The JSON report gives `ok`, `pages`, `fill_ratio`, `errors` and `warnings`. Exit code 1 means the CV must be fixed;
  exit code 2 means a usage or config problem. **Always pass `--profile`**: it blocks figures that the profile
  doesn't contain with the same unit (percent, multiple, money with amount and currency, plain number; numbers
  written as words count too; dates and phone digits in the profile are not evidence), employers, titles and
  certifications that are not in the profile, never-claim rules (matched by meaning, not only exact phrase),
  excluded terms, budget claims without `budget_owned`, and "N years" claims that don't match the role dates.
  It counts **bullets with a measured result** using the same rule as the onboarding quality gate
  (`tools/cv_rules.py`): a number tied to a change, share, money or scale. "Q3 2023", "Python 3" or "a team of 5"
  don't count. It asks for `{config.cv.min_quantified_bullets}`, but never more than the profile has for the roles
  shown. Bad input (e.g. a number where text is expected) stops with exit 2 and the exact field. It also checks
  **keyword coverage**:
  - a `must` keyword missing from the CV is an error, and a `nice` keyword missing is a warning;
  - evidence that isn't found in the profile is an error;
  - a `missing` keyword that appears on the CV anyway is an error;
  - a `learning` keyword that appears outside the Learning line is an error, and so is a Learning item that isn't
    in `skills.learning`, or more than `max_learning_items` items;
  - it warns when a `must` keyword appears only in the skills lines, or more than 3 times.

  The report's `keyword_coverage` (e.g. `must: 7/7`) goes into the tracking sheet notes.
- A number calculated from profile facts (e.g. total years of experience) must be declared in `derived_numbers`
  with its basis. The report lists these for review.

**Fitting loop.** The renderer stretches or compresses spacing and, if needed, reduces the font size (never below
9.5 pt) to fill exactly one page. Then:
- **"does not fit on one page"**: cut content in this order, then re-check: the weakest bullet without a metric
  (never one needed for `min_quantified_bullets`), a bullet from the oldest role, one summary line, the oldest role.
- **Widow / over-2-lines warnings**: rewrite that bullet (shorter to make 1 line, or more true detail for a full
  second line).
- **"page only N% full"**: add the next-best true bullet from the profile (the warning says how many are unused).
  If every profile bullet for these roles is already on the page, the renderer grows the font slightly and reports
  `short_cv` instead of a warning. A shorter CV is fine; don't pad it.
- Repeat until `ok: true` with no layout warnings, at most 5 rounds. Then report any warning you couldn't fix.

**Output: PDF only.** The PDF is the version verified to be exactly one page. Never create DOCX or Google Doc copies.
- Render the final version without `--check`. By default the PDF goes to
  `{config.cv.local_output_dir}/<Company>_<YYYY-MM-DD>/<file name>.pdf`, named after
  `{config.cv.file_name_template}`. The renderer **never overwrites**: a second CV for the same company on the same
  day goes to `<Company>_<YYYY-MM-DD>_2/`, then `_3/`, and so on.
- With Drive permission: upload the PDF unchanged (no conversion) to
  `{config.integrations.google.drive.cv_subfolder_id}`.
- The `Tailored CV Link` column gets the Drive link of the PDF, or its absolute local path in `chat` mode.

### Step 9: Record the results
**Always:** add every new job (and its scores, CV path and status) to `{config.tracking.local_state_file}`.

**`google_sheets`:**
1. Open the tracking spreadsheet.
2. Select the tab named `{config.tracking.tab_name_template}` for the current period (`tab_strategy`).
   If it doesn't exist, **duplicate the `{config.integrations.google.sheets.template_tab_name}` tab** (keeping
   header colours, column widths, fonts, dropdowns), clear the data rows, then fill it. Never create a blank tab.
3. Upsert rows by `Job ID` using the columns in `{config.tracking.columns}`. Each column's type, format and owner
   are defined in `templates/google_sheet_structure.json`; follow its `format_hint`s. Rules:
   - New rows get `Application Status = "New"`.
   - Never overwrite a status the user has changed, or any other column whose `owner` is `"user"`.
   - Sort the tab by `Fit Score (%)`, highest first.
   - `Source` = the board `name`, or `Manual`.
   - `ATS Keywords Matched` / `ATS Keywords Missing` come from Step 6.

**`chat`:** nothing is written to Google. The results table is shown in the chat in Step 10.

### Step 10: Deliver the results
**Email on** (`{config.notifications.email.enabled}`): send via `{config.notifications.email.provider}` to
`{config.notifications.email.recipients}`, following **`templates/email_template.md`**. The wording may vary; the
sections, their order and the facts may not:
1. Greeting, then a run summary: date and window, sources with counts, the funnel
   (collected → in scope → new → passed pre-filter → Fit ≥ threshold), the sheet tab and synced status changes.
2. The matches table (Fit · Role → apply link · Company · Mode · Note with `⚠` flags and `gap:` · CV PDF link),
   at most `max_rows_in_table` rows.
3. Near misses within `near_miss_margin` points below the threshold.
4. Keyword coverage and **"Quick questions"** about the most frequent `missing` keywords (*"<keyword>: used it at
   work / learning it / neither?"*). When the user answers (in chat, or in a reply they ask Claude to read), update
   the profile as described in Step 6.
5. Watchlist line, then issues (sources with 0 jobs, failed scrapes, Apify → Firecrawl fallback, credit problems),
   then the signature.

Link the Google Sheet tab when `link_tracking_sheet` is true. CVs are linked as PDFs, never attached as DOCX. Skip
the email when there are no new matches and `send_when_no_matches` is false.

**Email off:** present the same digest in the chat (see *Chat report* in `templates/email_template.md`). In `chat`
storage mode, add the **full results table** with the columns of `templates/google_sheet_structure.json`, in the
same order.

### Step 11: Close the run
- Write `runs/run_log_$D.tsv` (job id, source, decision, reason, fit score).
- Set `last_run` in `{config.tracking.local_state_file}` to now.
- If the email was sent, give a short summary in the chat, plus anything that needs attention (failed sources,
  keywords missing from the profile, profile gaps that capped scores).

---

## 5. Scheduling

When `{config.notifications.schedule.enabled}` is true, the run is triggered on `days` at `time` in `timezone` by:
- `claude_scheduled_task` (default): a Claude Code scheduled task with the prompt "run my job search". If the
  laptop was off, the run happens at the next launch, and Step 2 covers the gap (up to 3 weeks).
- `apify_schedule`: an Apify schedule that collects jobs while the laptop is off. Scoring and tailoring still
  happen at the next Claude session.

## 6. Integration roles

| Integration | Role in the pipeline |
|---|---|
| **Firecrawl** (required) | Web search across boards (Step 3), full job-description scraping, careers pages, JS-heavy pages |
| **Apify** (recommended) | LinkedIn collection (structured jobs with date and location filters); Firecrawl takes over when it's unavailable or out of credit |
| **Google MCP** (recommended) | Drive folder and CV PDFs (Step 8), Google Sheet (Steps 1 and 9), Gmail digest (Step 10). Without it, results are shown in the chat |
