# Digest email and chat report: structure

The digest is a short, factual run report written by Claude in SKILL.md Step 10. **The wording may change from run to
run. The structure and the facts may not:** each section below appears in this order whenever it has content, and
every number must match the run log (`runs/run_log_<date>.tsv`) and the tracking sheet.

Values in `{braces}` come from the run, `config.json` or `user_profile.json`.

---

## Subject

`{config.notifications.email.subject_template}`, e.g. `[Job Match Digest] 5 new roles — 2026-11-06`.

## Body sections

### 1. Greeting
`Hi {first name from profile.personal.full_name},`

### 2. Run summary (2–4 lines)
- **Run line:** the date and search window: `Run of {date} (last {window_days} days).` If the window was widened
  after a missed run, say so: `(last 6 days: previous run was missed)`.
- **Sources:** each source that returned jobs, with its count, then the boards searched via Firecrawl:
  `Sources: LinkedIn (212), Indeed (88), StepStone (41), plus Firecrawl searches of XING, jobs.ch and your watchlist.`
- **Funnel**, one line with arrows, using the same numbers as the run log:
  `Collected {n} → in scope {n} → new {n} → passed pre-filter {n} → Fit ≥ {min_fit_score}%: {n}.`
  Mention removed duplicates in brackets after the step where they were removed.
- **CVs:** `Tailored CVs: {n} (one per vacancy).`
- **Sheet:** the tab that was written and the status changes synced from it:
  `Google Sheet: new tab {tab name}; {n} status changes synced.` (Or `updated tab …` if it existed.)
- **CV note (optional, one line):** only for something that applied to every CV in this run, e.g. a profile update
  or a rule change: `Every CV now includes your new certification (PSPO II).`

### 3. Matches table
One row per new job with Fit ≥ `{config.notifications.email.min_fit_to_include}`, highest Fit first:

| Fit | Role | Company | Mode | Note | CV |
|---|---|---|---|---|---|

- **Role** links to the apply URL. **CV** links to that job's own tailored PDF (Drive or local path). Every job in
  the table has its own CV.
- **Mode:** the work mode and place, as in the sheet: `Remote (EU)`, `Hybrid, Berlin`, `Onsite, Vienna`.
- **Note:** at most about 20 words. Say why it fits, in the job's own terms. Add flags with `⚠`: junior or too-senior
  level, salary below your floor or missing, required language, residency limit, contract type. Name the single
  biggest missing requirement as `gap: …`.
- More than 15 matches: show the top 15 and add `+ {n} more in the sheet`.

### 4. Near misses
Jobs scoring within `{config.notifications.email.near_miss_margin}` points below the threshold, one line in total
or one line each, with the score and the main gaps:
`Near misses: {Role} at {Company} ({Mode}) {fit}%: {main gaps}. {Role} at {Company} {fit}%.`
Leave the section out if there are none.

### 5. Keywords and quick questions
- Keyword coverage for the run: `Keyword coverage: must-have 41/43, nice-to-have 18/27, learning line used in 3 CVs.`
- **Quick questions:** the 3–5 most frequent keywords the profile doesn't support, as questions the user can answer
  in one word:
  `Quick questions: Looker: used it at work / learning it / neither? · SAFe: used it at work / learning it / neither?`

### 6. Watchlist (only if `search.company_watchlist` is set)
Which watchlist companies had new matching roles, by priority, and say plainly when priority-A companies had none:
`Watchlist: Example GmbH (A) has a new Product Owner role (79%, above). No new matching roles at your other A-list companies.`

### 7. Issues (only if any)
Sources that returned 0 jobs, failed scrapes, Firecrawl or Apify credit problems, CVs that couldn't be fitted to one
page, or anything else the user should know. One line each.

### 8. Signature
`— Job Search Full-Ops Agent`

---

## Rules
- Plain, concise, no marketing language. The email should be readable in under a minute.
- Facts only. No invented reasons for a match; notes come from the scoring notes in `runs/analysis_<date>.json`.
- Don't repeat a job in both the matches table and the near misses.
- No new matches and `send_when_no_matches: true` → send sections 1, 2, 4, 5, 7 and 8 only, with the line
  `No new roles above {min_fit_score}% this run.`
- Link the Google Sheet tab when `link_tracking_sheet` is true. Never attach CVs as DOCX; link the PDFs.
- Send only to `{config.notifications.email.recipients}`. Never include API keys, file contents of the profile, or
  anything from `.env`.

---

## Chat report (when email is off)

When `notifications.email.enabled` is false, present the same digest in the chat: sections 2–7, in the same order,
without the greeting and signature. In the chat, the Role and CV links are clickable.

When `tracking.storage` is `chat` (no Google Sheet), also show the **full results table** after the digest, with the
columns of `templates/google_sheet_structure.json` in the same order. One row per new job, highest Fit first:

| Job Title | Company | Location / Work Type | Fit Score (%) | Posted Date | Source | Apply Link | CV Action | Tailored CV Link | Application Status | AI Fit & Tailoring Notes | ATS Keywords Matched | ATS Keywords Missing | Job ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

- Follow each column's `format_hint` from the sheet structure. Links show as `Open` / `PDF`; the CV link is the local
  PDF path.
- `Application Status` is `New` for new jobs. Tell the user they can update statuses by writing them in the chat
  (*"I applied to Northwind"*). Statuses are saved in `runs/tracker.json`.
- More than 15 jobs: show the top 15 and offer the rest on request.

---

## Example (fictional candidate and companies)

> Subject: [Job Match Digest] 4 new roles — 2026-11-06
>
> Hi Alex,
>
> Run of 2026-11-06 (last 3 days). Sources: LinkedIn (212), Indeed (88), StepStone (41), Welcome to the Jungle (19),
> plus Firecrawl searches of XING, jobs.ch and your watchlist.
> Collected 360 → in scope 102 → new 97 → passed pre-filter 38 (3 duplicates removed) → Fit ≥ 75%: 4.
> Tailored CVs: 4 (one per vacancy).
> Google Sheet: new tab Week_45_2026; 12 status changes synced.
>
> | Fit | Role | Company | Mode | Note | CV |
> |---|---|---|---|---|---|
> | 84% | Senior Product Manager, Billing | Northwind Payments | Hybrid, Berlin | Usage-based pricing migration, Stripe; gap: B2C | PDF |
> | 81% | Product Manager, Growth | Contoso Analytics | Remote (EU) | Funnel analysis and A/B testing at scale; ⚠ German C1 required | PDF |
> | 78% | Product Owner | Fabrikam Logistics | Hybrid, Amsterdam | Logistics domain and ML product; gap: SAFe | PDF |
> | 76% | Product Manager, Platform | Tailspin Software | Remote (DE) | API platform roadmap; ⚠ salary not stated | PDF |
>
> Near misses: Lead Product Manager at Litware (Onsite, Munich) 72%: 8+ years required, people management.
> Product Analyst at Adatum 69%.
>
> Keyword coverage: must-have 27/28, nice-to-have 11/16, learning line used in 2 CVs.
> Quick questions: Looker: used it at work / learning it / neither? · SAFe: used it at work / learning it / neither?
>
> Watchlist: Northwind Payments (A) has a new role (84%, above). No new matching roles at your other A-list companies.
>
> Issues: Jobs.cz returned 0 jobs this run.
>
> — Job Search Full-Ops Agent
