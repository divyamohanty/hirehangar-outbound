"""Public layer, part 1: job posts from free, official ATS APIs (Greenhouse, Lever, Ashby,
Workable, SmartRecruiters). No key, no cost. We store our OWN first_seen date because posted
dates lie (56% of SmartRecruiters matches claimed to be over a year old on Nov 6)."""
import csv
import re
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import classify
from .config import DATA

UA = {"User-Agent": "hh-outbound/0.1 (job-board reader)"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _iso(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):  # Lever: epoch ms
        return dt.datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")
    return str(v)[:10]


def fetch_board(ats, slug):
    """-> list of dicts {id,title,location,remote,url,posted_at}"""
    out = []
    if ats == "greenhouse":
        j = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        for x in j.get("jobs", []):
            out.append(dict(id=f"gh:{x['id']}", title=x.get("title"), location=(x.get("location") or {}).get("name", ""),
                            remote="", url=x.get("absolute_url"), posted_at=_iso(x.get("first_published") or x.get("updated_at"))))
    elif ats == "lever":
        j = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        for x in j:
            c = x.get("categories") or {}
            out.append(dict(id=f"lv:{x['id']}", title=x.get("text"), location=c.get("location", ""),
                            remote=x.get("workplaceType", ""), url=x.get("hostedUrl"), posted_at=_iso(x.get("createdAt"))))
    elif ats == "ashby":
        j = _get(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.request.quote(slug)}")
        for x in j.get("jobs", []):
            out.append(dict(id=f"ab:{x.get('id')}", title=x.get("title"), location=x.get("location", ""),
                            remote="remote" if x.get("isRemote") else (x.get("workplaceType") or ""),
                            url=x.get("jobUrl"), posted_at=_iso(x.get("publishedAt"))))
    elif ats == "workable":
        j = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        for x in j.get("jobs", []):
            loc = ", ".join(filter(None, [x.get("city"), x.get("state"), x.get("country")]))
            out.append(dict(id=f"wk:{x.get('shortcode')}", title=x.get("title"), location=loc,
                            remote="remote" if x.get("telecommuting") else "", url=x.get("url"),
                            posted_at=_iso(x.get("published_on"))))
    elif ats == "smartrecruiters":
        j = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
        for x in j.get("content", []):
            l = x.get("location") or {}
            loc = ", ".join(filter(None, [l.get("city"), l.get("region"), l.get("country")]))
            out.append(dict(id=f"sr:{x.get('id')}", title=x.get("name"), location=loc,
                            remote="remote" if l.get("remote") else "",
                            url=f"https://jobs.smartrecruiters.com/{slug}/{x.get('id')}", posted_at=_iso(x.get("releasedDate"))))
    return out


def _upsert(con, domain, company, p, source, today):
    b = classify.bucket(p["title"])
    if not b:
        return False
    is_us, is_remote, offshore = classify.location_flags(p["location"], p["remote"])
    if not (is_us or offshore):
        return False
    con.execute(
        """INSERT INTO job_posts (id,domain,company,title,bucket,location,remote,offshore_location,source,url,posted_at,first_seen,last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen""",
        (p["id"], domain, company, p["title"], b, p["location"], "yes" if is_remote else "no", offshore,
         source, p["url"], p["posted_at"], today, today),
    )
    return True


def pull_live(con, seeds_csv=None, limit=None, workers=8):
    seeds = list(csv.DictReader(open(seeds_csv or DATA / "seed_boards.csv")))
    if limit:
        seeds = seeds[:limit]
    today = dt.date.today().isoformat()
    stats = {"boards": 0, "failed": 0, "jobs_seen": 0, "kept": 0}

    def work(s):
        try:
            return s, fetch_board(s["ats"], s["slug"])
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
            return s, e

    with ThreadPoolExecutor(workers) as ex:
        for s, res in ex.map(work, seeds):
            if isinstance(res, Exception):
                stats["failed"] += 1
                continue
            stats["boards"] += 1
            stats["jobs_seen"] += len(res)
            for p in res:
                stats["kept"] += _upsert(con, s["domain"], s["company"], p, s["ats"], today)
            con.execute("INSERT OR IGNORE INTO companies (domain,name) VALUES (?,?)", (s["domain"], s["company"]))
    apply_overrides(con)
    con.commit()
    return stats


def load_snapshot(con, path=None):
    """Offline mode: load the Nov 6 scan (218 real roles, 150 companies) as if just pulled."""
    path = path or DATA / "job-post-scan-2026-11-06.csv"
    snap = dt.date(2026, 11, 6)
    n = 0
    for r in csv.DictReader(open(path)):
        days = int(r["days_since_posted"] or 0)
        posted = (snap - dt.timedelta(days=days)).isoformat()
        p = dict(id=f"snap:{r['url']}", title=r["title"], location=r["location"], remote=r["remote"],
                 url=r["url"], posted_at=posted)
        if _upsert(con, r["domain"], r["company"], p, "snapshot-2026-11-06", posted):
            n += 1
        # open_jobs_on_board is our free size proxy until enrichment gives real headcount
        name = r["company"]
        if re.search(r"\b(manager|director|head of|specialist|lead|executive)\b", name, re.I):  # scraper grabbed a job title as the company name; trust the domain
            name = r["domain"].split(".")[0].replace("-", " ").title()
        est = int(r["open_jobs_on_board"] or 0) * 6
        con.execute("INSERT OR IGNORE INTO companies (domain,name,hq_country,headcount) VALUES (?,?,?,?)",
                    (r["domain"], name, None, est or None))
    apply_overrides(con)
    con.commit()
    return n


def apply_overrides(con, path=None):
    """Hand-checked firmographics. In production these come from treg company enrichment."""
    path = path or DATA / "firmographics_overrides.csv"
    for r in csv.DictReader(open(path)):
        con.execute("UPDATE companies SET hq_country=COALESCE(?,hq_country), headcount=COALESCE(?,headcount), "
                    "is_staffing=? WHERE domain=?",
                    (r["hq_country"] or None, int(r["headcount"]) if r["headcount"] else None,
                     int(r["is_staffing"] or 0), r["domain"]))
