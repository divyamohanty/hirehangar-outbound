"""SCORE = fit x timing x can-we-fill-it (slide 4). Private data picks and times the account;
the play and the email's hook come only from public facts. Weights are learned from what
books meetings (`hh learn`)."""
import datetime as dt
import json
from collections import defaultdict

from . import classify

DEFAULT_WEIGHTS = {
    "fresh_post": 1.0, "recent_post": 1.0, "still_open": 1.0, "offshore_post": 1.0, "team_buildout": 1.0,
    "offshore_now": 1.0, "vendor": 1.0, "team_exits": 1.0, "spike": 1.0,
}
PRIVATE_SIGNALS = {"offshore_now", "vendor", "team_exits", "spike"}


def weights(con):
    w = dict(DEFAULT_WEIGHTS)
    for r in con.execute("SELECT signal, weight FROM signal_weights"):
        w[r["signal"]] = r["weight"]
    return w


def fit_score(co, has_remote):
    reasons = []
    if co["is_staffing"] or classify.looks_like_staffing(co["name"] or "", co["domain"]):
        return 0.0, ["skip: staffing/talent firm (competitor)"]
    if co["hq_country"] not in (None, "", "US"):
        return 0.0, [f"skip: HQ {co['hq_country']}"]
    hc = co["headcount"]
    if hc is None:
        f = 0.7; reasons.append("size unknown (enrich)")
    elif 10 <= hc <= 200:
        f = 0.8; reasons.append(f"~{hc} people, in ICP")
    elif hc < 10:
        f = 0.4; reasons.append(f"~{hc} people, very small")
    elif hc <= 500:
        f = 0.4; reasons.append(f"~{hc} people, above ICP")
    else:
        return 0.05, [f"skip: ~{hc} people, likely has an RPO"]
    if has_remote:
        f = min(1.0, f + 0.2); reasons.append("already hires remote/offshore")
    else:
        f = round(f * 0.75, 2); reasons.append("no remote roles seen yet")
    return round(f, 2), reasons


def persona(headcount, bucket):
    if headcount is not None and headcount < 25:
        return "Founder / CEO"
    if headcount is None or headcount <= 100:
        return {"GTM": "VP Sales", "Ops": "COO", "Marketing": "Head of Marketing",
                "Engineering": "CTO / VP Engineering"}.get(bucket, "Founder / CEO")
    return "Head of Talent + hiring manager on the post"


def next_send_window(after):
    """Tue-Thu morning in the prospect's time zone (stored as a date; 9am local is applied by the sender)."""
    d = after
    while d.weekday() not in (1, 2, 3):
        d += dt.timedelta(days=1)
    return d


def run(con, as_of):
    con.execute("DELETE FROM accounts")
    w = weights(con)
    bench = {r["role_bucket"]: dict(r) for r in con.execute("SELECT * FROM bench")}
    sigs = defaultdict(dict)
    for r in con.execute("SELECT * FROM company_signals"):
        sigs[r["domain"]][r["signal"]] = dict(r)
    facts = defaultdict(list)
    for r in con.execute("SELECT * FROM public_facts"):
        facts[r["domain"]].append(dict(r))
    buckets = defaultdict(list)
    for r in con.execute("SELECT domain, bucket, title FROM job_posts"):
        buckets[r["domain"]].append(r["bucket"])
    for r in con.execute("SELECT employer_domain d, role_bucket b FROM applications WHERE employer_domain IS NOT NULL"):
        buckets[r["d"]].append(r["b"])

    rows = []
    for co in con.execute("SELECT * FROM companies"):
        dom = co["domain"]
        s = sigs.get(dom, {})
        if not s:
            continue
        has_remote = any(k in s for k in ("offshore_now", "offshore_post", "vendor")) or \
            con.execute("SELECT 1 FROM job_posts WHERE domain=? AND remote='yes' LIMIT 1", (dom,)).fetchone() is not None
        fit, reasons = fit_score(co, has_remote)

        bucket = max(set(buckets[dom]), key=buckets[dom].count) if buckets[dom] else None
        b = bench.get(bucket) or {}
        if bench:
            fill = round(min(1.0, max(0.2, (b.get("available") or 0) / 25)), 2)
        else:  # no applications loaded yet (public-only run): don't let an empty bench flatten every score
            fill = 0.8
            reasons.append("fill not measured (no applications loaded)")

        timing_sigs = {k: v for k, v in s.items() if k != "spike"}
        timing = max([v["strength"] * w.get(k, 1.0) for k, v in timing_sigs.items()] or [0.0])
        n_open = con.execute("SELECT COUNT(*) FROM job_posts WHERE domain=?", (dom,)).fetchone()[0]
        if n_open > 1:  # several relevant roles open = more urgency; small, capped tie-breaker
            timing = min(1.0, timing + min(0.08, 0.01 * (n_open - 1)))
        if "vendor" in s and len(timing_sigs) > 1:
            timing = min(1.0, timing + 0.1)
        top = max(timing_sigs, key=lambda k: timing_sigs[k]["strength"] * w.get(k, 1.0)) if timing_sigs else "spike"

        # the play is decided by what is PUBLIC
        send_after = next_send_window(as_of)
        if "fresh_post" in s or "recent_post" in s:
            play = "after_post"
            # the hook must be a role in the bucket we pitch (don't cite a brand role and offer engineers)
            match = con.execute("SELECT title FROM job_posts WHERE domain=? AND bucket=? ORDER BY posted_at DESC LIMIT 1",
                                (dom, bucket)).fetchone()
            title = match["title"] if match else (s.get("fresh_post") or s.get("recent_post"))["detail"]
            fact = f"has an open {title} role"
        elif "still_open" in s:
            play = "still_open"
            fact = f"the {s['still_open']['detail']} role has been open a few weeks"
        elif "offshore_post" in s:
            play = "after_post"
            fact = f"is hiring {s['offshore_post']['detail']}"
        elif facts.get(dom):
            play = "before_post"
            fact = facts[dom][0]["fact"]
        elif "spike" in s:
            play, fact = "spike_wait", None
            send_after = next_send_window(as_of + dt.timedelta(days=45))
            timing = 0.4
        else:
            play, fact = "hold_no_public_fact", None  # private signal only: wait for a public trigger

        if fact:
            fact = " ".join(fact.split())  # job titles often carry stray spaces
        if "spike" in s and play != "spike_wait":
            reasons.append("recent spike: lead with flexible monthly cost")
        reasons += [f"{k}: {v['detail']}" if k not in PRIVATE_SIGNALS else f"{k} (private, company-level)"
                    for k, v in s.items()]
        score = round(fit * timing * fill, 3)
        status = "ready" if play in ("after_post", "still_open", "before_post") and fit >= 0.4 else "hold"
        rows.append((dom, co["name"], fit, round(timing, 2), fill, score, play, top, json.dumps(reasons), fact,
                     bucket, persona(co["headcount"], bucket), send_after.isoformat(), status))

    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)
