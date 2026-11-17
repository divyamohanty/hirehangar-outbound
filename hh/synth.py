"""SYNTHETIC applications for the demo. Every person and every employer here is invented
(employer domains end in .example). Real applications come from the ATS export instead
(`hh parse --dir <folder of resumes>`)."""
import datetime as dt
import json
import random

from .config import PRIVATE

FIRST = ["Ana", "Thabo", "Nour", "Lucia", "Mateo", "Ayesha", "Kofi", "Priya", "Juan", "Sara", "Omar", "Lina",
         "Diego", "Zanele", "Youssef", "Camila", "Ravi", "Mona", "Pedro", "Grace"]
LAST = ["Diaz", "Nkosi", "Hassan", "Gomez", "Perez", "Khan", "Mensah", "Rao", "Silva", "Ali", "Fernandez", "Mokoena"]
COUNTRIES = [("South Africa", "Africa/Johannesburg"), ("Egypt", "Africa/Cairo"), ("Argentina", "America/Buenos_Aires"),
             ("Mexico", "America/Mexico_City"), ("Philippines", "Asia/Manila"), ("Colombia", "America/Bogota"),
             ("United States", "America/Chicago")]

# Fictional US employers, each built to show one signal from slide 5.
EMPLOYERS = [
    # name, domain, headcount, scenario
    ("Brightloop", "brightloop.example", 40, "team_exits"),      # 4 SDRs from one team in 30 days
    ("Ledgerly", "ledgerly.example", 18, "offshore_now"),        # employs remote LATAM/Africa people today
    ("Fernway Health", "fernway.example", 120, "vendor"),        # contractor via Deel
    ("Quillstack", "quillstack.example", 85, "spike"),           # 9 applicants in one week -> layoffs
    ("Northpine", "northpine.example", 60, "team_exits_small"),  # only 2 -> below privacy threshold, must NOT fire
    ("Corvid Labs", "corvid.example", 30, "offshore_now"),
    ("Tessellate", "tessellate.example", 900, "team_exits"),     # too big -> fails ICP even with signal
]
ROLES = {
    "GTM": ["SDR", "Account Executive", "BDR"],
    "Marketing": ["Content Marketer", "SEO Specialist", "Growth Marketer"],
    "Ops": ["Operations Associate", "Executive Assistant", "Customer Support Lead"],
    "Engineering": ["Backend Engineer", "QA Engineer", "DevOps Engineer"],
}


def _resume(rng, name, country, tz, employer, domain, title, team, remote_us, vendor, notice, rate, stack):
    lines = [
        f"Name: {name}",
        f"Email: {name.lower().replace(' ', '.')}{rng.randint(10, 9999)}@mail.example",
        f"Location: {country}",
        "",
        "EXPERIENCE",
        f"{title}, {employer} ({domain}) | {team} team | {'Remote' if remote_us else 'On-site'} | 2023 - Present",
    ]
    if vendor:
        lines.append(f"  Contractor via {vendor}")
    lines += [
        f"  Worked {'US hours' if remote_us else 'local hours'}; stack: {stack}",
        "",
        f"Notice period: {notice} weeks",
        f"Expected monthly rate (USD): {rate}",
    ]
    return "\n".join(lines)


def generate(as_of, n_background=60, seed=7):
    rng = random.Random(seed)
    out = PRIVATE / "resumes"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.txt"):
        f.unlink()
    meta = []

    def emit(employer, domain, bucket, days_ago, country=None, remote_us=None, vendor=None, team=None):
        c, tz = country or rng.choice(COUNTRIES)
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        title = rng.choice(ROLES[bucket])
        stack = {"GTM": "HubSpot, Apollo, Gong", "Marketing": "Webflow, Ahrefs, HubSpot",
                 "Ops": "Notion, Zapier, QuickBooks", "Engineering": "Python, Postgres, AWS"}[bucket]
        remote = remote_us if remote_us is not None else (c != "United States")
        text = _resume(rng, name, c, tz, employer, domain, title, team or bucket, remote, vendor,
                       rng.choice([2, 4, 4, 6]), rng.choice([1600, 2000, 2400, 2800, 3500]), stack)
        received = (as_of - dt.timedelta(days=days_ago)).isoformat()
        i = len(meta)
        (out / f"app_{i:04d}.txt").write_text(f"Received: {received}\n" + text)
        meta.append(i)

    for name, domain, _, sc in EMPLOYERS:
        if sc == "team_exits":
            for d in (3, 9, 14, 22):
                emit(name, domain, "GTM", d, country=("United States", "America/Chicago"), remote_us=False, team="Sales Development")
        elif sc == "team_exits_small":
            for d in (5, 12):
                emit(name, domain, "GTM", d, country=("United States", "America/Chicago"), remote_us=False, team="Sales Development")
        elif sc == "offshore_now":
            emit(name, domain, "Ops", 6, country=("South Africa", "Africa/Johannesburg"), remote_us=True)
            emit(name, domain, "Marketing", 11, country=("Argentina", "America/Buenos_Aires"), remote_us=True)
        elif sc == "vendor":
            emit(name, domain, "Engineering", 4, country=("Mexico", "America/Mexico_City"), remote_us=True, vendor="Deel")
        elif sc == "spike":
            for _ in range(9):
                emit(name, domain, rng.choice(["GTM", "Marketing", "Engineering"]), rng.randint(1, 6))
    # background noise + the bench (people we could place): applicants with no special signal
    for _ in range(n_background):
        b = rng.choice(list(ROLES))
        emit("Freelance", "", b, rng.randint(0, 29))
    # a repeat applicant (same person twice) to show dedupe
    first = (out / "app_0000.txt").read_text()
    (out / f"app_{len(meta):04d}.txt").write_text(first)
    return len(meta) + 1


DEMO_COMPANIES = [(n, d, h) for n, d, h, _ in EMPLOYERS]

# Public facts for the fictional employers (in real life: Parallel Monitor / Exa / treg web search).
DEMO_PUBLIC_FACTS = [
    ("brightloop.example", "job_post", "posted a remote SDR role this week", "https://brightloop.example/careers"),
    ("ledgerly.example", "funding", "announced a Seed round", "https://news.example/ledgerly-seed"),
    ("fernway.example", "new_leader", "hired a new VP Engineering", "https://news.example/fernway-vpe"),
    # corvid.example deliberately has NO public fact -> must be held, not emailed
]


def write_demo_public(con):
    for n, d, h in DEMO_COMPANIES:
        con.execute("INSERT OR REPLACE INTO companies (domain,name,hq_country,headcount) VALUES (?,?,?,?)",
                    (d, n, "US", h))
    for d, kind, fact, url in DEMO_PUBLIC_FACTS:
        con.execute("INSERT OR REPLACE INTO public_facts VALUES (?,?,?,?,?)", (d, kind, fact, url, None))
    con.commit()


if __name__ == "__main__":
    print(json.dumps(generate(dt.date.today())))
