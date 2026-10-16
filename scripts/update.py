"""Builds profile cards (SVG) and refreshes generated README sections.

Runs in GitHub Actions with GITHUB_TOKEN. No third-party services.
"""
import datetime as dt
import html
import json
import os
import re
import urllib.request

LOGIN = "l7v0l"
TOKEN = os.environ["GITHUB_TOKEN"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      nodes {
        name description url homepageUrl stargazerCount forkCount pushedAt
        defaultBranchRef { target { ... on Commit { history(first: 1) { nodes { messageHeadline committedDate } } } } }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
    contributionsCollection {
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      restrictedContributionsCount
    }
  }
}
"""

QUOTES = [
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Code is like humor. When you have to explain it, it's bad.", "Cory House"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("Any fool can write code a computer can understand.", "Martin Fowler"),
    ("Programs must be written for people to read.", "Harold Abelson"),
]


def gql():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]["user"]


def esc(s):
    return html.escape(str(s), quote=True)


def ago(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    d = (dt.datetime.now(dt.timezone.utc) - t).days
    if d < 1:
        return "today"
    if d < 30:
        return f"{d}d ago"
    if d < 365:
        return f"{d // 30}mo ago"
    return f"{d // 365}y ago"


CSS = (
    "<style>text{font-family:'Segoe UI',Ubuntu,Arial,sans-serif}"
    ".t{font-size:18px;font-weight:600;fill:#58a6ff}"
    ".l{font-size:13px;fill:#8b949e}.v{font-size:14px;font-weight:600;fill:#c9d1d9}"
    ".b{font-size:13px;fill:#c9d1d9}</style>"
)


def card(w, h, inner):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'{CSS}<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="10" fill="#0d1117" stroke="#30363d"/>'
        f"{inner}</svg>"
    )


def stats_svg(u, repos):
    cc = u["contributionsCollection"]
    commits = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    rows = [
        ("Public repos", len(repos)),
        ("Total stars", sum(r["stargazerCount"] for r in repos)),
        ("Commits (last year)", commits),
        ("Pull requests", cc["totalPullRequestContributions"]),
        ("Issues", cc["totalIssueContributions"]),
        ("Followers", u["followers"]["totalCount"]),
    ]
    out = f'<text x="24" y="34" class="t">{LOGIN} · GitHub stats</text>'
    for i, (k, v) in enumerate(rows):
        y = 66 + i * 26
        out += f'<text x="24" y="{y}" class="l">{esc(k)}</text><text x="396" y="{y}" class="v" text-anchor="end">{v:,}</text>'
    return card(420, 66 + len(rows) * 26 + 6, out)


def langs_svg(repos):
    total, colors = {}, {}
    for r in repos:
        if r["name"] == LOGIN:
            continue
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            total[n] = total.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or "#8b949e"
    top = sorted(total.items(), key=lambda x: -x[1])[:6]
    s = sum(total.values()) or 1
    out = '<text x="24" y="34" class="t">Top languages</text>'
    out += '<clipPath id="c"><rect x="24" y="48" width="372" height="10" rx="5"/></clipPath><g clip-path="url(#c)">'
    x = 24.0
    for n, v in top:
        w = 372 * v / s
        out += f'<rect x="{x:.1f}" y="48" width="{w:.1f}" height="10" fill="{colors[n]}"/>'
        x += w
    out += "</g>"
    for i, (n, v) in enumerate(top):
        col, row = i % 2, i // 2
        px, py = 24 + col * 190, 86 + row * 24
        out += (
            f'<circle cx="{px + 5}" cy="{py - 4}" r="5" fill="{colors[n]}"/>'
            f'<text x="{px + 18}" y="{py}" class="b">{esc(n)} <tspan class="l">{100 * v / s:.1f}%</tspan></text>'
        )
    return card(420, 86 + ((len(top) + 1) // 2) * 24 + 4, out)


def replace(text, key, body):
    pat = re.compile(rf"(<!--{key}:START-->).*?(<!--{key}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


def main():
    u = gql()
    repos = u["repositories"]["nodes"]
    work = sorted((r for r in repos if r["name"] != LOGIN), key=lambda r: r["pushedAt"], reverse=True)

    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "assets", "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(u, repos))
    with open(os.path.join(ROOT, "assets", "langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(repos))

    now = ["| Project | Last commit | When |", "|:--|:--|:--|"]
    for r in work[:4]:
        nodes = ((r.get("defaultBranchRef") or {}).get("target") or {}).get("history", {}).get("nodes") or []
        msg = (nodes[0]["messageHeadline"] if nodes else "-").replace("|", "\\|")
        now.append(f"| [**{r['name']}**]({r['url']}) | {msg} | {ago(r['pushedAt'])} |")
    now_md = "\n".join(now)

    day = dt.date.today().timetuple().tm_yday
    q, a = QUOTES[day % len(QUOTES)]
    quote_md = f"> _{q}_ — **{a}**"
    stamp = f"<sub>Auto-updated {dt.date.today().isoformat()}</sub>"

    for name in ("README.md", "README.ar.md"):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        t = open(p, encoding="utf-8").read()
        t = replace(t, "NOW", now_md)
        t = replace(t, "QUOTE", quote_md)
        t = replace(t, "STAMP", stamp)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(t)


if __name__ == "__main__":
    main()
