"""Sequence + copy (slide 9) and the privacy linter (slide 10).

DAY 0  email tied to something public      DAY 7  cost comparison in the $2k-$5k+ bands
DAY 2  LinkedIn connect (HeyReach)         DAY 12 "want profiles next time you open a role?"
DAY 3  3 anonymised profiles matching the JD
Rules: under 90 words, no links in email 1, Tue-Thu mornings in their time zone.
"""
import datetime as dt
import re

SEATS = {"GTM": "sales", "Marketing": "marketing", "Ops": "ops", "Engineering": "engineering"}
PEOPLE = {"GTM": "SDRs and AEs", "Marketing": "marketers", "Ops": "ops people", "Engineering": "engineers"}
FORBIDDEN = re.compile(
    r"\b(applicant|applied|application|resume|résumé|cv|leaving|resign\w*|quit\w*|notice period|"
    r"interviewing|job[- ]hunting|our database|your (former|current) (employee|staff|team member))\b", re.I)
URL = re.compile(r"https?://|www\.|\.com\b", re.I)


def _first(name):
    if not name or name.startswith("["):  # contact not enriched yet: leave the sender's merge tag
        return "{{firstName}}"
    return name.split(" ")[0]


def build(a, contact, bench):
    """-> list of (step, day, channel, subject, body)"""
    co, fact, b = a["name"], a["public_fact"], a["bucket"] or "GTM"
    who = PEOPLE.get(b, "operators")
    first = _first(contact.get("full_name") if contact else None)
    rate = (bench.get(b) or {}).get("median_rate_usd")
    if a["play"] == "after_post":
        subj, body = f"the {b.lower()} role at {co}", (
            f"Hi {first}, saw {co} {fact}. We've got vetted {who} who've worked with US teams and keep US hours. "
            f"Flat monthly fee, no placement fee, cancel any month.\n\nWant me to send three profiles?")
    elif a["play"] == "still_open":
        subj, body = "still hiring?", (
            f"Hi {first}, noticed {fact}. When a role sits open that long it's sometimes the role, not the "
            f"candidates, and we'll say so if it is. We can have a shortlist of vetted {who} to you in 48 hours.\n\n"
            f"Worth a look?")
    else:  # before_post: no role named, offer profiles for when the need shows up
        subj, body = f"{who} for {co}", (
            f"Hi {first}, saw {co} {fact}. Teams at that stage usually open {SEATS.get(b, 'new')} seats soon after. "
            f"We keep vetted {who} who work US hours ready to start within a week, on a flat monthly fee.\n\n"
            f"Want a few profiles on file for when the need shows up?")
    cost = (f"For context: a {b} hire through us is around ${rate:,}/month all in, vs a US salary plus "
            f"benefits and a 20% agency fee." if rate else "Happy to share a cost comparison for the role.")
    return [
        (0, 0, "email", subj, body),
        (1, 2, "linkedin", "", f"Hi {first}, sent you a note about {who} for {co}. Happy to connect."),
        (2, 3, "email", f"re: {subj}", f"Hi {first}, three anonymised profiles that match what you're hiring for: "
                                        f"[PROFILE 1] [PROFILE 2] [PROFILE 3]. Want intros to any of them?"),
        (3, 7, "email", f"re: {subj}", f"Hi {first}, {cost} Worth a 20 minute scoping call?"),
        (4, 12, "email", f"re: {subj}", f"Hi {first}, I'll stop here. Want profiles next time you open a role?"),
    ]


def lint(text, step, private_details, company=""):
    problems = []
    if company:  # "Applied Compute" is a company name, not a leak
        text = re.sub(re.escape(company), "COMPANY", text, flags=re.I)
    if FORBIDDEN.search(text):
        problems.append(f"forbidden word: {FORBIDDEN.search(text).group(0)}")
    for d in private_details:  # nothing derived from applications may appear verbatim
        if d and d.lower() in text.lower():
            problems.append("contains private signal text")
    if step == 0:
        if len(text.split()) > 90:
            problems.append(f"{len(text.split())} words (>90)")
        if URL.search(text):
            problems.append("link in first email")
    return problems


def run(con, as_of=None):
    con.execute("DELETE FROM drafts")
    bench = {r["role_bucket"]: dict(r) for r in con.execute("SELECT * FROM bench")}
    private = [r["detail"] for r in con.execute(
        "SELECT detail FROM company_signals WHERE signal IN ('offshore_now','vendor','team_exits','spike')")]
    n, blocked = 0, 0
    for a in con.execute("SELECT * FROM accounts WHERE status='ready' ORDER BY score DESC"):
        contact = con.execute("SELECT * FROM contacts WHERE domain=? ORDER BY email IS NULL LIMIT 1", (a["domain"],)).fetchone()
        start = dt.date.fromisoformat(a["send_after"])
        for step, day, ch, subj, body in build(dict(a), dict(contact) if contact else None, bench):
            problems = lint(subj + "\n" + body, step, private, a["name"])
            blocked += bool(problems)
            send = start + dt.timedelta(days=day)
            con.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                        (a["domain"], step, day, ch, send.isoformat(), subj, body, "; ".join(problems) or "ok"))
            n += 1
    con.commit()
    return {"drafts": n, "blocked_by_lint": blocked}
