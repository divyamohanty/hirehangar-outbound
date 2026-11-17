"""Turn rows into COMPANY-LEVEL signals. Nothing below a company leaves this module.

Private (from applications, slide 5):          Public (from job posts / facts):
  offshore_now  remote non-US staff today         fresh_post     posted <= 2 days ago (48h window)
  vendor        buys via Deel/EOR/agency today    recent_post    posted <= 14 days ago
  team_exits    >=3 from one team in 30 days      still_open     open >= 21 days by OUR first-seen date
  spike         sudden weekly spike (layoffs)     offshore_post  US company posting an offshore role
  bench         what we can fill, by role         team_buildout  >=2 posts in one bucket within 7 days
"""
import datetime as dt
import statistics
from collections import Counter, defaultdict

from .config import TEAM_SIGNAL_MIN_APPLICANTS, TEAM_SIGNAL_WINDOW_DAYS


def _d(s):
    return dt.date.fromisoformat(s[:10]) if s else None


def compute(con, as_of):
    con.execute("DELETE FROM company_signals")
    con.execute("DELETE FROM bench")
    now = dt.datetime.utcnow().isoformat(timespec="seconds")
    sig = []  # (domain, signal, strength, detail)
    since = as_of - dt.timedelta(days=TEAM_SIGNAL_WINDOW_DAYS)

    apps = [dict(r) for r in con.execute("SELECT * FROM applications")]
    apps = [a for a in apps if a["received_at"] and since <= _d(a["received_at"]) <= as_of]
    heads = {r["domain"]: r["headcount"] for r in con.execute("SELECT domain, headcount FROM companies")}
    hq = {r["domain"]: r["hq_country"] for r in con.execute("SELECT domain, hq_country FROM companies")}

    by_co = defaultdict(list)
    for a in apps:
        if a["employer_domain"]:
            by_co[a["employer_domain"]].append(a)

    for dom, rows in by_co.items():
        hc = heads.get(dom) or 50
        # spike first: a layoff week overrides the team signal (different play, later timing)
        weeks = Counter(_d(a["received_at"]).isocalendar()[1] for a in rows)
        wk, peak = weeks.most_common(1)[0]
        if peak >= max(5, round(0.05 * hc)):
            sig.append((dom, "spike", 0.5, f"{peak} applicants in ISO week {wk}"))
            continue
        offshore = [a for a in rows if a["remote_for_us_company"] and (a["applicant_country"] or "") != "United States"
                    and hq.get(dom) in (None, "US")]
        if offshore:
            sig.append((dom, "offshore_now", 0.85, f"{len(offshore)} remote non-US staff in {sorted({a['role_bucket'] for a in offshore})}"))
        vendors = sorted({a["vendor"] for a in rows if a["vendor"]})
        if vendors:
            sig.append((dom, "vendor", 0.6, "buys via " + ", ".join(vendors)))
        teams = Counter((a["team"], a["role_bucket"]) for a in rows)
        for (team, bucket), n in teams.items():
            if n < TEAM_SIGNAL_MIN_APPLICANTS:
                continue  # privacy floor: never act on 1-2 people
            rate = n / hc
            notice = max((a["notice_weeks"] or 0) for a in rows if a["team"] == team)
            sig.append((dom, "team_exits", min(1.0, 0.6 + 0.1 * (n - 3) + 2 * rate),
                        f"{bucket}: {n} from one team in {TEAM_SIGNAL_WINDOW_DAYS}d, backfill in ~{notice}w"))

    # bench: who we could actually place, by role (slide 5, signal 5)
    bench = defaultdict(list)
    for a in apps:
        if a["role_bucket"] and (a["applicant_country"] or "") != "United States":
            bench[a["role_bucket"]].append(a)
    for b, rows in bench.items():
        rates = [a["monthly_rate_usd"] for a in rows if a["monthly_rate_usd"]]
        top = Counter(a["applicant_country"] for a in rows).most_common(1)[0][0]
        con.execute("INSERT INTO bench VALUES (?,?,?,?)", (b, len(rows), int(statistics.median(rates)) if rates else None, top))

    # public signals
    posts = defaultdict(list)
    for p in con.execute("SELECT * FROM job_posts"):
        posts[p["domain"]].append(dict(p))
    for dom, ps in posts.items():
        ages = []
        for p in ps:
            seen = _d(p["first_seen"]) or _d(p["posted_at"])
            posted = _d(p["posted_at"]) or seen
            ages.append(((as_of - posted).days, (as_of - seen).days, p))
        fresh = [p for a, _, p in ages if 0 <= a <= 2]
        recent = [p for a, _, p in ages if 0 <= a <= 14]
        stale = [p for _, s, p in ages if s >= 21 and _d(p["last_seen"]) and (as_of - _d(p["last_seen"])).days <= 2]
        if fresh:
            sig.append((dom, "fresh_post", 0.85, fresh[0]["title"]))
        elif recent:
            sig.append((dom, "recent_post", 0.6, recent[0]["title"]))
        if stale:
            sig.append((dom, "still_open", 0.65, stale[0]["title"]))
        off = [p for p in ps if p["offshore_location"]]
        if off:
            sig.append((dom, "offshore_post", 0.9, f"{off[0]['title']} ({off[0]['location']})"))
        per_bucket = Counter(p["bucket"] for age, _s, p in ages if 0 <= age <= 7)
        b, n = (per_bucket.most_common(1) or [(None, 0)])[0]
        if n >= 2:
            sig.append((dom, "team_buildout", 0.75, f"{n} {b} roles in 7 days"))

    con.executemany("INSERT OR REPLACE INTO company_signals VALUES (?,?,?,?,?)", [s + (now,) for s in sig])
    con.commit()
    return Counter(s[1] for s in sig)
