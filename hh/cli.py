"""hh: the Hire Hangar outbound pipeline.

  python3 -m hh demo                 # whole pipeline, offline, $0, no keys
  python3 -m hh jobs --live          # pull today's posts from free ATS APIs
  python3 -m hh parse --dir PATH     # parse a folder of real resumes (txt/pdf/docx)
  python3 -m hh signals | score | enrich [--live] | draft | export | report
  python3 -m hh learn out/outcomes.csv
"""
import argparse
import datetime as dt
import json
import os
import shutil

from . import db, draft, enrich, export, jobs, parse, score, signals, synth
from .config import OUT, PRIVATE


def as_of(args):
    return dt.date.fromisoformat(args.as_of) if getattr(args, "as_of", None) else dt.date.today()


def report(con, top=15):
    print("\nTOP ACCOUNTS (score = fit x timing x fill)")
    print(f"{'#':>2}  {'company':28} {'score':>5}  {'play':20} {'signal':14} {'email to':22} {'send'}")
    for i, a in enumerate(con.execute("SELECT * FROM accounts ORDER BY status='ready' DESC, score DESC LIMIT ?", (top,)), 1):
        print(f"{i:>2}  {a['name'][:28]:28} {a['score']:>5}  {a['play'][:20]:20} {a['top_signal'][:14]:14} "
              f"{a['persona'][:22]:22} {a['send_after']}")
    held = con.execute("SELECT play, COUNT(*) n FROM accounts WHERE status='hold' GROUP BY play").fetchall()
    print("\nheld back:", ", ".join(f"{r['play']}={r['n']}" for r in held) or "none")
    d = con.execute("SELECT domain, subject, body FROM drafts WHERE step=0 AND lint='ok' AND domain LIKE '%.example' "
                    "ORDER BY rowid LIMIT 1").fetchone() or \
        con.execute("SELECT domain, subject, body FROM drafts WHERE step=0 AND lint='ok' LIMIT 1").fetchone()
    if d:
        print(f"\nSAMPLE DAY-0 EMAIL ({d['domain']})\nsubject: {d['subject']}\n\n{d['body']}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("demo"); p.add_argument("--live-jobs", action="store_true", help="also pull live ATS posts")
    p = sub.add_parser("jobs"); p.add_argument("--live", action="store_true"); p.add_argument("--limit", type=int)
    p = sub.add_parser("parse"); p.add_argument("--dir", default=str(PRIVATE / "resumes"))
    for name in ("signals", "score", "draft"):
        p = sub.add_parser(name); p.add_argument("--as-of")
    p = sub.add_parser("enrich"); p.add_argument("--live", action="store_true"); p.add_argument("--limit", type=int, default=10)
    sub.add_parser("export"); sub.add_parser("report")
    p = sub.add_parser("learn"); p.add_argument("outcomes")
    args = ap.parse_args(argv)

    if args.cmd == "demo":
        # Pretend today is Nov 6 2026, the day the public scan was run, so both layers line up.
        day = dt.date(2026, 11, 6)
        if (OUT / "hh.sqlite").exists():
            (OUT / "hh.sqlite").unlink()
        con = db.connect()
        print("1/7 synthetic applications ->", synth.generate(day), "files in data/private/resumes (git-ignored)")
        print("2/7 parse (private box)      ->", parse.ingest_dir(con, PRIVATE / "resumes"))
        synth.write_demo_public(con)
        print("3/7 public job posts         ->", jobs.load_snapshot(con), "roles from the Nov 6 scan")
        if args.live_jobs:
            print("    + live ATS pull          ->", jobs.pull_live(con))
        print("4/7 company-level signals    ->", dict(signals.compute(con, day)))
        print("5/7 scored accounts          ->", score.run(con, day))
        print("6/7 enrich (treg)            ->", enrich.run(con, live=False))
        print("7/7 drafts + privacy lint    ->", draft.run(con, day))
        print("    exports                  ->", export.run(con)["files"], "in out/")
        report(con)
        return

    con = db.connect()
    if args.cmd == "jobs":
        print(jobs.pull_live(con, limit=args.limit) if args.live else {"snapshot_rows": jobs.load_snapshot(con)})
    elif args.cmd == "parse":
        print(parse.ingest_dir(con, args.dir))
    elif args.cmd == "signals":
        print(dict(signals.compute(con, as_of(args))))
    elif args.cmd == "score":
        print(score.run(con, as_of(args)))
    elif args.cmd == "enrich":
        print(enrich.run(con, live=args.live, limit=args.limit))
    elif args.cmd == "draft":
        print(draft.run(con, as_of(args)))
    elif args.cmd == "export":
        print(export.run(con))
    elif args.cmd == "report":
        report(con)
    elif args.cmd == "learn":
        print(json.dumps(export.learn(con, args.outcomes), indent=1))
