"""Storage. SQLite locally so it runs anywhere for $0; the schema is plain SQL and moves to
Postgres unchanged (swap the connection). Two zones:

  private zone : applications  (company-level facts parsed from resumes, no names/emails)
  public zone  : job_posts, public_facts  (the only things an email may cite)
"""
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  domain TEXT PRIMARY KEY, name TEXT, hq_country TEXT, headcount INTEGER,
  stage TEXT, is_staffing INTEGER DEFAULT 0, tz TEXT DEFAULT 'America/New_York'
);

-- PRIVATE ZONE. One row per application. applicant_hash is a salted hash so repeat
-- applicants can be dropped; the raw resume never enters this table.
CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY, applicant_hash TEXT, received_at TEXT,
  employer_name TEXT, employer_domain TEXT, team TEXT, role_bucket TEXT, seniority TEXT,
  applicant_country TEXT, remote_for_us_company INTEGER, vendor TEXT,
  notice_weeks INTEGER, monthly_rate_usd INTEGER, stack TEXT, tz TEXT
);

-- PUBLIC ZONE.
CREATE TABLE IF NOT EXISTS job_posts (
  id TEXT PRIMARY KEY, domain TEXT, company TEXT, title TEXT, bucket TEXT,
  location TEXT, remote TEXT, offshore_location TEXT, source TEXT, url TEXT,
  posted_at TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS public_facts (
  domain TEXT, kind TEXT, fact TEXT, source_url TEXT, seen_at TEXT,
  PRIMARY KEY (domain, kind, fact)
);

-- DERIVED. Company-level only.
CREATE TABLE IF NOT EXISTS company_signals (
  domain TEXT, signal TEXT, strength REAL, detail TEXT, computed_at TEXT,
  PRIMARY KEY (domain, signal)
);
CREATE TABLE IF NOT EXISTS bench (
  role_bucket TEXT PRIMARY KEY, available INTEGER, median_rate_usd INTEGER, top_tz TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
  domain TEXT PRIMARY KEY, name TEXT, fit REAL, timing REAL, fill REAL, score REAL,
  play TEXT, top_signal TEXT, reasons TEXT, public_fact TEXT, bucket TEXT,
  persona TEXT, send_after TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS contacts (
  domain TEXT, full_name TEXT, first_name TEXT, title TEXT, email TEXT,
  email_status TEXT, linkedin_url TEXT, source TEXT, PRIMARY KEY (domain, full_name)
);
CREATE TABLE IF NOT EXISTS drafts (
  domain TEXT, step INTEGER, day INTEGER, channel TEXT, send_at TEXT,
  subject TEXT, body TEXT, lint TEXT, PRIMARY KEY (domain, step)
);
CREATE TABLE IF NOT EXISTS signal_weights (signal TEXT PRIMARY KEY, weight REAL);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
