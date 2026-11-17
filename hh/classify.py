"""Cheap, deterministic classifiers. In production a small LLM classifies from the job
description; keywords are the free fallback and are good enough to rank accounts."""
import re

BUCKETS = [
    # order matters: "Engineering Manager, Growth" must land in Engineering, not Marketing
    ("Engineering", r"engineer|developer|devops|\bsre\b|\bqa\b|data scien|machine learning|\bml\b|full[- ]?stack|backend|front[- ]?end|architect"),
    ("GTM", r"account executive|\bae\b|\bsdr\b|\bbdr\b|sales|business development|account manager|customer success|revenue|partnership|solutions consultant"),
    ("Marketing", r"marketing|content|\bseo\b|brand|demand gen|growth|social media|copywrit|\bpmm\b|communications|lifecycle"),
    ("Ops", r"operations|\bops\b|support|finance|accountant|bookkeep|recruit|executive assistant|admin|payroll|\bhr\b|people"),
]

US_STATES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|"
    "illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    "mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|"
    "north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|"
    "utah|vermont|virginia|washington|west virginia|wisconsin|wyoming"
)
US_RE = re.compile(
    r"united states|\busa\b|\bu\.s\.|\bus\b|\bnyc\b|san francisco|los angeles|boston|chicago|seattle|austin|"
    r"denver|atlanta|miami|\b(?:" + US_STATES + r")\b|,\s?(?:ca|ny|tx|wa|ma|co|il|fl|ga|nc|va|pa|nj|ut|or|az)\b",
    re.I,
)
OFFSHORE = [
    "philippines", "india", "mexico", "argentina", "brazil", "colombia", "south africa", "egypt", "pakistan",
    "nigeria", "kenya", "latam", "latin america", "poland", "ukraine", "vietnam", "costa rica", "peru", "chile",
]
NON_US_ONLY = re.compile(r"united kingdom|\buk\b|london|germany|berlin|france|paris|denmark|netherlands|ireland|canada|toronto|australia", re.I)
STAFFING = re.compile(r"staffing|recruit|talent|outsourc|\bbpo\b|virtual assistant|hire|jobs\b|placement|pavago", re.I)


def bucket(title):
    t = (title or "").lower()
    for name, pat in BUCKETS:
        if re.search(pat, t):
            return name
    return None


def location_flags(location, remote_hint=""):
    """-> (is_us, is_remote, offshore_country_or_None)"""
    loc = f"{location or ''} {remote_hint or ''}"
    low = loc.lower()
    offshore = next((c for c in OFFSHORE if c in low), None)
    is_remote = "remote" in low or "anywhere" in low or str(remote_hint).lower() in ("yes", "true", "remote")
    is_us = bool(US_RE.search(loc)) or (is_remote and not offshore and not NON_US_ONLY.search(loc))
    return is_us, is_remote, offshore


def looks_like_staffing(name, domain=""):
    return bool(STAFFING.search(f"{name} {domain}"))
