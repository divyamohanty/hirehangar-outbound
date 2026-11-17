"""Find the right person and a verified email with treg (one login, 30+ providers,
cheapest first, spend caps). Runs with YOUR treg account: `treg login`. Dry-run by default.

Per account:  people.search(domain + persona title)  -> email.find -> email.verify
Typical cost: people.search often free (quickenrich/leadsforge), email.find ~$0.005, verify ~$0.0004.
"""
import json
import shutil
import subprocess

from . import config

PERSONA_TITLES = {
    "Founder / CEO": "CEO",
    "VP Sales": "VP Sales",
    "COO": "COO",
    "Head of Marketing": "Head of Marketing",
    "CTO / VP Engineering": "CTO",
    "Head of Talent + hiring manager on the post": "Head of Talent",
}


class Budget:
    def __init__(self, cap):
        self.cap, self.spent = cap, 0.0

    def ok(self, next_max):
        return self.spent + next_max <= self.cap


def treg_call(tool, body, max_cost, extra_headers=()):
    cmd = [config.TREG_BIN, "--json", "call", tool, "--method", "POST",
           "--header", f"X-Treg-Route-Max-Cost: {max_cost}", "--data", json.dumps(body)]
    for h in extra_headers:
        cmd += ["--header", h]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    j = json.loads(r.stdout or "{}")
    charged = (j.get("_treg") or {}).get("charged_micro", 0) / 1_000_000
    return (j.get("result") or {}).get("output"), charged


def run(con, live=False, limit=10):
    accts = list(con.execute("SELECT * FROM accounts WHERE status='ready' ORDER BY score DESC LIMIT ?", (limit,)))
    if not live:
        for a in accts:
            con.execute("INSERT OR IGNORE INTO contacts VALUES (?,?,?,?,?,?,?,?)",
                        (a["domain"], f"[{a['persona']}]", None, a["persona"], None, "dry-run", None, "dry-run"))
        con.commit()
        return {"mode": "dry-run", "accounts": len(accts),
                "est_cost_usd": round(len(accts) * 0.0055, 4), "hint": "run `hh enrich --live` after `treg login`"}
    if not shutil.which(config.TREG_BIN):
        raise SystemExit("treg not found. Install: uv tool install 'tools-registry[proxy]' then `treg login`.")
    budget = Budget(config.TREG_MAX_SPEND_USD)
    found = 0
    for a in accts:
        if not budget.ok(0.07):
            print(f"  spend cap ${config.TREG_MAX_SPEND_USD} reached, stopping")
            break
        title = PERSONA_TITLES.get(a["persona"], "CEO")
        people, c = treg_call("treg.people.search", {"company_domain": a["domain"], "title": title, "limit": 3}, 0.02)
        budget.spent += c
        rows = (people or {}).get("people") if isinstance(people, dict) else people
        if not rows:
            continue
        p = rows[0]
        full = p.get("full_name") or " ".join(filter(None, [p.get("first_name"), p.get("last_name")]))
        fn, ln = (full.split(" ", 1) + [""])[:2]
        em, c = treg_call("treg.people.email.find", {"first_name": fn, "last_name": ln, "domain": a["domain"]}, 0.009,
                          ["X-Treg-Route-Exclude: crawl4ai"])
        budget.spent += c
        email = em.get("email") if isinstance(em, dict) else None
        status = None
        if email:
            v, c = treg_call("treg.people.email.verify", {"email": email}, 0.004)
            budget.spent += c
            status = (v or {}).get("status") if isinstance(v, dict) else None
        con.execute("INSERT OR REPLACE INTO contacts VALUES (?,?,?,?,?,?,?,?)",
                    (a["domain"], full, fn, p.get("title") or title, email, status,
                     p.get("linkedin_url") or p.get("linkedin"), "treg"))
        found += 1
    con.commit()
    return {"mode": "live", "accounts": len(accts), "contacts": found, "spent_usd": round(budget.spent, 4)}
