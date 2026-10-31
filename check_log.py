"""Check a web server access log against AI operators' declared egress ranges.

This is the daily check a website or national CERT would run under the proposed Declared Egress
Standard. For each request it finds the declared list (operator and purpose) that the source address
belongs to, and raises three kinds of flag:

  RESEARCH-RANGE        a request from a range declared for research, training or evaluation runs
  WRITE-FROM-DECLARED   a request that writes (POST, PUT, PATCH, DELETE, or an editing GET) from a declared
                        range: normal for some user-directed agents, never for crawlers
  CLAIMED-NOT-DECLARED  a user agent that names an operator's bot, from outside all of that operator's
                        declared ranges: spoofed, or the operator's lists are incomplete

  python check_log.py demo/access_log.txt
  python check_log.py demo/access_log.txt --extra demo/research_registry.json

Declared ranges come from results/prefixes.csv (written by scorecard.py). --extra adds registry files in the
format proposed in Appendix A3 of the proposal. Log lines must be in the common or combined log format.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import ipaddress
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) \S+(?: "[^"]*" "([^"]*)")?')
WRITE_GET = re.compile(r"[?&](action=(edit|save|submit)|save=|edit=)", re.I)
RESEARCH = re.compile(r"research|evaluation", re.I)
BOT_TOKENS = {
    "OpenAI": ["gptbot", "oai-searchbot", "chatgpt-user", "oai-adsbot"],
    "Anthropic": ["claudebot", "claude-user", "claude-searchbot"],
    "Google": ["googlebot", "google-agent", "googleother"],
    "Microsoft": ["bingbot"], "Apple": ["applebot"],
    "Perplexity": ["perplexitybot", "perplexity-user"], "Mistral": ["mistralai-user", "mistralai-index"],
    "Common Crawl": ["ccbot"], "DuckDuckGo": ["duckassistbot"],
}


class Declared:
    """Every declared range, searchable by address (ranges may overlap, so a lookup returns all hits)."""

    def __init__(self) -> None:
        self.ranges: dict[int, list[tuple]] = {4: [], 6: []}
        self.index: dict[int, tuple[list[int], int]] = {}

    def add(self, prefix: str, operator: str, name: str, purpose: str) -> None:
        n = ipaddress.ip_network(prefix, strict=False)
        self.ranges[n.version].append((int(n.network_address), int(n.broadcast_address), operator, name, purpose))

    def finish(self) -> None:
        for v, rs in self.ranges.items():
            rs.sort()
            self.index[v] = ([r[0] for r in rs], max((r[1] - r[0] for r in rs), default=0))

    def lookup(self, ip: str) -> list[tuple[str, str, str]]:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return []
        starts, span = self.index[a.version]
        rs, x, hits = self.ranges[a.version], int(a), []
        j = bisect.bisect_right(starts, x) - 1
        while j >= 0 and starts[j] >= x - span:
            if rs[j][0] <= x <= rs[j][1]:
                hits.append(rs[j][2:])
            j -= 1
        return hits


def load(extra: list[str]) -> Declared:
    d = Declared()
    purposes = {(r["operator"], r["list"]): r["purpose"]
                for r in csv.DictReader(open(ROOT / "results" / "scorecard.csv", encoding="utf-8"))}
    for p in csv.DictReader(open(ROOT / "results" / "prefixes.csv", encoding="utf-8")):
        d.add(p["prefix"], p["operator"], p["list"], purposes.get((p["operator"], p["list"]), ""))
    for path in extra:
        reg = json.loads(Path(path).read_text(encoding="utf-8"))
        for pfx in reg.get("prefixes", []):
            d.add(pfx.get("ipv4Prefix") or pfx.get("ipv6Prefix"), reg["provider"],
                  f"declared {reg['purpose']} range", reg["purpose"])
    d.finish()
    return d


def check(line: str, declared: Declared) -> dict | None:
    m = LOG_LINE.match(line)
    if not m:
        return None
    ip, when, method, path, status, ua = m.groups()
    ua_low = (ua or "").lower()
    hits = declared.lookup(ip)
    write = method.upper() in ("POST", "PUT", "PATCH", "DELETE") or (method.upper() == "GET" and WRITE_GET.search(path))
    flags, advice = [], ""
    if any(RESEARCH.search(h[2]) for h in hits):
        flags.append("RESEARCH-RANGE")
        advice = ("report to the provider and CERT-Bund within 24 hours" if write
                  else "research agents have no reason to be here: note it and watch")
    if hits and write:
        flags.append("WRITE-FROM-DECLARED")
        if not advice:
            crawler = all("crawler" in h[2] for h in hits)
            advice = ("a crawler should never write: report to the operator" if crawler
                      else "may act for a user: check the account and content")
    for op, tokens in BOT_TOKENS.items():
        if any(t in ua_low for t in tokens) and not any(h[0] == op for h in hits):
            flags.append("CLAIMED-NOT-DECLARED")
            advice = advice or f"claims to be {op} but is not from its declared addresses: treat as spoofed"
    who = "; ".join(f"{h[0]} {h[1]}" for h in hits) or "not declared"
    return {"time": when.split(" ")[0], "ip": ip, "request": f"{method} {path}"[:60], "declared_as": who,
            "flags": " + ".join(flags), "advice": advice}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", help="access log in common or combined log format")
    ap.add_argument("--extra", action="append", default=[], help="extra registry file (proposed format)")
    ap.add_argument("--out", help="also write the report to this file")
    args = ap.parse_args()
    declared = load(args.extra)
    rows = [r for line in open(args.log, encoding="utf-8") if (r := check(line.strip(), declared))]
    flagged = [r for r in rows if r["flags"]]
    lines = [f"Checked {len(rows)} requests against {sum(len(v) for v in declared.ranges.values())} declared ranges. "
             f"Flagged: {len(flagged)}.", ""]
    for r in rows:
        mark = "FLAG" if r["flags"] else "ok  "
        lines.append(f"{mark} {r['time']}  {r['ip']:<15} {r['request']}")
        lines.append(f"     declared as: {r['declared_as']}")
        if r["flags"]:
            lines.append(f"     {r['flags']}: {r['advice']}")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
