#!/usr/bin/env python3
"""Fetch people profiles fast: 100 people per GitHub GraphQL call.

Takes every contributor login already in redhat.db that has no profile yet,
fetches name/company/location/bio/email/website, saves to the users table,
then writes the Boston/MA people to boston_people.csv.

GraphQL has its own rate limit (separate from the REST one collect.py hit),
so this runs even while collect.py is sleeping.

Usage:
    export GITHUB_TOKEN=...
    python fetch.py
    python fetch.py --redhat-only     # CSV keeps only people whose profile mentions Red Hat
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

GRAPHQL = "https://api.github.com/graphql"
BATCH = 100
FIELDS = "login name company location bio email websiteUrl url"

BOSTON = re.compile(r"\bboston\b|massachusetts", re.I)
MA = re.compile(r"\bMA\b|\bMass\.?(?=$|[\s,])")  # case-sensitive: skips Madrid, Malaysia


def in_boston_ma(loc):
    loc = loc or ""
    return bool(BOSTON.search(loc) or MA.search(loc))


def red_hat(company, bio, email):
    t = f"{company or ''} {bio or ''}".lower()
    return "red hat" in t or "redhat" in t or (email or "").lower().endswith("@redhat.com")


def run_query(s, logins):
    parts = [f"u{i}: user(login: {json.dumps(l)}) {{ {FIELDS} }}" for i, l in enumerate(logins)]
    q = "query { rateLimit { remaining resetAt } " + " ".join(parts) + " }"
    while True:
        r = s.post(GRAPHQL, json={"query": q}, timeout=60)
        body = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
        limited = r.status_code in (403, 429) or any(
            e.get("type") == "RATE_LIMITED" for e in body.get("errors", []) or [])
        if limited:
            reset = r.headers.get("X-RateLimit-Reset")
            wait = int(reset) - time.time() + 2 if reset else 60
            print(f"  GraphQL rate limited, sleeping {int(max(wait, 5))}s", flush=True)
            time.sleep(max(wait, 5))
            continue
        if r.status_code >= 500:
            time.sleep(5)
            continue
        r.raise_for_status()
        return body  # partial data is normal: renamed/deleted users come back null


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="redhat.db")
    ap.add_argument("--redhat-only", action="store_true")
    a = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or sys.exit("Set GITHUB_TOKEN first.")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})

    db = sqlite3.connect(a.db)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          login TEXT PRIMARY KEY, name TEXT, company TEXT, location TEXT,
          bio TEXT, blog TEXT, email TEXT, html_url TEXT);
        CREATE TABLE IF NOT EXISTS missing(login TEXT PRIMARY KEY);
    """)
    todo = [r[0] for r in db.execute("""
        SELECT DISTINCT login FROM contributions
        WHERE login NOT IN (SELECT login FROM users) AND login NOT IN (SELECT login FROM missing)""")]
    print(f"{len(todo)} people to fetch ({(len(todo) + BATCH - 1) // BATCH} calls)", flush=True)

    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        data = (run_query(s, batch).get("data") or {})
        for j, login in enumerate(batch):
            u = data.get(f"u{j}")
            if not u:
                db.execute("INSERT OR IGNORE INTO missing VALUES (?)", (login,))
                continue
            db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?)",
                       (login, u["name"], u["company"], u["location"], u["bio"],
                        u["websiteUrl"], u["email"] or None, u["url"]))
        db.commit()
        left = (data.get("rateLimit") or {}).get("remaining", "?")
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}  (GraphQL points left: {left})", flush=True)

    # Boston / MA people
    rows = db.execute("""
        SELECT u.login, u.name, u.company, u.location, u.bio, u.email, u.blog, u.html_url,
               COUNT(c.repo), SUM(c.n)
        FROM users u JOIN contributions c ON c.login = u.login GROUP BY u.login""").fetchall()
    people = []
    for login, name, company, loc, bio, email, blog, url, repos, commits in rows:
        if not in_boston_ma(loc):
            continue
        rh = red_hat(company, bio, email)
        if a.redhat_only and not rh:
            continue
        people.append({"login": login, "name": name, "company": company, "location": loc,
                       "bio": bio, "email": email, "blog": blog, "url": url,
                       "says_red_hat": rh, "red_hat_repos": repos, "commits": commits})
    people.sort(key=lambda p: (not p["says_red_hat"], -(p["commits"] or 0)))

    cols = ["login", "name", "company", "location", "bio", "email", "blog", "url",
            "says_red_hat", "red_hat_repos", "commits"]
    with open("boston_people.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(people)

    total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"\n{total} profiles in db. {len(people)} in Boston/MA "
          f"({sum(p['says_red_hat'] for p in people)} say Red Hat) -> boston_people.csv")
    print(f"done {datetime.now(timezone.utc):%H:%M UTC}")


if __name__ == "__main__":
    main()