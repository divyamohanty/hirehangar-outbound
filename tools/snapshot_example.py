"""Save a run's results (public data only) as readable examples: python3 tools/snapshot_example.py OUT_DIR"""
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(os.environ.get("HH_DB", "out/hh.sqlite"))
con.row_factory = sqlite3.Row
acc = list(con.execute("SELECT * FROM accounts ORDER BY status='ready' DESC, score DESC"))

with open(out / "accounts_ranked.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["rank", "company", "domain", "score", "fit", "timing", "fill", "play", "status", "top_signal",
                "role_bucket", "email_to", "public_hook", "why"])
    for i, a in enumerate(acc, 1):
        w.writerow([i, a["name"], a["domain"], a["score"], a["fit"], a["timing"], a["fill"], a["play"], a["status"],
                    a["top_signal"], a["bucket"], a["persona"], a["public_fact"] or "", " | ".join(json.loads(a["reasons"]))])

md = ["# Sample sequences\n\n`{{firstName}}` is filled in by Instantly once treg has found the contact.\n"]
for a in [x for x in acc if x["status"] == "ready"][:3]:
    md.append(f"\n## {a['name']} ({a['domain']})\n\nscore **{a['score']}** · signal `{a['top_signal']}` · email to: {a['persona']}\n")
    for r in con.execute("SELECT * FROM drafts WHERE domain=? ORDER BY step", (a["domain"],)):
        subj = f" · subject: _{r['subject']}_" if r["subject"] else ""
        md.append(f"\n**Day {r['day']} · {r['channel']}**{subj}\n\n> " + r["body"].replace("\n", "\n> ") + "\n")
(out / "sample_sequences.md").write_text("".join(md))

with open(out / "offshore_posts.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["company", "title", "location"])
    for r in con.execute("SELECT company, title, location FROM job_posts WHERE offshore_location IS NOT NULL ORDER BY company"):
        w.writerow(list(r))
print(f"{len(acc)} accounts -> {out}")
