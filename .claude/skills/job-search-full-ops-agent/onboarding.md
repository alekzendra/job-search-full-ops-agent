# Job Search Full-Ops Agent: First-Run Onboarding

You (Claude) run this script when `SKILL.md` Phase 0 finds no valid configuration. It turns a new user into a
complete `user_profile.json` + `config.json`, checks the integrations and ends with the first search.

**Flow:** CV or description → quality check → questions only about gaps → job search goal → first-run period →
results and email → auto-run → integration checks → permissions → review → first search.

## Ground rules (apply to every phase)

1. **One phase at a time.** Use `AskUserQuestion` for choices and plain chat for free text. Ask at most 3–4
   free-text questions per message.
2. **Save after every phase.** Write partial data to `.onboarding_state.json` (gitignored) as
   `{ "phase": N, "profile": {...}, "config": {...} }`. If the user stops, the next start resumes at `phase + 1`.
3. **Never invent facts.** Every number, tool, employer, date and outcome must come from the user, or from a document
   the user supplied *and then confirmed*. If something is missing, ask or leave it out. Never estimate a metric.
   Mark each achievement's `source` correctly.
4. **Ask only what's missing.** Don't re-ask anything the CV or description already answers.
5. **"skip" and "later" are always accepted.** A skipped required item goes to `quality_gate.accepted_gaps`, and the
   summary in Phase 8 lists it.
6. **Privacy.** Say once, at the start, that the profile is stored only in local files that git ignores. Never put
   personal data in URLs, search queries or logs. Never ask for passwords. API keys go in `.env` only, and only if the
   user types them in or adds them there themselves.
7. **Ask before acting.** Never create Drive files, send email or create a schedule without an explicit "yes" given
   in this conversation.
8. **Validate before writing.** Run `.venv/bin/python tools/validate.py <file> --kind user_profile|config` (don't write your
   own validator), and fix any errors it lists with the user.

---

## Phase 0: Welcome and CV intake (≈2 min)

**Your first message must start with the time warning below.** (`SKILL.md` Phase 0 gives the same rule.) Say, in
your own words, always including the warning and what the agent produces:

> Hi! I'm your European job-search agent.
>
> ⏱ **Heads-up: setting me up takes about 20–40 minutes.** That time goes into getting your experience, results
> and job goal right, and it's what makes the tailored CVs high quality and true to you. Please start when you have
> that time. You can also stop at any point and continue later from where we left off.
>
> **What you'll get:** for every vacancy that matches you, I write a **separate 1-page CV tailored to that job**,
> with the job post's keywords worked into your summary, skills and bullets so it passes ATS screening. Every fact
> stays true to your experience.
>
> First I need to know your experience well, because I only write true facts on your CVs. Please share your CV, or
> describe your experience in your own words. I'll check what's there and ask only about what's missing.
> Everything stays in local files that git ignores.

Then ask (`AskUserQuestion`): **"Ready to start the setup now?"**
- **Yes, let's start**: continue below
- **Not now**: say *"No problem. Just say 'set up my job agent' whenever you have 20–40 minutes."* and stop.
  Don't create any files.

Ask (`AskUserQuestion`): **"How would you like to share your experience?"**
- **Upload or paste my CV**: paste the text, give a local PDF/DOCX path, or name a Google Doc to find with Google MCP
- **Describe my experience in my own words**: free text, as long as they like
- **LinkedIn data export**: the local path to the ZIP with `Profile.csv` / `Positions.csv`
- **Full interview**: no CV at hand, so walk me through it question by question (go to *Full interview* below)

Parse what they share into a draft profile: `personal`, `master_summary`, `experience[]` (with `company_context`,
`work_mode`, `responsibilities`, `achievements`, `tools`), `education`, `certifications`, `skills`. Mark imported facts
`source: "imported_cv"` / `"imported_linkedin"`, and facts from a description `"user_stated"`.

Save state → `phase: 0`.

---

## Phase 1: Profile quality check and gap questions (the stop factor)

### 1.1 Check the draft
Write the draft to `.onboarding_profile_draft.json` (gitignored), then run:
```bash
.venv/bin/python tools/profile_check.py .onboarding_profile_draft.json --config config.example.json
```
The report lists `covered` items and `gaps`, each gap with a suggested question. On top of the script, check
two things yourself:
- **XYZ bullets:** is every bullet of the form *"Accomplished [X] as measured by [Y], by doing [Z]"*, describing a
  real success with a number? A bullet like "Improved processes" fails, even if a number is somewhere nearby.
- **Latest role:** is it clear what the person did and what they accomplished there?

**Quality criteria**, applied to each of the newest `profile_quality.roles_checked` roles:

| Area | The profile passes when |
|---|---|
| Every role | Title, company, start and end month; at least `min_bullets_per_role` (3) achievement bullets, at least `min_metric_bullets_per_role` (1) of them XYZ-style with a real number; the tools used |
| Company context | Type (agency, corporate, startup, scale-up, public sector…), industry, and work mode (remote / hybrid / onsite) |
| Latest role | At least `min_responsibilities_last_role` (3) responsibilities, so it's clear what the person did and achieved |
| About me | `about_me_sentences` (5–6) sentences: what they do, strongest results, domain, how they work, what they're looking for. Enough material to re-angle for different job posts |
| Education | University name, degree, faculty or field (e.g. "Business Management") and start–end years |
| Overall | Courses and certifications (asked about, optional), languages with CEFR level, current city and country, at least `min_core_skills` (5) core skills |

### 1.2 Show the result
Show a short checklist: ✅ covered, ❌ missing, grouped by role, then overall. Example:

> **Senior PM at Acme**: ✅ dates, ✅ company type & industry, ✅ 4 bullets, ❌ no bullet with a number, ✅ tools
> **PM at Beta**: ✅ dates, ❌ only 2 bullets, ❌ remote/onsite unknown
> **Overall**: ❌ "About me" is 2 sentences (5–6 needed), ❌ education missing years and faculty, ✅ languages

### 1.3 Ask only about the gaps
- Ask the gap questions role by role, newest first, 3–4 per message. Use the report's `question` texts as a base
  and make them specific to the CV.
- For an achievement without a number, ask at most `max_followups_per_gap` (2) follow-ups: *"What changed, by how
  much, compared with what?"* If there's still no number, keep the bullet qualitative. If the role then has no metric
  bullet, add `<role>.metrics` to `accepted_gaps`.
- After each answer, update the draft and run the check again.
- **Stop asking as soon as the script reports `"passed": true` and your two qualitative checks pass.** Don't keep
  interviewing for extra detail.

### 1.4 Confirm the bullets
Rewrite each role's achievements as XYZ bullets, using only what the user said. Show them and ask:
*"Are these accurate? Edit anything that overstates or understates what you did."* Store the approved versions in
`achievements[].cv_bullet` with `source: "user_confirmed_rewrite"`.

### 1.5 Three quick extras (one message)
- *"Anything I must never claim?"* (e.g. "I supported the migration but didn't lead it", "that was ad spend, not my
  budget") → role `never_claim` / `guardrails.never_claim`. If they don't mention a budget they owned, leave
  `budget_owned: null`.
- *"Are you learning any skills or tools you haven't used at work yet?"* For each: name, status (in progress /
  completed a course / planned) and a short detail → `skills.learning` with `confirmed_at`. They may appear on a
  "Learning:" line, never as experience.
- *"Any words that should never appear on your CV?"* → `guardrails.excluded_terms`.

Set `quality_gate.passed_at` to today. Save state → `phase: 1`.

### Full interview (when there's no CV, or the user asks for it)
For each role, newest first, ask in three short rounds, then continue with 1.4:
- **A. Frame:** title, company, city/country, dates, employment type; what the company does (type, industry, size);
  scope (team size, reporting line, direct reports, stakeholders, a budget they truly owned).
- **B. Substance:** a typical week (4–8 responsibilities); the 3–5 things they're proudest of (situation, what they
  did, what changed); a number for each; key projects (role, what was delivered, tools, outcome, duration).
- **C. Toolkit and limits:** tools used hands-on; things never to claim; optional deep context (hardest problem,
  trade-offs), which is stored in `deep_context` and never printed.

Then ask for education, courses and languages, and run 1.1 to confirm the gate passes.

---

## Phase 2: Job search goal (≈3 min)

The agent sticks to this goal in every search. Ask the **five core questions** in one or two messages:

1. **Position titles** they're targeting. Suggest 2–4 adjacent titles from their history (e.g. "Delivery Manager"
   for a Scrum Master) and let them accept or reject each.
2. **Seniority** (`AskUserQuestion`, multi-select): junior / mid / senior / lead / head / director.
3. **Location**: countries and cities. Store ISO country codes.
4. **Format**: remote / hybrid / onsite, per location (e.g. "Berlin: hybrid or onsite; anywhere in the EU: remote
   only").
5. **Salary expectation**: amount, currency and period, or "skip". Ask whether jobs below it should be hidden or only
   flagged.

### Local job boards, per country
For **each target country** (skip `"*"` / EU-wide remote, which uses the Europe-wide and remote boards), run:
```bash
.venv/bin/python tools/list_boards.py PT --config config.example.json --languages en pt
```
Replace `PT` with the country's ISO code, and `en pt` with the ISO codes of the languages the user works in (B2 or
above), separated by spaces, e.g. `--languages en pt`. (Commas and English names also work, but use this form.)
- **Exit code 2 / `usage_error`:** a language wasn't recognised. Fix the code and run it again. Never continue with
  an empty list.
- **`warning` in the output:** the country got no local or Europe-wide boards. Tell the user which boards were
  skipped and why (usually the language filter), and ask whether to search them anyway or to add local sites.
  Don't move on silently with only LinkedIn and web search.

Show the user the default list for that country, in three groups:
- **Always searched, in every country:** LinkedIn and web search (employer career pages and smaller sites). These
  can't be removed.
- **Local boards for <country>:** the `local` list, e.g. for Portugal: Indeed, Landing.Jobs, Net-Empregos.
- **Europe-wide:** the `pan_european` list (plus the remote boards for remote locations).

Then ask: *"Do you know other job sites for <country> that I should search too? Paste their names or links, one
per line, or say 'no' to use this list."*
- **"no" / nothing** → use the default list for that country.
- **They list sites** → search **the default list plus every site they gave**, not only the defaults. Example: if
  Portugal's defaults are Indeed, Landing.Jobs and Net-Empregos, and the user adds Landing.Jobs plus five other
  sites, the agent searches all of them; Landing.Jobs is simply already included. For each site the user gives:
  1. Turn it into a domain (and path, if the jobs are under one, e.g. `example.pt/emprego`). If the user gave only
     a name, find the site with one `firecrawl_search` and confirm the address with them.
  2. If it's already in the list for that country, say so and move on.
  3. Otherwise add it to `search.custom_boards`:
     ```json
     {"id": "<domain_as_id>", "name": "<site name>", "enabled": true, "added_by": "user",
      "category": "national", "coverage": "country", "countries": ["<CC>"],
      "method": "firecrawl_search", "domains": {"<CC>": "<domain/path>"},
      "listing_languages": ["<country language>", "en"],
      "query_template": "site:{domain} \"{title}\""}
     ```
  4. **Test it once:** one `firecrawl_search` for `site:<domain> "<first target title>"` (about 2 Firecrawl credits;
     say so). If it returns job pages and their URLs share a clear pattern (e.g. `/job/<id>`), set
     `job_url_pattern`. Set `verified` to today. If it returns nothing, retry once without the title. If there's
     still nothing, tell the user: *"Search engines don't seem to list this site's jobs, so it may return nothing.
     Keep it anyway?"*. Keep it or drop it as they choose, and record the outcome in `notes`.
- The user may also say *"don't search X in <country>"*. Turn that board off (`enabled: false`) only if it isn't
  used for another target country. LinkedIn and web search always stay on.

Then ask (`AskUserQuestion`): **"Do you want to adjust advanced settings?"**
- **No, use sensible defaults** (recommended):
  - work languages = the user's languages at B2 or above;
  - EU-wide remote = yes if "remote" was chosen for anywhere in the EU;
  - country-locked remote = only in the target countries;
  - time-zone limit = ±2 h;
  - all industries, company sizes and contract types;
  - no deal-breakers;
  - all boards from the per-country step above.
- **Yes**: ask about any of these the user picks:
  - languages they'll work in;
  - remote scope (EU-wide, country-locked, time-zone limit);
  - industries to prefer or exclude;
  - company size;
  - contract types (permanent / B2B / freelance / part-time);
  - maximum years of experience required;
  - deal-breakers;
  - a company watchlist: specific employers whose careers pages to check every run → `company_watchlist[]`.

Save state → `phase: 2`.

---

## Phase 3: First-run period

Ask (`AskUserQuestion`): **"How far back should the first search look?"**
- 1 week
- **2 weeks** (recommended)
- 3 weeks
- 1 month (the maximum: LinkedIn and Indeed only filter by up to one month)

Store it as `search.first_run_lookback_days`. Explain: *"After the first run, every run covers the time since the
previous one, up to 3 weeks. If more than 3 weeks pass between runs, I'll search the last 3 weeks and tell you."*
(`search.max_lookback_days` = 21.)

Save state → `phase: 3`.

---

## Phase 4: Results and email

1. **Results table (Google Sheet).** Explain: *"I keep all jobs in a Google Sheet, with a tab per week, status
   dropdowns, links to the CVs and my notes. For that, please connect the Google Drive connector (Claude: Settings
   → Connectors → Google Drive)."* Check whether the Google Drive tools are available.
   - Connected → `tracking.storage: "google_sheets"`. The Drive permission is asked in Phase 7.
   - Not connected and the user doesn't want to connect it → `tracking.storage: "chat"`. Explain that results will
     be shown in this chat in the same table format as the sheet, and that job history is kept in a local file
     (`runs/tracker.json`) so that jobs aren't shown twice.
2. **Email.** Ask (`AskUserQuestion`): **"Do you want an email with the summary and results when each search is
   done?"**
   - **Yes** → ask for the email address(es). Sending needs the Gmail connector (Settings → Connectors → Gmail);
     check that its tools are available. Store `notifications.email.enabled: true`, `provider: "gmail_mcp"` and the
     `recipients`. Email only the addresses the user gave.
   - **No** → `notifications.email.enabled: false`. Results are presented in the chat (digest plus the full results
     table, in the template format).

Save state → `phase: 4`.

---

## Phase 5: Auto-run

Ask (`AskUserQuestion`): **"Do you want me to run the search automatically?"**
- Mon / Wed / Fri (recommended)
- Every weekday
- Once a week
- No, only when I ask

For automatic runs, ask the time of day and confirm the time zone (default: the zone of their home city). Store
`notifications.schedule` with `orchestrator: "claude_scheduled_task"`. This kind of schedule catches up missed runs
when the app reopens, and the next run then covers the gap (up to 3 weeks). **Don't create the schedule yet.** That
happens in Phase 7, after consent.

Save state → `phase: 5`.

---

## Phase 6: Integration checks

Run each check, then show a status table (`✅ ok / ⚠️ degraded / ❌ missing`) with a one-line fix for each problem.
Write the results to `integrations.*.status` and `last_checked_at`.

| Integration | Required | Check (cheap, read-only) | If missing |
|---|---|---|---|
| **Firecrawl** | Yes | `firecrawl_search` with a neutral query (`"product manager" site:eurojobs.com`, `limit: 1`). | README *Prerequisites → Firecrawl*. Searching can't run without it. Stop here and offer to resume later. |
| **Apify** | Recommended for LinkedIn | `fetch-actor-details` for `curious_coder/linkedin-jobs-scraper` (no run, no cost). | Explain: *"LinkedIn is the biggest job source. Through Apify I get structured LinkedIn jobs with date and location filters, for about $0.002 per job. Apify's free plan includes a small monthly credit. Without Apify I search LinkedIn through Firecrawl, which finds fewer jobs and less precise locations."* If they decline, set `apify.mode: "disabled"`. |
| **Google Drive / Sheets** | If `tracking.storage` is `google_sheets` | `search_files` for the folder name in `integrations.google.drive.root_folder_name`. | Offer to connect it now, or switch to `tracking.storage: "chat"`. |
| **Gmail** | If email is on | Confirm the Gmail tools are available. **Don't send anything.** | Offer to connect it now, or turn email off (results go to the chat). |

Never look for tokens in the user's files or browser. If a check fails, explain the fix and let the user choose:
fix it now, continue without it, or pause.

Save state → `phase: 6`.

---

## Phase 7: Permissions and workspace setup

Ask each of these **separately** and wait for a clear yes:

1. **Google Drive** (only if `tracking.storage` is `google_sheets`): *"May I create a folder **"Job Search Full-Ops Agent"** in
   your Google Drive, with a **"Tailored CVs"** subfolder and a tracking spreadsheet **"Job Search Full-Ops Tracker"**? I'll
   only write inside that folder."*
   - Yes → create them. Build the `Template` tab from `templates/google_sheet_structure.json`: header style,
     column order and widths, frozen rows, number and date formats, dropdowns (`Application Status` values from
     `config.tracking.statuses`) and conditional colours. If the Google MCP can't apply some formatting, create the
     columns anyway and tell the user which formatting to add by hand. Store the IDs in
     `config.integrations.google.*` and set `permissions.create_files_in_drive: true` with a timestamp. If a folder
     with that name already exists, ask whether to reuse it.
   - No → `tracking.storage: "chat"`. PDFs are saved locally only, and nothing is written to Drive until the user
     changes this.
2. **Test email** (only if email is on): *"Should I send a short test email to <recipients>?"* Send only on yes.
3. **Schedule** (only if auto-run is on): *"Should I create the scheduled run: <days> at <time> <tz>?"* Create it only
   on yes, then show its ID and how to pause it.

Save state → `phase: 7`.

---

## Phase 8: Review and save

1. Show a **compact summary** (no raw JSON unless asked):
   - Profile: name, N roles, N bullets (N with numbers), education, languages, location
   - Quality gate: passed, plus any `accepted_gaps`
   - Goal: titles, seniority, locations and formats, salary
   - First-run period, results (Google Sheet or chat), email (yes/no and address), auto-run
2. Ask: *"Anything to change before I save?"*
3. Write `user_profile.json` and `config.json`, then run `.venv/bin/python tools/validate.py` (both must be valid;
   `onboarding.completed: true`,
   `completed_at`, `last_completed_phase: 8`). Create `.env` from `.env.example` only if it doesn't exist; never
   overwrite it.
4. Confirm that `.gitignore` contains `user_profile.json`, `config.json`, `.env`, `.onboarding_state.json`,
   `.onboarding_profile_draft.json`, `output_resumes/` and `runs/`. Add any that are missing.
5. Delete `.onboarding_state.json` and `.onboarding_profile_draft.json`.

---

## Phase 9: First search

Say: *"Setup is done. I'll now search the last <first_run_lookback_days> days, score every match and write a 1-page
CV for each job at or above <min_fit_score>%."* Ask for a go-ahead, then continue with the run pipeline in
`SKILL.md`. If the user wants to wait, tell them how to start later ("run my job search") and how to edit the profile
("update my profile", "change my job goal").

---

## Re-entry rules

| Situation at start | Action |
|---|---|
| No `config.json` and no `user_profile.json` | Full onboarding from Phase 0 |
| `.onboarding_state.json` exists | *"We stopped at phase N. Continue?"* → resume at N+1 |
| Files exist but fail schema validation | List the invalid fields and fix them with the user (only the affected phase) |
| `tools/profile_check.py user_profile.json` no longer passes (e.g. after a manual edit) | Run Phase 1.2–1.4 for the gaps only |
| A required integration is `missing` | Run Phase 6 only |
| User answers "used it / learning it / neither?" questions (digest or pre-tailoring) | "used it": ask where and how (Round C of the full interview for that role) and add the evidence. "learning": add it to `skills.learning`. Then validate and save. |
| "set up Google Drive for the job agent" | Phase 6 (Google check) and Phase 7 step 1 only |
| "update my profile" | Phase 0 intake for the new info (e.g. a new role), then Phase 1 for the gaps only |
| "add a job board" / "search <site> for <country>" | The *Local job boards, per country* step for that country only, then validate and save |
| "change my job goal" / "change my settings" | Phase 2 (and the advanced settings if asked), then validate and save |
| "change email" / "change schedule" | Phase 4 step 2 / Phase 5, then Phase 7 for consent |
