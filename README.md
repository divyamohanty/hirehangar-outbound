# Hire Hangar outbound: 250K applications → client meetings

A working v0 of the outbound system from my take-home deck. It turns job applications into a
ranked list of US companies that will need remote hires soon. It writes the emails, checks them
for privacy leaks, and hands everything to Instantly, HeyReach and HubSpot.

**North star:** new-client scoping calls held, tracked by signal.

```bash
git clone <this repo> && cd hirehangar-outbound
python3 -m hh demo        # full pipeline, offline, no keys, $0 (Python 3.9+, standard library only)
python3 -m unittest -v    # 11 tests, including the privacy rules
```

> **About the data.** Every applicant and every `.example` company in the demo is **synthetic**. No real
> resumes were used. The job posts are **real**: 216 public roles from my Nov 6 2026 scan of free ATS
> boards (`data/job-post-scan-2026-11-06.csv`). `python3 -m hh jobs --live` pulls today's posts from the same boards.

---

## The idea in one line

**Private data picks the account. Public data writes the email.**

Everyone can see job posts. Only Hire Hangar sees the applications. Every resume says where someone works
today, how they were hired, and that they're about to leave. A month of them together shows which US
companies will need people, often weeks before a job goes up.

## How it works

```
 PRIVATE BOX (raw resumes never leave)                    PUBLIC SIGNALS (the only things an email may cite)
 ┌──────────┐  ┌──────────────┐  ┌───────────┐            ┌───────────┐ ┌──────────┐ ┌────────────┐
 │ 1 ingest │→ │ 2 parse      │→ │ 3 company │            │ job posts │ │ funding  │ │ new leaders│
 │ ATS pull │  │ Docling+LLM  │  │  signals  │            │ free ATS  │ │ treg/    │ │ treg/Exa/  │
 │ dedupe   │  │ fixed JSON   │  │ (k ≥ 3)   │            │ APIs      │ │ Parallel │ │ Parallel   │
 └──────────┘  └──────────────┘  └─────┬─────┘            └─────┬─────┘ └────┬─────┘ └─────┬──────┘
                                       └──────────────┬─────────┴────────────┴─────────────┘
                                                      ▼
                                   4 SCORE = fit × timing × can-we-fill-it   (SQLite → Postgres)
                                                      ▼
                         5 ENRICH (treg: right person + verified email, spend-capped)
                                                      ▼
                         6 DRAFT 5-touch sequence  →  PRIVACY LINT (blocks any leak)
                                                      ▼
                         7 EXPORT → Instantly · HeyReach · HubSpot (intake brief pre-filled)
                                                      ▼
                         8 LEARN: what books meetings reweights the score  ◄── outcomes.csv
```

| Step | Command | Module | What it does |
|---|---|---|---|
| 1-2 | `hh parse --dir PATH` | `hh/parse.py` | Resume → one fixed JSON per application. Name and email become a salted hash, used only to drop repeat applicants. |
| public | `hh jobs --live` | `hh/jobs.py` | Greenhouse, Lever, Ashby, Workable and SmartRecruiters public APIs. Stores **our own first-seen date**, because posting dates lie. |
| 3 | `hh signals` | `hh/signals.py` | Company-level signals only (below). |
| 4 | `hh score` | `hh/score.py` | Fit × timing × fill. Picks the play, the buyer persona and the send date. |
| 5 | `hh enrich --live` | `hh/enrich.py` | treg people search, then email find, then verify. Cheapest provider first, hard spend cap. |
| 6 | `hh draft` | `hh/draft.py` | Day 0/2/3/7/12 sequence. Lint: under 90 words, no links in email 1, no private data. |
| 7 | `hh export` | `hh/export.py` | `out/*.csv` ready to import. |
| 8 | `hh learn out/outcomes.csv` | `hh/export.py` | Signals that book meetings get more weight. |

## The five signals you can't buy anywhere (slide 5)

| # | Signal | Rule in code | Play |
|---|---|---|---|
| 1 | Someone outside the US works remotely for a US company **today** | `offshore_now` | Best fit: they already pay for remote talent. A backfill could be weeks away. |
| 2 | "Contractor via Deel" / agency on the resume | `vendor` | Tells us who they buy from today. Adds to timing. |
| 3 | 3+ people from one team in 30 days, adjusted for size | `team_exits` (never fires below 3) | Backfill coming. Expected date comes from notice periods. |
| 4 | Sudden spike from one company in one week | `spike` | Usually layoffs. Wait about 45 days, then pitch flexible monthly cost. |
| 5 | Bench depth and pay by role | `bench` table → `fill` | Only pitch roles we can fill in 48 hours. |

Public signals: `fresh_post` (≤2 days, the 48h window), `recent_post` (≤14d), `still_open` (≥21d by our
first-seen date, the "you might be hiring the wrong role" email), `offshore_post` (a US company posting an
offshore role, i.e. signal 1 in public; e.g. TechnologyAdvice's "Philippines, Remote" SDR role), `team_buildout`.

## Who to target (slide 3)

`hh/score.py: fit_score()` and `persona()`:
- **Company:** US, 10-200 people. Above 500 is skipped (likely has an RPO). Staffing firms and talent marketplaces are skipped as competitors.
- **Best fit:** already works with remote or offshore people (+0.2 fit). On-site-only companies are discounted.
- **Who gets the email:** under 25 people → founder. 25-100 → the leader of the hiring team (VP Sales / COO / Head of Marketing / CTO). 100+ → Head of Talent plus the hiring manager.

## The one rule I wouldn't bend: nothing in an email can be traced to a candidate

Enforced in code, not just in policy:
- Applications never store names or emails (`parse.py`). Raw resumes stay in `data/private/` (git-ignored).
- Team signals need **3+ applicants** (`TEAM_SIGNAL_MIN_APPLICANTS`). Below that, the signal doesn't exist.
- A company with only private signals is **held**, never emailed, until a public fact exists (`hold_no_public_fact`).
- Every draft goes through `draft.lint()`. It blocks words like applicant/resume/leaving/resign and any private signal text. `tests/` checks every draft.

## The stack: what each tool does and why it's there

Everything is **BYOK** (bring your own keys). Nothing is billed to anyone else, and every paid tool is optional.

| Job | Tool | Why this one | Cost | In this repo |
|---|---|---|---|---|
| Read resumes | **Docling** (open source) + a **small LLM** with a fixed JSON format | Docling handles PDF/DOCX layout for free. A small model is enough for field extraction at 250K/month. Pay **Reducto/Extend** only for the messy 5-10% (scans, odd layouts). | $0 Docling. LLM cents per 1K resumes. **$0 with local Ollama.** | `parse.py`: `HH_LLM_PROVIDER=rules \| anthropic \| openai` (any OpenAI-compatible server) |
| Storage + logic | **Postgres** + small Python jobs, built with Claude Code | Candidate data stays in house. Plain SQL a single operator can query. | $0 (SQLite locally, same schema for Postgres) | `db.py` |
| Job posts | **Free ATS APIs** (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) + JobSpy/Firecrawl for the long tail | Official, structured and free. Daily coverage for about $0. | $0 | `jobs.py` (live, tested on 25 boards / 345 jobs) |
| People + emails | **treg**: one login, 30+ data providers, cheapest first, spend caps | Replaces separate Apollo/Hunter/ZeroBounce seats. Free providers answer first. Misses are free on per-success providers. | people search often $0, email find ≈$0.005, verify ≈$0.0004 | `enrich.py` (`treg login`, `HH_TREG_MAX_SPEND_USD`) |
| Triggers | **Parallel Monitor** (funding, new leaders), **treg web search** | You describe the trigger in plain English. Feeds `public_facts`, the only thing an email can cite. | pay per use | `public_facts` table (demo rows); add your key |
| Lookalikes | **Exa Websets** | "Companies like our best 20 clients" without building filters by hand. | pay per use | roadmap |
| Sending | **Instantly** on separate domains, 15-20 warmed inboxes | Volume without risking hirehangar.com deliverability. | ~$100-400/mo | `out/instantly_leads.csv` |
| LinkedIn | **HeyReach** | Day-2 connect step, multi-account. | ~$80/mo | `out/heyreach_linkedin.csv` |
| CRM | **HubSpot free** | Every yes lands with the scoping-call intake brief already filled in. | $0 | `out/hubspot_companies.csv` |
| Testing a new play | **Clay** | Still great for trying a play on a few hundred accounts. treg + Postgres carry the volume. | | n/a |

### Where treg fits (and where it doesn't)

| Use treg for | Don't use treg for |
|---|---|
| Finding the buyer at a company (`treg.people.search`, by domain + title) | Anything with applicant data. Applicant data never leaves the private box. |
| Work email find + verify (`treg.people.email.find`, `.verify`) | Job posts. The ATS APIs are free and official. |
| Trigger discovery (`treg.web.search` for funding and leadership news) | Exact checks of a known page (plain HTTP is free) |
| Company firmographics (headcount, HQ) to replace the size proxy | |

Spend control: every call sets `X-Treg-Route-Max-Cost`, and every run stops at `HH_TREG_MAX_SPEND_USD`.

## Monthly cost at full volume (slide 11)

About **$1K-1.5K/month** all in: inboxes and domains, Instantly, HeyReach, treg enrichment for about 2.6K
contacts, and LLM parsing. That's roughly what one placement brings in each month.

Funnel (assumptions, not promises): 250K applications → ~100K with a resolvable employer → ~6K companies that fit → ~1.5K
with a live trigger → ~2.6K people contacted → 60-90 good replies (3%) → **40-60 meetings/month** (60% book).
The real ceiling is who takes 2-3 scoping calls a day.

## Run it for real

```bash
cp .env.example .env                       # fill only what you use
python3 -m hh jobs --live                  # today's posts from data/seed_boards.csv (126 boards)
python3 -m hh parse --dir /path/to/ats-export   # .txt works out of the box; pip install docling for PDF/DOCX
python3 -m hh signals && python3 -m hh score
treg login && python3 -m hh enrich --live --limit 25
python3 -m hh draft && python3 -m hh export && python3 -m hh report
# after the pilot: fill meeting_booked in out/outcomes_template.csv
python3 -m hh learn out/outcomes_template.csv && python3 -m hh score
```

## First 30 days

- **Week 1:** parse a week of applications and hand-check 300. Test the ICP against real clients (who bought, which roles, who stayed past month 3). Warm up domains.
- **Week 2:** pick 300 accounts split by signal, plus a **no-signal control group**.
- **Weeks 3-4:** send. Founders take the top 30 personally. Scale whatever books. `hh learn` reweights the score.

## Known limits of this v0 (honest list)

- Company size in the public scan is a proxy (`open_jobs_on_board × 6`) until treg firmographics replace it. A few known misses are fixed by hand in `data/firmographics_overrides.csv`.
- Role buckets use keyword rules. In production a small LLM classifies from the job description.
- `still_open` needs at least 3 weeks of daily pulls to build our own first-seen history.
- Exa Websets and Parallel Monitor are listed above, not yet wired in. They write into `public_facts`.

---
Built by Divyashree Mohanty for Hire Hangar, November 2026.
