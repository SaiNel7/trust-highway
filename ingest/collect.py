#!/usr/bin/env python3
"""Collect Red Hat GitHub repos, contributors and profiles into SQLite.

Usage:
    export GITHUB_TOKEN=ghp_...
    python collect.py --max-repos-per-org 40
Re-running resumes: repos and users already stored are skipped.
"""
import argparse
import json
import os
import sqlite3
import sys
import time

import requests

API = "https://api.github.com"
DEFAULT_ORGS = [
    "redhat-developer", "openshift", "RedHatOfficial", "redhat-cop",
    "ansible", "containers", "instructlab", "operator-framework",
    "kubevirt", "redhat-openshift-ecosystem", "opendatahub-io",
    "Red-Hat-AI-Innovation-Team", "quarkusio", "keycloak", "patternfly",
    "RedHat-Storage", "ceph", "cockpit-project", "osbuild",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos(
  full_name TEXT PRIMARY KEY, org TEXT, description TEXT, language TEXT,
  topics TEXT, stars INTEGER, langs TEXT, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contributions(
  login TEXT, repo TEXT, n INTEGER, PRIMARY KEY(login, repo));
CREATE TABLE IF NOT EXISTS users(
  login TEXT PRIMARY KEY, name TEXT, company TEXT, location TEXT,
  bio TEXT, blog TEXT, email TEXT, html_url TEXT);
"""


def make_session():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN first (a classic or fine-grained read-only token).")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return s


def get(s, url, params=None):
    """GET with rate-limit handling. Returns (json_or_None, response)."""
    while True:
        r = s.get(url, params=params, timeout=30)
        if r.status_code in (403, 429) and (
            r.headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in r.headers
        ):
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = int(r.headers.get("Retry-After", max(reset - time.time(), 1) + 2))
            print(f"  rate limited, sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code in (403, 404, 409, 451):
            # 403 here (not rate limited) = e.g. "contributor list is too large" on huge repos
            if r.status_code == 403:
                print(f"  skipped {url}: {r.text[:100]}", flush=True)
            return None, r
        if r.status_code == 204:  # empty repo
            return None, r
        r.raise_for_status()
        return r.json(), r


def paginate(s, url, params=None, max_pages=10):
    params = dict(params or {}, per_page=100)
    out = []
    for _ in range(max_pages):
        data, r = get(s, url, params)
        if not data:
            break
        out.extend(data)
        nxt = r.links.get("next")
        if not nxt:
            break
        url, params = nxt["url"], None
    return out


def collect_repos(s, db, org, limit, min_stars):
    repos = paginate(
        s, f"{API}/orgs/{org}/repos",
        {"type": "public", "sort": "pushed", "direction": "desc"}, max_pages=5,
    )
    repos = [r for r in repos if not r["fork"] and not r["archived"] and r["stargazers_count"] >= min_stars]
    repos = repos[:limit]
    for r in repos:
        db.execute(
            "INSERT OR IGNORE INTO repos(full_name, org, description, language, topics, stars) VALUES (?,?,?,?,?,?)",
            (r["full_name"], org, r["description"] or "", r["language"] or "",
             json.dumps(r.get("topics", [])), r["stargazers_count"]),
        )
    db.commit()
    return [r["full_name"] for r in repos]


def collect_contributors(s, db, full_name):
    if db.execute("SELECT done FROM repos WHERE full_name=?", (full_name,)).fetchone()[0]:
        return
    langs, _ = get(s, f"{API}/repos/{full_name}/languages")
    contribs = paginate(s, f"{API}/repos/{full_name}/contributors", max_pages=5)
    for c in contribs:
        if c.get("type") != "User" or c["login"].endswith("[bot]"):
            continue
        db.execute("INSERT OR REPLACE INTO contributions VALUES (?,?,?)",
                   (c["login"], full_name, c["contributions"]))
    db.execute("UPDATE repos SET langs=?, done=1 WHERE full_name=?",
               (json.dumps(langs or {}), full_name))
    db.commit()


def collect_users(s, db):
    logins = [row[0] for row in db.execute(
        "SELECT DISTINCT login FROM contributions WHERE login NOT IN (SELECT login FROM users)")]
    print(f"Fetching {len(logins)} profiles", flush=True)
    for i, login in enumerate(logins, 1):
        u, _ = get(s, f"{API}/users/{login}")
        if u:
            db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?)",
                       (login, u.get("name"), u.get("company"), u.get("location"),
                        u.get("bio"), u.get("blog"), u.get("email"), u.get("html_url")))
        if i % 50 == 0:
            db.commit()
            print(f"  {i}/{len(logins)}", flush=True)
    db.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--orgs", nargs="*", default=DEFAULT_ORGS)
    p.add_argument("--max-repos-per-org", type=int, default=40)
    p.add_argument("--min-stars", type=int, default=5)
    p.add_argument("--db", default="redhat.db")
    p.add_argument("--skip-users", action="store_true", help="skip profile lookups")
    a = p.parse_args()

    s = make_session()
    db = sqlite3.connect(a.db)
    db.executescript(SCHEMA)

    for org in a.orgs:
        print(f"[{org}]", flush=True)
        try:
            names = collect_repos(s, db, org, a.max_repos_per_org, a.min_stars)
        except requests.HTTPError as e:
            print(f"  skipped: {e}")
            continue
        for n in names:
            try:
                collect_contributors(s, db, n)
            except (requests.RequestException, ValueError) as e:
                print(f"  skipped {n}: {e}", flush=True)
        print(f"  {len(names)} repos done", flush=True)

    if not a.skip_users:
        collect_users(s, db)
    print("Done. Next: python skills.py")


if __name__ == "__main__":
    main()