# Job board live test: 2026-11-07 (Landing.Jobs re-tested 2026-11-08)

Each board was searched once through the Firecrawl MCP (`firecrawl_search`, `limit: 3`, `tbs: qdr:m` = last month)
with a project-management title and a city in one of its countries. Five boards had one job page scraped in full
to check that the description comes through. Indeed's structured provider was called once.
Cost: about 76 Firecrawl credits.

**Result types**
- **jobs**: hits are individual job ads.
- **mixed**: some hits are job ads and some are search-results pages. The agent sorts them with
  `job_url_pattern` and scrapes up to 2 search-results pages per board for job links.
- **listing pages**: only search-results pages came back, so job links must be collected from them.

The URLs each `job_url_pattern` was checked against are in `tests/test_config.py`.

## Aggregators and public employment services

| Board | Test query | Result | Notes / change made |
|---|---|---|---|
| LinkedIn | "Project Manager" Berlin | jobs | A bare "Berlin" returned Berlin NJ / New Berlin WI. **Fix:** `{location}` is now "City, Country". |
| Indeed (provider) | DE, "Project Manager", Berlin, 3 days | jobs | 5 dated Berlin jobs with language, hybrid tag and employer apply link. **Change:** uses the Firecrawl `indeed-com` provider (5 credits/call) for AT BE CH DE ES FR GB IE IT NL SE. |
| Indeed (site search) | de.indeed.com "Projektmanager" Berlin | listing pages | Search-results and salary pages, no single ads. Used only for countries the provider doesn't cover. |
| Glassdoor | glassdoor.de "Project Manager" Berlin | mixed | Job page scraped in full on a basic proxy. **Change:** enabled. The Firecrawl Glassdoor provider is US-only, so it isn't used. |
| EURES | search URL template; site search | **broken** | The search URL returns 404 to scrapers; vacancies are rendered by JavaScript and aren't indexed. **Change:** disabled. |
| Eurojobs | "Project Manager" Germany | jobs | One UK result for a Germany query; the location pre-filter handles it. |
| Platsbanken (SE) | "Projektledare" Stockholm | jobs | Full Swedish text scraped. The location is loose (returned an Östhammar job). |
| Web search (always on) | "Project Manager" "Lisbon, Portugal" job, last week | mixed | Tested 2026-11-08. Found jobs on employer career pages that no board covers (Takeda, Nestlé, a consulting firm's careers page), plus noise (a salary site, a Facebook group, listing pages). **Setup:** noise sites and boards already searched go into `excludeDomains`; hits are classified by page content because there's no URL pattern for "any site". |

## Tech & startup

| Board | Test query | Result | Notes / change made |
|---|---|---|---|
| Wellfound | "Product Manager" (remote OR Berlin) | jobs | Mostly US roles; filtered later by geography. |
| Welcome to the Jungle | "Product Manager" Paris | jobs | Clean Paris results. |
| No Fluff Jobs | "Project Manager" Warszawa | jobs | Clean. |
| Landing.Jobs | "Project Manager" | **0 results with time filter** → jobs (low precision) | Re-tested 2026-11-08 after a trial run: `qdr:m` returns nothing, no filter returns jobs. **Change:** `search_time_filter: null`. Hits are often unrelated roles (SAP, cloud); scoring filters them out. |
| Jobriver (DE) | "Projektmanager" Berlin, last month | **0 results** → jobs | Works only without a time filter and without a city. **Change:** `search_time_filter: null`, title-only query, domain `jobriver.de/en/jobs`. |
| The Hub (Nordics) | "Product Manager" | jobs | Replaces Breakit.se, a news site without a job board. |
| Tecnoempleo (ES) | "Project Manager" Madrid | jobs | Clean. |

## Remote-first

| Board | Result | Notes / change made |
|---|---|---|
| RemoteOK | jobs (low precision) | The title often matched only the sidebar. |
| We Work Remotely | jobs | Clean. |
| EU Remote Jobs | jobs | Clean, European time zones. |
| Working Nomads | jobs | Many US-only roles; the residency and geography pre-filters handle them. |
| Remote.co | jobs | **Change:** domain tightened to `remote.co/job-details`. |

## National boards

| Board | Test query | Result | Notes / change made |
|---|---|---|---|
| StepStone (DE) | "Projektmanager" Berlin | mixed | |
| XING | "Projektmanager" Berlin | mixed | Job page scraped in full **without login**. **Change:** `requires_login_for_full_text: false`. |
| karriere.at | "Projektmanager" Wien | listing pages | Collect job links from search-results pages. |
| jobs.ch | "Projektleiter" Zürich | jobs | Full text scraped. |
| Reed | "Project Manager" London | mixed | |
| CV-Library | "Project Manager" London | jobs | |
| Jobs.ie | "Project Manager" Dublin | jobs | |
| Nationale Vacaturebank | "Projectmanager" Amsterdam | jobs | |
| Jobindex (DK) | "Projektleder" København | mixed | |
| InfoJobs (ES) | "Project Manager" Madrid | mixed | |
| Net-Empregos (PT) | "Gestor de Projeto" Lisboa | mixed | |
| Jobs.cz | "Projektový manažer" Praha | **0 results** → listing pages | The `/rpd` path filter + time filter returned nothing. **Change:** domain `jobs.cz`, no time filter; collect `/rpd/<id>` links from search-results pages. |
| Profesia (SK) | "Projektový manažér" Bratislava | listing pages | Collect `/O<id>` links from search-results pages. |
| eJobs (RO) | "Project Manager" Bucuresti | jobs | Clean. |

## Not tested / known gaps
- Only one query per board, so these results show that a board is reachable, not how many jobs it returns.
- `job_url_pattern` for karriere.at, Jobs.cz and Profesia is based on their public URL format; no single job page
  from those boards came back in this test.
- Re-run this test before each release. Boards change their URL formats without notice.
