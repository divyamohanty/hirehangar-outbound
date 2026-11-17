# Hire Hangar Outbound

**Turning 250K job applications a month into new-client meetings.**

A working v0 of the outbound system from my take-home ([deck](docs/deck.pdf)). It finds US companies that
will need remote hires soon, ranks them, writes the emails, checks every email for privacy leaks, and
produces files ready to import into Instantly, HeyReach and HubSpot.

> **Private data picks the account. Public data writes the email.**

| | |
|---|---|
| **North star** | New-client scoping calls held, tracked by signal |
| **Runs on** | Python 3.9+, standard library only. No installs, no keys |
| **Cost to run the demo** | **$0** |
| **Tests** | 11, including the privacy rules |

---

## Contents

1. [Try it in 60 seconds](#1-try-it-in-60-seconds)
2. [What you get (real output)](#2-what-you-get-real-output)
3. [How it works](#3-how-it-works)
4. [The signals](#4-the-signals)
5. [Who we target](#5-who-we-target)
6. [The privacy rule, enforced in code](#6-the-privacy-rule-enforced-in-code)
7. [The stack: every tool and why it's there](#7-the-stack-every-tool-and-why-its-there)
8. [What it costs](#8-what-it-costs)
9. [Running it for real (BYOK)](#9-running-it-for-real-byok)
10. [Repo map](#10-repo-map)
11. [Known limits and next steps](#11-known-limits-and-next-steps)

---

## 1. Try it in 60 seconds

```bash
git clone https://github.com/divyamohanty/hirehangar-outbound.git
cd hirehangar-outbound

python3 -m hh demo          # the whole pipeline on sample data, offline, about 1 second
python3 -m hh jobs --live   # pull today's real job posts from 126 company job boards, about 45 seconds
python3 -m unittest -v      # run the tests
```

**About the data:**
- **Applicants are synthetic.** Every applicant and every `.example` company was made up for the demo. No real resumes were used.
- **Job posts are real.** They come from the free public APIs of Greenhouse, Lever, Ashby, Workable and SmartRecruiters.

---

## 2. What you get (real output)

### Live run, Nov 17 2026: public job posts only, $0

`python3 -m hh jobs --live` read **1,552 open jobs** from **125 company job boards** in 44 seconds.
**966** were relevant US or offshore roles in Hire Hangar's four buckets.

**Top 10 accounts.** All come from real job posts.

| # | Company | Score | Why it ranks | Email goes to |
|---|---|---|---|---|
| 1 | Jump | 0.706 | Hiring in Poland + 4 remote sales roles (SDR, AEs, AM) | VP Sales |
| 2 | Mitratech | 0.706 | Hiring engineers in India | CTO / VP Eng |
| 3 | Oscilar | 0.706 | Hiring backend engineers in Brazil, Poland, India | CTO / VP Eng |
| 4 | Tilt | 0.706 | Hiring engineers in India | CTO / VP Eng |
| 5 | Weave | 0.706 | Hiring engineers in India | CTO / VP Eng |
| 6 | Zeely AI | 0.706 | Hiring in Ukraine (engineering, marketing, sales) | CTO / VP Eng |
| 7 | Sweed | 0.691 | Hiring in Brazil | Head of Marketing |
| 8 | Olly Olly | 0.684 | Hiring engineers in Brazil (remote) | VP Sales |
| 9 | PandaDoc | 0.684 | Hiring in Ukraine + 2 ops roles posted the same week | Head of Marketing |
| 10 | Ambrook | 0.670 | Engineering role posted in the last 48 hours | CTO / VP Eng |

A company that already hires outside the US is the best fit, because the hardest objection
("will remote work for us?") is already answered.

**14 companies were held back automatically**, each with a reason. For example:
- Dialpad, Glossier, A Place for Mom: 500+ people, likely already have an RPO
- Corti: Denmark HQ
- Gina's Tech Jobs: a staffing firm, so a competitor

**The Day 0 email it wrote for #1:**

> **subject:** the sales role at Jump
>
> Hi {{firstName}}, saw Jump has an open Tech Touch Account Manager role. We've got vetted SDRs and AEs
> who've worked with US teams and keep US hours. Flat monthly fee, no placement fee, cancel any month.
>
> Want me to send three profiles?

Full results: [`examples/live-run-2026-11-17/`](examples/live-run-2026-11-17/)
- [ranked accounts](examples/live-run-2026-11-17/accounts_ranked.csv) (96 companies, each with its "why")
- [the full 5-touch sequences](examples/live-run-2026-11-17/sample_sequences.md)
- [the 27 offshore job posts it found](examples/live-run-2026-11-17/offshore_posts.csv)

### Demo run: synthetic applications + the Nov 6 job scan

This run shows the private half: what the applications add on top of public posts.

```
1/7 synthetic applications -> 85 files in data/private/resumes (git-ignored)
2/7 parse (private box)      -> 84 kept, 1 repeat applicant dropped
3/7 public job posts         -> 216 roles from the Nov 6 scan
4/7 company-level signals    -> team_exits 2, offshore_now 3, vendor 1, spike 1, fresh_post 40, ...
5/7 scored accounts          -> 155
6/7 enrich (treg)            -> dry-run: 10 accounts, est. $0.055 if run live
7/7 drafts + privacy lint    -> 655 drafts, 0 blocked
```

**What the applications do here:**
- **Fernway Health** has no job post. It ranks because applications show it already employs remote staff in Mexico through Deel. The email cites only a public fact (a new VP Engineering hire).
- **Corvid Labs** has the same private signal but no public fact, so it is **held** and never emailed.
- **Quillstack** shows a layoff-style spike, so it waits about 45 days.
- **Northpine** has only 2 applicants from one team. That is below the privacy floor, so **no signal fires at all**.

Full results: [`examples/demo-synthetic-applications/`](examples/demo-synthetic-applications/)

---

## 3. How it works

```
 PRIVATE BOX (raw resumes never leave)                PUBLIC SIGNALS (the only things an email may cite)
 ┌──────────┐  ┌──────────────┐  ┌───────────┐        ┌───────────┐  ┌───────────┐  ┌──────────────┐
 │ ingest   │→ │ parse        │→ │ company-  │        │ job posts │  │ funding   │  │ new leaders  │
 │ + dedupe │  │ Docling+LLM  │  │ level     │        │ free ATS  │  │ Parallel /│  │ Parallel /   │
 │          │  │ fixed JSON   │  │ signals   │        │ APIs      │  │ treg      │  │ Exa / treg   │
 └──────────┘  └──────────────┘  └─────┬─────┘        └─────┬─────┘  └─────┬─────┘  └──────┬───────┘
                                       └──────────────┬─────┴──────────────┴───────────────┘
                                                      ▼
                                SCORE = fit × timing × can-we-fill-it
                                                      ▼
                       ENRICH: treg finds the buyer + a verified email (spend-capped)
                                                      ▼
                       DRAFT the 5-touch sequence → PRIVACY LINT (blocks any leak)
                                                      ▼
                       EXPORT → Instantly · HeyReach · HubSpot (intake brief pre-filled)
                                                      ▼
                       LEARN: what books meetings reweights the score
```

| Step | Command | What it does |
|---|---|---|
| Parse | `hh parse --dir PATH` | Turns each resume into one fixed JSON record. Name and email become a salted hash, used only to drop repeat applicants. |
| Job posts | `hh jobs --live` | Reads the public job board APIs. Keeps **our own first-seen date**, because posted dates lie. |
| Signals | `hh signals` | Builds company-level signals (section 4). |
| Score | `hh score` | Fit × timing × fill. Picks the play, the buyer and the send date (Tue to Thu). |
| Enrich | `hh enrich --live` | treg people search, then email find, then verify. Cheapest provider first, hard spend cap. |
| Draft | `hh draft` | Writes the Day 0/2/3/7/12 sequence and lints every message. |
| Export | `hh export` | Writes `out/*.csv` for Instantly, HeyReach, HubSpot and a ranked account list. |
| Learn | `hh learn outcomes.csv` | Signals that book meetings get more weight next time. |
| Report | `hh report` | Prints the top accounts and a sample email. |

---

## 4. The signals

### Private: from the applications (what nobody else has)

| # | Signal | What it means | What we do |
|---|---|---|---|
| 1 | `offshore_now` | Someone outside the US works remotely for this US company today | Best fit. They already pay for remote talent, and a backfill may be weeks away. |
| 2 | `vendor` | "Contractor via Deel" or an agency on the resume | Shows who they buy from today. Raises timing. |
| 3 | `team_exits` | 3+ people from one team applied within 30 days, adjusted for company size | A backfill is coming. Notice periods tell us roughly when. |
| 4 | `spike` | A sudden weekly spike from one company | Usually layoffs. Wait about 45 days, then lead with flexible monthly cost. |
| 5 | `bench` | Available people and pay, by role | Becomes the **fill** score. We only pitch roles we can fill in 48 hours. |

### Public: from job boards and news

| Signal | Rule |
|---|---|
| `fresh_post` | Posted in the last 2 days. The 48-hour window. |
| `recent_post` | Posted in the last 14 days |
| `offshore_post` | A US company posting a role abroad. Signal 1, visible in public. |
| `team_buildout` | 2+ roles in one bucket within 7 days |
| `still_open` | Open 21+ days by **our** first-seen date. Sends the "you might be hiring the wrong role" email. |

### The play, decided by what is public

| Play | When | First email |
|---|---|---|
| `after_post` | A relevant role is live | "Saw you have an open X role… want three profiles?" |
| `still_open` | Open 3+ weeks | "Sometimes it's the role, not the candidates… shortlist in 48 hours" |
| `before_post` | Private signal + a public fact (funding, new leader) | No role named. "Want profiles on file for when the need shows up?" |
| `spike_wait` | Layoff spike | Scheduled about 45 days out |
| `hold_no_public_fact` | Private signal only | **Not emailed.** Waits for a public trigger. |

---

## 5. Who we target

| Filter | Rule |
|---|---|
| Company | US-based, 10 to 200 people. Seed to Series B, bootstrapped, or just through layoffs |
| Roles | Remote roles in the four buckets: GTM, Engineering, Ops, Marketing |
| Best fit | Already works with remote or offshore people (+0.2 fit) |
| Skip | Staffing firms and talent marketplaces (competitors), non-US HQ, 500+ people |

| Company size | Who gets the email |
|---|---|
| Under 25 | Founder / CEO |
| 25 to 100 | Leader of the hiring team: VP Sales, COO, Head of Marketing, or CTO |
| 100+ | Head of Talent, plus the hiring manager on the post |

---

## 6. The privacy rule, enforced in code

**Nothing in an email can be traced back to a candidate.** Candidates are half of Hire Hangar's
business. One "how did you know Priya was leaving?" costs more than this whole channel is worth.

| Rule | Where |
|---|---|
| Names and emails are never stored. Applications keep company-level facts and a salted hash. | `hh/parse.py` |
| Raw resumes stay in `data/private/`, which git ignores | `.gitignore` |
| Team signals need **3+ applicants**. Below that, the signal doesn't exist. | `hh/config.py`, `hh/signals.py` |
| A company with only private signals is **held** until a public fact exists | `hh/score.py` |
| Every message is linted. It is blocked if it contains words like applicant, resume, leaving or resign, or any private signal text. | `hh/draft.py` |
| Tests check every generated message | `tests/test_pipeline.py` |

---

## 7. The stack: every tool and why it's there

Every paid tool is optional and runs on **your own keys** (BYOK). Nothing is billed to anyone else.

| Job | Tool | Why this tool | Cost | Status |
|---|---|---|---|---|
| Read resumes | **Docling** + a **small LLM** with a fixed JSON format | Docling handles PDF and DOCX layouts for free. A small model is enough to pull fields at 250K a month. | $0 Docling. Cents per 1K resumes, or **$0 with a local Ollama model** | ✅ built (`rules`, `anthropic` or `openai` mode) |
| Messy 5-10% of resumes | **Reducto / Extend** | Pay for heavy parsing only on scans and odd layouts | pay per page | planned |
| Storage + logic | **Postgres** + small Python jobs | Candidate data stays in house. One person can run it. | $0 (SQLite locally; the same SQL runs on Postgres) | ✅ built |
| Job posts | **Free ATS APIs** (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) | Official, structured and free | **$0** | ✅ built, tested live |
| Long-tail job boards | **JobSpy / Firecrawl** | Indeed, LinkedIn and career pages without an ATS API | $0 / pay per page | planned |
| People + work emails | **treg**: one login, 30+ data providers | Cheapest provider first, spend caps, no separate Apollo/Hunter/ZeroBounce seats | people search often $0, email find ≈ $0.005, verify ≈ $0.0004 | ✅ built (`hh enrich --live`) |
| Triggers | **Parallel Monitor**, **treg web search** | Funding and new-leader news, described in plain English | pay per use | `public_facts` table ready |
| Lookalikes | **Exa Websets** | "Companies like our best 20 clients" | pay per use | planned |
| Email sending | **Instantly**, separate domains, 15-20 warmed inboxes | Volume without risking hirehangar.com's sending reputation | ~$100-400/mo | ✅ CSV export |
| LinkedIn | **HeyReach** | The Day 2 connect step | ~$80/mo | ✅ CSV export |
| CRM | **HubSpot free** | Every yes arrives with the scoping-call brief filled in | $0 | ✅ CSV export |
| Testing a new play | **Clay** | Great for trying a play on a few hundred accounts. treg and Postgres carry the volume. | | — |

### Where treg fits

| Use treg for | Never use treg for |
|---|---|
| Finding the buyer at a company (`treg.people.search`) | Anything with applicant data. It never leaves the private box. |
| Finding and verifying work emails (`treg.people.email.find` / `.verify`) | Job posts. The ATS APIs are free and official. |
| Finding triggers (`treg.web.search`) | |
| Real headcount and HQ, to replace the size estimate | |

Every treg call sets a per-call price ceiling. Every run stops at `HH_TREG_MAX_SPEND_USD` (default $0.50).

---

## 8. What it costs

| What | Cost |
|---|---|
| `hh demo`, the tests, `hh jobs --live`, signals, scoring, drafts, exports | **$0.** No keys, no paid APIs. |
| `hh enrich --live` (treg) | About **$0.0055 per account**, so 100 accounts ≈ $0.55, hard-capped |
| Resume parsing with an LLM | $0 with local Ollama, or a few cents per 1,000 resumes with a small hosted model |
| **Full production volume** | About **$1K-1.5K a month**: inboxes and domains, Instantly, HeyReach, enrichment, parsing. Roughly one placement's monthly fee. |

**The funnel.** These are assumptions to replace with pilot data, not promises.

```
250K applications → ~100K with a resolvable employer → ~6K companies that fit → ~1.5K with a live trigger
→ ~2.6K people contacted → 60-90 good replies (3%) → 40-60 meetings a month (60% book)
```

The real ceiling is who takes the 2-3 scoping calls a day.

---

## 9. Running it for real (BYOK)

```bash
cp .env.example .env                             # fill in only what you use; .env is git-ignored

python3 -m hh jobs --live                        # daily: today's posts from data/seed_boards.csv
python3 -m hh parse --dir /path/to/ats-export    # .txt works as is; `pip install docling` for PDF/DOCX
python3 -m hh signals && python3 -m hh score

treg login                                       # once, with your own treg account
python3 -m hh enrich --live --limit 25           # buyer + verified email, spend-capped

python3 -m hh draft && python3 -m hh export      # writes out/*.csv
python3 -m hh report

# after the pilot: fill meeting_booked in out/outcomes_template.csv, then
python3 -m hh learn out/outcomes_template.csv && python3 -m hh score
```

| Setting in `.env` | What it's for |
|---|---|
| `HH_LLM_PROVIDER` | `rules` (free) / `anthropic` / `openai` (any OpenAI-compatible server, e.g. Ollama) |
| `ANTHROPIC_API_KEY` | Only if `HH_LLM_PROVIDER=anthropic` |
| `HH_HASH_SALT` | Salt for the applicant dedupe hash |
| `HH_TREG_MAX_SPEND_USD` | Spend cap per enrich run |

### First 30 days

| Week | Plan |
|---|---|
| 1 | Parse a week of applications and hand-check 300. Test the ICP against real clients (who bought, which roles, who stayed past month 3). Warm up domains. |
| 2 | Pick 300 accounts split by signal, plus a **no-signal control group** |
| 3-4 | Send. Founders take the top 30 personally. Scale what books. `hh learn` reweights the score. |

---

## 10. Repo map

```
hh/
  cli.py        commands: demo, jobs, parse, signals, score, enrich, draft, export, report, learn
  jobs.py       free ATS APIs + the Nov 6 snapshot loader
  parse.py      resume → fixed JSON (rules / Claude / any OpenAI-compatible model), PII dropped
  signals.py    company-level private + public signals
  score.py      fit × timing × fill, play, persona, send date
  enrich.py     treg people search → email find → verify, spend-capped
  draft.py      5-touch sequence + privacy lint
  export.py     Instantly / HeyReach / HubSpot CSVs + the learn step
  classify.py   role buckets, US/offshore locations, staffing filter
  synth.py      synthetic applicants for the demo
  db.py         schema (SQLite now, Postgres-ready)
data/
  seed_boards.csv               126 company job boards (from the Nov 6 scan)
  job-post-scan-2026-11-06.csv  216 real roles, used by the demo
  firmographics_overrides.csv   hand-checked HQ/size fixes (treg replaces this)
examples/
  live-run-2026-11-17/          real output from today's live pull
  demo-synthetic-applications/  output of `hh demo`
out/            export files from the last run
tests/          pipeline + privacy tests
docs/deck.pdf   the take-home deck
```

---

## 11. Known limits and next steps

- **Company size is an estimate.** In public-only runs we don't know headcount yet, so it counts as "unknown". treg firmographics will replace this. A few known cases are fixed by hand in `data/firmographics_overrides.csv`.
- **Role buckets use keywords.** In production, a small LLM classifies each role from the job description.
- **`still_open` needs history.** It needs at least 3 weeks of daily pulls to build our own first-seen dates.
- **Not wired in yet:** Exa Websets, Parallel Monitor and JobSpy. They write into the existing `public_facts` and `job_posts` tables.
- **Profiles in the Day 3 email are placeholders.** In production they're pulled from the bench for the matching role.

---

Built by **Divyashree Mohanty** for Hire Hangar · November 2026
