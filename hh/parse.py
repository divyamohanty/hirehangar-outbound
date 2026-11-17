"""Private layer: resume -> one fixed JSON per application.

  1. Text: plain .txt as-is; PDFs/DOCX through Docling (open source, `pip install docling`)
     if installed. Scans and odd layouts (the messy 5-10%) are where you'd pay Reducto/Extend.
  2. Fields: a small LLM with a fixed JSON format (Anthropic, or any OpenAI-compatible server
     such as a local Ollama for $0), or the free rules parser.
  3. PII is dropped here. Name/email become a salted hash used only to drop repeat applicants.
"""
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from . import classify, config

FIELDS = ["received_at", "employer_name", "employer_domain", "team", "title", "applicant_country",
          "remote_for_us_company", "vendor", "notice_weeks", "monthly_rate_usd", "stack"]

PROMPT = """Extract these fields from the resume as JSON with exactly these keys:
received_at (YYYY-MM-DD or null), employer_name (CURRENT employer), employer_domain (or null),
team, title (current), applicant_country, remote_for_us_company (true if they currently work
remotely for a US-based company), vendor (EOR/agency they are contracted through, e.g. Deel,
Remote.com, an agency name, else null), notice_weeks (int or null), monthly_rate_usd (int or null),
stack (comma separated tools). Do NOT include the person's name, email, phone or address.
Return only JSON.

RESUME:
"""

SALT = os.getenv("HH_HASH_SALT", "change-me-in-.env")


def to_text(path):
    p = Path(path)
    if p.suffix.lower() in (".txt", ".md"):
        return p.read_text(errors="ignore")
    try:
        from docling.document_converter import DocumentConverter  # optional dependency
    except ImportError:
        raise RuntimeError(f"{p.name}: install docling to parse {p.suffix} files (pip install docling)")
    return DocumentConverter().convert(str(p)).document.export_to_markdown()


def _identity_hash(text):
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    key = (m.group(0) if m else text[:80]).lower()
    return hashlib.sha256((SALT + key).encode()).hexdigest()[:16]


def parse_rules(text):
    g = lambda pat: (re.search(pat, text, re.I | re.M) or [None, None])[1]
    exp = re.search(r"^(.+?), (.+?)(?: \(([^)]*)\))? \| (.+?) team \| (Remote|On-site)", text, re.M)
    out = dict(
        received_at=g(r"^Received: (\S+)"),
        applicant_country=g(r"^Location: (.+)$"),
        vendor=g(r"Contractor via (.+)$"),
        notice_weeks=int(g(r"Notice period: (\d+)") or 0) or None,
        monthly_rate_usd=int(g(r"monthly rate \(USD\): (\d+)") or 0) or None,
        stack=g(r"stack: (.+)$"),
    )
    if exp:
        title, emp, dom, team, mode = exp.groups()
        out.update(title=title.strip(), employer_name=emp.strip(), employer_domain=(dom or None), team=team.strip(),
                   remote_for_us_company=(mode == "Remote" and bool(dom) and emp != "Freelance"))
    return out


def _post(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _json_from(s):
    s = s[s.find("{"): s.rfind("}") + 1]
    return json.loads(s)


def parse_llm(text):
    if config.LLM_PROVIDER == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("HH_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
        r = _post("https://api.anthropic.com/v1/messages",
                  {"model": config.ANTHROPIC_MODEL, "max_tokens": 600,
                   "messages": [{"role": "user", "content": PROMPT + text}]},
                  {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"})
        return _json_from(r["content"][0]["text"])
    r = _post(config.OPENAI_BASE_URL.rstrip("/") + "/chat/completions",
              {"model": config.OPENAI_MODEL, "messages": [{"role": "user", "content": PROMPT + text}],
               "response_format": {"type": "json_object"}},
              {"authorization": f"Bearer {config.OPENAI_API_KEY}"})
    return _json_from(r["choices"][0]["message"]["content"])


def parse_one(path):
    text = to_text(path)
    fields = parse_rules(text) if config.LLM_PROVIDER == "rules" else parse_llm(text)
    if fields.get("received_at") is None:
        fields["received_at"] = parse_rules(text).get("received_at")
    fields = {k: fields.get(k) for k in FIELDS}
    fields["role_bucket"] = classify.bucket(fields.get("title") or "")
    fields["applicant_hash"] = _identity_hash(text)
    return fields


def ingest_dir(con, folder):
    files = sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith("."))
    seen, kept, dupes, errors = set(), 0, 0, 0
    for p in files:
        try:
            f = parse_one(p)
        except Exception as e:  # keep going; log the file, never the content
            print(f"  ! {p.name}: {e}")
            errors += 1
            continue
        key = (f["applicant_hash"], f.get("employer_domain"))
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        con.execute(
            """INSERT OR REPLACE INTO applications (id,applicant_hash,received_at,employer_name,employer_domain,team,
               role_bucket,seniority,applicant_country,remote_for_us_company,vendor,notice_weeks,monthly_rate_usd,stack,tz)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p.stem, f["applicant_hash"], f["received_at"], f["employer_name"], f["employer_domain"], f["team"],
             f["role_bucket"], None, f["applicant_country"], int(bool(f["remote_for_us_company"])), f["vendor"],
             f["notice_weeks"], f["monthly_rate_usd"], f["stack"], None),
        )
        kept += 1
    con.commit()
    return {"files": len(files), "kept": kept, "repeat_applicants_dropped": dupes, "errors": errors}
