"""Hand-off files. Import into Instantly (email, separate sending domains), HeyReach (LinkedIn)
and HubSpot free (companies, with the scoping-call intake brief already filled in).
CSV import is free and works on every plan; API push can be added per tool with your key."""
import csv
import json

from .config import OUT


def run(con):
    OUT.mkdir(exist_ok=True)
    drafts = {}
    for d in con.execute("SELECT * FROM drafts ORDER BY domain, step"):
        drafts.setdefault(d["domain"], []).append(dict(d))
    accts = [dict(a) for a in con.execute("SELECT * FROM accounts ORDER BY score DESC")]
    contacts = {c["domain"]: dict(c) for c in con.execute("SELECT * FROM contacts")}

    with open(OUT / "accounts_ranked.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "company", "domain", "score", "fit", "timing", "fill", "play", "status", "top_signal",
                    "bucket", "email_to", "send_after", "public_fact", "why"])
        for i, a in enumerate(accts, 1):
            w.writerow([i, a["name"], a["domain"], a["score"], a["fit"], a["timing"], a["fill"], a["play"], a["status"],
                        a["top_signal"], a["bucket"], a["persona"], a["send_after"], a["public_fact"] or "",
                        " | ".join(json.loads(a["reasons"]))])

    ok = lambda dom: all(x["lint"] == "ok" for x in drafts.get(dom, []))
    with open(OUT / "instantly_leads.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["email", "first_name", "company_name", "website", "signal", "send_after"] +
                   [f"step{i}_{k}" for i in range(5) for k in ("subject", "body")])
        for a in accts:
            ds = drafts.get(a["domain"])
            if not ds or not ok(a["domain"]):
                continue
            c = contacts.get(a["domain"], {})
            cells = []
            for x in sorted(ds, key=lambda x: x["step"]):
                cells += [x["subject"], x["body"]]
            w.writerow([c.get("email") or "", c.get("first_name") or "", a["name"], a["domain"], a["top_signal"],
                        a["send_after"]] + cells)

    with open(OUT / "heyreach_linkedin.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["linkedin_url", "full_name", "company", "connect_note", "send_on"])
        for a in accts:
            for x in drafts.get(a["domain"], []):
                if x["channel"] == "linkedin" and ok(a["domain"]):
                    c = contacts.get(a["domain"], {})
                    w.writerow([c.get("linkedin_url") or "", c.get("full_name") or "", a["name"], x["body"], x["send_at"]])

    with open(OUT / "hubspot_companies.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Company name", "Company Domain Name", "hh_score", "hh_signal", "hh_play", "hh_role_bucket",
                    "hh_intake_brief"])
        for a in accts:
            if a["status"] != "ready":
                continue
            brief = (f"Signal: {a['top_signal']}. Hook used: {a['public_fact']}. Likely role bucket: {a['bucket']}. "
                     f"Buyer: {a['persona']}. Fit {a['fit']}, timing {a['timing']}, fill {a['fill']}.")
            w.writerow([a["name"], a["domain"], a["score"], a["top_signal"], a["play"], a["bucket"], brief])

    # outcomes template for the feedback loop (fill sent/meeting after the pilot, then `hh learn`)
    with open(OUT / "outcomes_template.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["domain", "top_signal", "sent", "meeting_booked"])
        for a in accts:
            if a["status"] == "ready":
                w.writerow([a["domain"], a["top_signal"], 1, 0])
    return {"files": ["accounts_ranked.csv", "instantly_leads.csv", "heyreach_linkedin.csv",
                      "hubspot_companies.csv", "outcomes_template.csv"]}


def learn(con, path):
    """What books meetings reweights the score: weight = signal's meeting rate / overall rate (smoothed)."""
    rows = list(csv.DictReader(open(path)))
    tot_s = sum(int(r["sent"]) for r in rows) or 1
    tot_m = sum(int(r["meeting_booked"]) for r in rows)
    base = (tot_m + 1) / (tot_s + 10)
    by = {}
    for r in rows:
        s = by.setdefault(r["top_signal"], [0, 0])
        s[0] += int(r["sent"]); s[1] += int(r["meeting_booked"])
    out = {}
    for sig, (sent, met) in by.items():
        out[sig] = round(min(2.0, max(0.3, ((met + base * 10) / (sent + 10)) / base)), 2)
        con.execute("INSERT OR REPLACE INTO signal_weights VALUES (?,?)", (sig, out[sig]))
    con.commit()
    return out
