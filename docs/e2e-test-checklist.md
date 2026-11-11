# End-to-end test checklist: Job Search Full-Ops Agent

Thank you for testing! This checklist walks through the whole user flow, from the first setup to the second search
run. For each item, tick it if it works as described, or note what happened instead. A feedback template is at the
end.

- **Time needed:** about 1.5–2 hours (setup 20–40 min, first run 20–40 min, the rest spread over two days).
- **Cost:** a run uses roughly 100–300 Firecrawl credits, depending on titles, countries and boards. Apify costs
  about $0.002 per LinkedIn job (a few cents per run on the free plan).
- **Your data:** you can use your real CV or a made-up one. Everything stays in local files. Don't paste personal
  data into your feedback; describe the problem instead.

---

## 0. Before you start

- [ ] Claude Code is installed (desktop app → Code tab, or the terminal version), on a paid Claude plan.
- [ ] Python 3.9+ (`python3 --version`) and Node.js (`node --version`) are installed.
- [ ] Unpack `job-search-full-ops-agent.zip` into your home folder, as a **fresh** folder. If you tested before,
      delete the old folder first, or setup will be skipped.
- [ ] The hidden skill folder exists: `ls ~/job-search-full-ops-agent/.claude/skills/job-search-full-ops-agent`
      shows `SKILL.md` and `onboarding.md`.
- [ ] Install the requirements:
      `cd ~/job-search-full-ops-agent && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- [ ] Firecrawl connected: `claude mcp add firecrawl -e FIRECRAWL_API_KEY=fc-… -- npx -y firecrawl-mcp`
- [ ] Optional, but please test it if you can: Apify connected
      (`claude mcp add apify -e APIFY_TOKEN=… -- npx -y @apify/actors-mcp-server`).
- [ ] Optional: Google Drive and Gmail connectors turned on (Claude: Settings → Connectors).
- [ ] `claude mcp list` shows the connectors you added.

---

## 1. Start and warning

Open the folder in Claude Code and type `/job-search-full-ops-agent` (or say "set up my job agent").

- [ ] The **very first reply** warns that setup takes **about 20–40 minutes**, says why (quality of the CVs), and
      says you can stop and continue later.
- [ ] It tells you what you'll get: a separate 1-page CV **for every matching vacancy**, with the job's keywords,
      only true facts.
- [ ] It asks whether to **start now or later**.
- [ ] *Edge case:* answer **"Not now"**. It stops politely and creates no files (`ls` shows no `config.json`,
      `user_profile.json` or `.onboarding_state.json`). Then start again.
- [ ] It mentions that your profile stays in local files that aren't published.

## 2. Your experience: CV intake and quality check

- [ ] It asks how you want to share your experience: **upload/paste CV**, **describe in your own words**,
      **LinkedIn export**, or **full interview**.
- [ ] After you share it, it shows a **checklist (✅ / ❌)** per role and overall.
- [ ] The checklist covers, **per role**: title, company, dates; at least **3 achievement bullets**; at least **one
      result with a real number**; **company type** (agency / corporate / startup…), **industry**, **remote /
      hybrid / onsite**; tools.
- [ ] For the **latest role**, it checks that what you did and achieved is clear (at least 3 responsibilities).
- [ ] **Overall**, it checks:
      - an **"About me" of 5–6 sentences**;
      - **education** with university, degree, faculty/field and years;
      - courses and certifications;
      - languages with levels (A1–C2 / native);
      - city and country;
      - at least 5 core skills.
- [ ] It asks **only about the ❌ items**. It doesn't re-ask what your CV already says.
- [ ] It asks at most 3–4 questions per message, and at most 2 follow-ups per gap.
- [ ] *Edge case:* give a bullet like "Shipped the Q3 2023 release" or "Led a team of 5". It should **not** count
      as a result with a number, and it should ask for a real result (%, time, money, before → after).
- [ ] *Edge case:* answer **"skip"** to one gap. It accepts it and moves on (it's listed in the summary later).
- [ ] It **stops asking** once everything passes. It doesn't keep interviewing for no reason.
- [ ] It rewrites your achievements as **XYZ bullets** ("did X, measured by Y, by doing Z"), shows them, and asks
      you to confirm or edit them. Nothing is exaggerated.
- [ ] It asks three quick extras:
      - anything it must **never claim**;
      - skills you're **learning** but haven't used at work;
      - words to **keep off** your CV.

## 3. Job search goal

- [ ] It asks the **five core questions**: titles (and suggests 2–4 related titles), seniority, location
      (countries and cities), format (remote / hybrid / onsite per location), salary (skippable).
- [ ] It offers **"advanced settings?"** as optional. **No** gives sensible defaults (no long list of extra
      questions).
- [ ] *Optional:* say **Yes** and check that the advanced options appear: languages, remote scope, industries,
      company size, contract types, maximum years required, deal-breakers, company watchlist.

## 4. Local job boards, per country

- [ ] For **each target country**, it shows the boards it will search, in three groups:
      - **always:** LinkedIn and web search;
      - **local boards** for that country (e.g. Portugal: Indeed, Landing.Jobs, Net-Empregos);
      - **Europe-wide** boards.
- [ ] It asks whether you know **other local job sites** for that country.
- [ ] *Test A:* say **"no"** for one country. It keeps the default list.
- [ ] *Test B:* for another country, give **one site already on the list plus 2–3 new ones**. It says the known one
      is already included, adds the new ones **on top of** the defaults, and tests each new site once, mentioning
      the small credit cost.
- [ ] If a site you add has no searchable jobs, it tells you and asks whether to keep it.
- [ ] It does **not** let you remove LinkedIn or web search.

## 5. First-run period

- [ ] It asks how far back the **first** search should look: 1 week / **2 weeks** (recommended) / 3 weeks /
      1 month.
- [ ] It explains that later runs cover the time since the previous run, **up to 3 weeks**.

## 6. Results and email

- [ ] It explains the **Google Sheet** (a tab per week, status dropdowns, CV links) and asks you to connect
      **Google Drive** if it isn't connected.
- [ ] *If you don't connect Google Drive:* it says results will be shown **in the chat in the same table format**.
- [ ] It asks: **"Do you want an email with the summary and results when each search is done?"**
- [ ] If **yes**, it asks for your email address(es) and checks that Gmail is connected.
- [ ] If **no**, it says results will be shown in the chat.

## 7. Auto-run

- [ ] It asks whether to **run automatically**: Mon/Wed/Fri, every weekday, weekly, or only when you ask.
- [ ] If automatic, it asks for the **time** and confirms your **time zone**.
- [ ] It does **not** create the schedule yet. That comes after your consent in step 9.

## 8. Connector checks

- [ ] It shows a status table (✅ / ⚠️ / ❌) for Firecrawl, Apify, Google Drive and Gmail.
- [ ] It doesn't spend money or send anything during these checks.
- [ ] If Apify isn't connected, it explains why Apify is recommended for LinkedIn (more jobs, better filters, about
      $0.002 per job) and that Firecrawl is used instead.
- [ ] If something required is missing, it explains how to fix it and lets you choose: fix now, continue without
      it, or pause.

## 9. Permissions (each asked separately)

- [ ] **Google Drive:** it asks before creating the folder "Job Search Full-Ops Agent", the subfolder "Tailored CVs"
      and the sheet "Job Search Full-Ops Tracker". Nothing is created before you say yes.
- [ ] In Drive, the sheet has a `Template` tab with the right columns, a frozen blue header, a status dropdown and
      colours. (If some formatting is missing, the agent should have told you what to add by hand.)
- [ ] **Test email:** it asks before sending one. Check that it arrives.
- [ ] **Schedule:** it asks before creating it, then shows how to pause it.

## 10. Review and save

- [ ] It shows a short summary:
      - your profile: roles, bullets with numbers, education, languages;
      - quality-check result and any skipped items;
      - goal, first-run period, results (Sheet or chat), email, auto-run.
- [ ] It asks whether to change anything before saving.
- [ ] Afterwards, `config.json` and `user_profile.json` exist in the folder, and `.onboarding_state.json` is gone.
- [ ] **Resume test** (optional, separate try): stop in the middle of setup, close Claude, reopen and start again.
      It offers to continue from where you stopped.

## 11. First search run

It should start right after setup (after you confirm).

- [ ] It searches the period you chose (e.g. the last 2 weeks).
- [ ] **LinkedIn** is searched through **Apify** if it's connected (or Firecrawl if not), and the digest says which.
- [ ] The **local boards** you added in step 4 are searched for their countries.
- [ ] Web search results include jobs from **employer career pages**, not just job boards.
- [ ] The **same job posted twice** (on two boards, or by the employer and a recruiting agency) appears **only
      once**.
- [ ] Jobs outside your locations, work format, languages or salary rules are filtered out.
- [ ] *If you started the run yourself:* before writing the CVs, it may ask one short batch of questions like
      *"Looker: used it at work / learning it / neither?"*.

## 12. Tailored CVs (most important)

Open 2–3 of the generated PDFs (`output_resumes/` or the Drive folder "Tailored CVs").

- [ ] **One CV per matching job.** The digest says `Tailored CVs: N (one per vacancy)` and there are N PDFs.
- [ ] Each CV differs: the summary, skills order and bullet wording match **that** job post.
- [ ] The job post's **keywords** appear inside the summary, skills and bullets, not as a separate list, and not
      stuffed (each at most about 3 times).
- [ ] Every fact is **true**: no invented numbers, employers, titles, certifications or tools.
- [ ] Nothing from your **never-claim** list appears, in any wording.
- [ ] "N years of experience" matches your real dates, or says "N+ years".
- [ ] Skills you said you're **learning** appear only on a separate "Learning:" line, if at all.
- [ ] Each CV is **exactly one page**, readable, with no 1–2-word lines dangling at the end of a bullet.
- [ ] A short career gives a shorter CV with a slightly bigger font, not one stuffed with filler.
- [ ] **PDF only**: no Word or Google Doc versions are created.
- [ ] File names have no spaces (e.g. `CV_Your_Name_Company_2026-11-10.pdf`).

## 13. Results: Google Sheet or chat

- [ ] **Sheet:** a new tab (e.g. `Week_46_2026`), copied from `Template` with its formatting, one row per job,
      highest Fit first.
- [ ] Columns are filled: title, company, location/mode, fit %, date, source, apply link, CV link, status `New`,
      notes, keywords matched and missing, Job ID.
- [ ] **No sheet:** the chat shows the same columns as a table.

## 14. Digest email (or chat report)

- [ ] The email arrives at the address you gave (or the same report appears in the chat).
- [ ] Contents, in this order:
      - greeting;
      - run summary: date, period, sources with counts, a funnel like "Collected → in scope → new → passed
        pre-filter → Fit ≥ 75%", the number of tailored CVs;
      - **matches table**: Fit, Role (link), Company, Mode, Note with ⚠ flags and "gap:", CV link;
      - **near misses**: jobs just below the threshold;
      - keyword coverage and **quick questions** ("used it / learning it / neither?");
      - watchlist (if set);
      - **issues** (e.g. a board with 0 jobs, Apify → Firecrawl switch);
      - signature "— Job Search Full-Ops Agent".
- [ ] Numbers in the email match the sheet.

## 15. Second run (next day, or a few days later)

- [ ] Start it yourself ("run my job search") or let the schedule run it.
- [ ] It searches only the **time since the last run** (at most 3 weeks).
- [ ] Jobs from the first run **don't appear again**.
- [ ] Change a status in the sheet (e.g. "Applied") before the run. It's **not** reset afterwards. In chat mode,
      tell it "I applied to <company>" and check it's remembered.
- [ ] *Optional:* the schedule runs on its own at the set time. If your laptop was closed, it runs when Claude
      opens again.
- [ ] *Optional, Apify fallback:* if Apify fails or runs out of credit, the run continues with Firecrawl and the
      digest mentions it.

## 16. Updating things later

- [ ] "update my profile" (e.g. add a new role): it asks only about the new role's gaps.
- [ ] Answer a quick question, e.g. "Looker: learning it". It updates your profile, and a later CV shows it on the
      Learning line.
- [ ] "change my job goal": it asks the goal questions again.
- [ ] "search <site> for <country>": it adds and tests that board.
- [ ] "change email" / "change schedule": it asks for consent again before applying.

## 17. Privacy and safety

- [ ] The agent never asked for passwords, and never logged in to job boards.
- [ ] Nothing was created in Drive, emailed or scheduled without your clear yes.
- [ ] Emails went only to the address you gave.
- [ ] Your personal files (`config.json`, `user_profile.json`, `.env`, `output_resumes/`, `runs/`) are listed in
      `.gitignore`.

---

## Feedback template

Copy this, fill it in, and send it back. **Please don't include personal data** (your CV text, email or phone).

```
Tester: <name or nickname>   Date: <date>   Setup: desktop app / terminal; Apify yes/no; Google Drive yes/no; email yes/no
Countries tested: <e.g. PT, DE>   Titles: <e.g. Product Manager>

Summary: <1-3 sentences: overall impression>

Failed or odd items:
- Section/item: <e.g. 4 / Test B>
  Expected: <what the checklist says>
  Actual: <what happened>
  Severity: blocker / major / minor
  Screenshot or copied message: <optional, with personal data removed>

Time taken: setup <min>, first run <min>
Credits used (if you can see them): Firecrawl <n>, Apify <$>
Ideas / wishes: <anything>
```
