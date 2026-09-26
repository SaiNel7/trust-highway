#!/usr/bin/env python3
"""Infer per-engineer skill profiles from collected GitHub data.

Reads redhat.db (from collect.py), writes:
    profiles.json  full profile per engineer (skills, top repos, languages)
    profiles.csv   flat table for spreadsheets
    graph.json     nodes/edges (person, repo, skill) ready for a graph DB or force-graph UI

Scoring: each contribution to a repo adds weight log(1 + commits) to the
skills that repo signals (language mix, topics, description keywords, org).
"""
import argparse
import csv
import json
import math
import re
import sqlite3
from collections import defaultdict

# Skill area -> signals. "langs" match GitHub language names, "kw" match
# topics/description/repo name (regex, case-insensitive), "orgs" match the owner.
SKILLS = {
    "Frontend (TypeScript/JS)": {"langs": ["TypeScript", "JavaScript", "CSS", "HTML", "SCSS", "Vue"],
                                 "kw": r"\b(react|frontend|ui|patternfly|web ?console|angular|vue)\b",
                                 "orgs": ["patternfly"]},
    "Cloud / Kubernetes": {"langs": [],
                           "kw": r"\b(kubernetes|k8s|openshift|operator|helm|cloud|cluster|container orchestration|olm)\b",
                           "orgs": ["openshift", "operator-framework", "redhat-openshift-ecosystem"]},
    "Containers & Runtimes": {"langs": [],
                              "kw": r"\b(podman|buildah|skopeo|container|oci|crun|runc|quadlet)\b",
                              "orgs": ["containers"]},
    "Automation / DevOps": {"langs": ["Jinja", "Ansible"],
                            "kw": r"\b(ansible|playbook|terraform|gitops|ci/?cd|pipeline|tekton|argo|infrastructure as code)\b",
                            "orgs": ["ansible", "redhat-cop"]},
    "AI / ML": {"langs": ["Jupyter Notebook"],
                "kw": r"\b(ai|ml|machine learning|llm|model|training|inference|vllm|instructlab|granite|data science|mlops)\b",
                "orgs": ["instructlab", "opendatahub-io", "Red-Hat-AI-Innovation-Team"]},
    "Java / JVM": {"langs": ["Java", "Kotlin", "Scala", "Groovy"],
                   "kw": r"\b(java|quarkus|jvm|spring|maven|gradle)\b",
                   "orgs": ["quarkusio"]},
    "Go / Backend services": {"langs": ["Go"], "kw": r"\b(golang|microservice|grpc|rest api|backend)\b", "orgs": []},
    "Python": {"langs": ["Python"], "kw": r"\b(python|django|flask|fastapi)\b", "orgs": []},
    "Systems / Low-level (C, Rust)": {"langs": ["C", "C++", "Rust", "Assembly", "Makefile"],
                                     "kw": r"\b(kernel|systemd|driver|firmware|bootloader|libvirt|qemu|selinux)\b",
                                     "orgs": ["cockpit-project", "osbuild"]},
    "Virtualization": {"langs": [], "kw": r"\b(kubevirt|virtual machine|vm|hypervisor|libvirt|qemu|kvm)\b",
                       "orgs": ["kubevirt"]},
    "Storage": {"langs": [], "kw": r"\b(ceph|storage|rook|csi|object store|s3|block device)\b",
                "orgs": ["ceph", "RedHat-Storage"]},
    "Security / Identity": {"langs": [], "kw": r"\b(security|keycloak|oauth|oidc|sso|identity|auth|cve|vulnerability|compliance|selinux|tls)\b",
                            "orgs": ["keycloak"]},
    "Observability": {"langs": [], "kw": r"\b(prometheus|grafana|observability|monitoring|tracing|opentelemetry|logging|metrics)\b",
                      "orgs": []},
    "Linux / OS": {"langs": ["Shell"], "kw": r"\b(rhel|linux|fedora|centos|rpm|dnf|image builder|bootc|cockpit)\b",
                   "orgs": ["osbuild", "cockpit-project"]},
}
COMPILED = {k: re.compile(v["kw"], re.I) for k, v in SKILLS.items()}


def repo_signals(repo):
    """Return {skill: strength 0..1} for a repo row."""
    full, org, desc, lang, topics, langs_json = repo
    text = " ".join([full.split("/")[-1].replace("-", " "), desc or "", " ".join(json.loads(topics or "[]"))])
    langs = json.loads(langs_json or "{}")
    total = sum(langs.values()) or 1
    out = defaultdict(float)
    for skill, spec in SKILLS.items():
        s = 0.0
        share = sum(langs.get(l, 0) for l in spec["langs"]) / total
        s += share * 0.8
        if COMPILED[skill].search(text):
            s += 0.5
        if org in spec["orgs"]:
            s += 0.4
        if s > 0.15:
            out[skill] = min(s, 1.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="redhat.db")
    ap.add_argument("--min-commits", type=int, default=5, help="ignore drive-by contributors below this total")
    ap.add_argument("--redhat-only", action="store_true",
                    help="keep only profiles whose company/bio mentions Red Hat")
    ap.add_argument("--location", default="", help="filter by location substring, e.g. Boston")
    a = ap.parse_args()

    db = sqlite3.connect(a.db)
    repos = {r[0]: r for r in db.execute(
        "SELECT full_name, org, description, language, topics, langs FROM repos WHERE done=1")}
    signals = {name: repo_signals(r) for name, r in repos.items()}

    people = defaultdict(lambda: {"skills": defaultdict(float), "repos": [], "langs": defaultdict(float), "commits": 0})
    for login, repo, n in db.execute("SELECT login, repo, n FROM contributions"):
        if repo not in repos:
            continue
        p = people[login]
        w = math.log1p(n)
        p["commits"] += n
        p["repos"].append((repo, n))
        for sk, strength in signals[repo].items():
            p["skills"][sk] += w * strength
        langs = json.loads(repos[repo][5] or "{}")
        tot = sum(langs.values()) or 1
        for l, b in langs.items():
            p["langs"][l] += w * b / tot

    users = {r[0]: r for r in db.execute("SELECT login, name, company, location, bio, blog, email, html_url FROM users")}

    profiles = []
    for login, p in people.items():
        if p["commits"] < a.min_commits:
            continue
        u = users.get(login)
        name, company, location, bio, blog, email, url = (u[1:] if u else (None,) * 7)
        blob = f"{company or ''} {bio or ''}".lower()
        is_rh = "red hat" in blob or "redhat" in blob or (email or "").endswith("@redhat.com")
        if a.redhat_only and not is_rh:
            continue
        if a.location and a.location.lower() not in (location or "").lower():
            continue
        top = sorted(p["skills"].items(), key=lambda kv: -kv[1])
        best = top[0][1] if top else 1
        skills = [{"skill": k, "score": round(v / best, 2)} for k, v in top[:5] if v / best >= 0.25]
        top_langs = sorted(p["langs"].items(), key=lambda kv: -kv[1])[:4]
        profiles.append({
            "login": login, "name": name, "company": company, "location": location,
            "bio": bio, "url": url or f"https://github.com/{login}", "red_hat": is_rh,
            "total_commits": p["commits"],
            "primary_skill": skills[0]["skill"] if skills else None,
            "skills": skills,
            "languages": [l for l, _ in top_langs],
            "top_repos": [{"repo": r, "commits": n} for r, n in sorted(p["repos"], key=lambda x: -x[1])[:5]],
        })
    profiles.sort(key=lambda x: -x["total_commits"])

    with open("profiles.json", "w") as f:
        json.dump(profiles, f, indent=2)

    with open("profiles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["login", "name", "company", "location", "red_hat", "commits", "primary_skill",
                    "skills", "languages", "top_repos"])
        for p in profiles:
            w.writerow([p["login"], p["name"], p["company"], p["location"], p["red_hat"], p["total_commits"],
                        p["primary_skill"], "; ".join(s["skill"] for s in p["skills"]),
                        "; ".join(p["languages"]), "; ".join(r["repo"] for r in p["top_repos"])])

    nodes, edges, seen = [], [], set()

    def node(id_, kind, label, **kw):
        if id_ not in seen:
            seen.add(id_)
            nodes.append({"id": id_, "type": kind, "label": label, **kw})

    for p in profiles:
        pid = f"person:{p['login']}"
        node(pid, "person", p["name"] or p["login"], location=p["location"], commits=p["total_commits"],
             primary_skill=p["primary_skill"], red_hat=p["red_hat"])
        for s in p["skills"]:
            node(f"skill:{s['skill']}", "skill", s["skill"])
            edges.append({"source": pid, "target": f"skill:{s['skill']}", "type": "HAS_SKILL", "weight": s["score"]})
        for r in p["top_repos"]:
            node(f"repo:{r['repo']}", "repo", r["repo"])
            edges.append({"source": pid, "target": f"repo:{r['repo']}", "type": "CONTRIBUTED_TO", "weight": r["commits"]})
    with open("graph.json", "w") as f:
        json.dump({"nodes": nodes, "edges": edges}, f)

    by_skill = defaultdict(int)
    for p in profiles:
        if p["primary_skill"]:
            by_skill[p["primary_skill"]] += 1
    print(f"{len(profiles)} engineers profiled -> profiles.json, profiles.csv, graph.json")
    for k, v in sorted(by_skill.items(), key=lambda kv: -kv[1]):
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()