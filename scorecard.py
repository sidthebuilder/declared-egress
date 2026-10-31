"""Registry Scorecard: grade the IP range files that AI companies publish for their bots and agents.

When an AI agent misbehaves on someone's website, the site can only tell whose agent it was if the
operator has declared where its agents' traffic comes from. This script measures how far today's
declarations are from four checkable requirements (Kumar 2026, "Attestation Gaps"):

  R1 Current    the file says when it was made, and that date is at most --max-age days old (default 30)
  R2 Separate   one purpose per list, and none of its addresses appear in any other published list
  R3 Dedicated  every address is registered (RDAP) to the operator itself, not rented cloud space
  R4 Signed     the file carries a signature or points to an append-only version history

Usage
  python scorecard.py                  fetch the live files into snapshots/<UTC date>/ and score them
  python scorecard.py --retry-failed   keep the newest snapshot; fetch only failed or newly added files; score
  python scorecard.py --offline        re-score the newest snapshot; RDAP answers come from cache/rdap.json
Results go to results/. Standard library only, Python 3.11 or later.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOTS, RESULTS, CACHE = ROOT / "snapshots", ROOT / "results", ROOT / "cache"
UA = "Mozilla/5.0 (compatible; RegistryScorecard/0.1; +https://github.com/sidthebuilder)"

# Words that identify the operator itself in an RDAP registration record.
OPERATOR_KEYS = {
    "OpenAI": ["openai"], "Anthropic": ["anthropic"], "Google": ["google"],
    "Microsoft": ["microsoft", "msft"], "Apple": ["apple"], "Perplexity": ["perplexity"],
    "Mistral": ["mistral"], "Common Crawl": ["common crawl", "commoncrawl"],
    "DuckDuckGo": ["duckduckgo", "duck duck go"],
}
# Who else the address space may be registered to, for "rented from ...".
HOLDER_KEYS = [
    ("Microsoft Azure", ["microsoft", "msft"]), ("Amazon AWS", ["amazon", "aws"]),
    ("Google Cloud", ["google"]), ("Oracle Cloud", ["oracle"]), ("Cloudflare", ["cloudflare"]),
    ("Akamai/Linode", ["akamai", "linode"]), ("DigitalOcean", ["digitalocean"]),
    ("Hetzner", ["hetzner"]), ("OVH", ["ovh"]), ("Alibaba Cloud", ["alibaba", "aliyun"]),
    ("Tencent Cloud", ["tencent"]), ("Fastly", ["fastly"]),
]
SIGNATURE_KEY = re.compile(r"signature|^sig$|jws|proof|history|previous|prev_?hash|changelog", re.I)


def http_get(url: str, timeout: int = 30) -> dict:
    """GET a URL and return status, final URL, content type and body. Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "final_url": r.geturl(),
                    "type": r.headers.get("Content-Type", ""), "body": r.read()}
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        return {"status": e.code, "final_url": url,
                "type": e.headers.get("Content-Type", "") if e.headers else "", "body": body}
    except Exception as e:  # DNS failure, timeout, TLS error
        return {"status": 0, "final_url": url, "type": "", "body": b"", "error": repr(e)}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def load_sources() -> list[dict]:
    with open(ROOT / "sources.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def powershell_get(url: str, dest: Path) -> dict:
    """Windows fallback for servers whose certificate chain Python cannot complete but Windows can."""
    ps = (f"$ProgressPreference='SilentlyContinue'; (Invoke-WebRequest -UseBasicParsing -Uri '{url}' "
          f"-UserAgent '{UA}' -OutFile '{dest}' -PassThru).StatusCode")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=90)
        status = int((out.stdout.strip().splitlines() or ["0"])[-1])
    except Exception as e:
        return {"status": 0, "final_url": url, "type": "", "body": b"", "error": repr(e)}
    return {"status": status, "final_url": url, "type": "",
            "body": dest.read_bytes() if dest.exists() else b"", "via": "powershell"}


def fetch(url: str, dest: Path) -> dict:
    """Fetch one file into the snapshot and return its manifest fields."""
    r = http_get(url)
    if "CERTIFICATE_VERIFY_FAILED" in r.get("error", "") and os.name == "nt":
        r = powershell_get(url, dest)
    dest.write_bytes(r["body"])
    return {"status": r["status"], "final_url": r["final_url"], "content_type": r["type"],
            "bytes": len(r["body"]), "sha256": hashlib.sha256(r["body"]).hexdigest(),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "via": r.get("via", "python"), "error": r.get("error", "")}


def take_snapshot(sources: list[dict]) -> Path:
    """Fetch every source file; keep the raw bytes and a manifest with hashes."""
    snap = SNAPSHOTS / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snap.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in sources:
        name = slug(f"{s['operator']} {s['product']}") + ".json"
        manifest.append({**s, "file": name, **fetch(s["url"], snap / name)})
        print(f"  HTTP {manifest[-1]['status']}  {s['operator']:<13} {s['product']}")
        time.sleep(0.3)
    (snap / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return snap


def update_snapshot(snap: Path, sources: list[dict]) -> None:
    """Keep an existing snapshot: retry files that failed, and fetch sources added to sources.csv since."""
    path = snap / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for m in manifest:
        if m["status"] != 200:
            m.update(fetch(m["url"], snap / m["file"]))
            print(f"  retried: HTTP {m['status']}  {m['operator']} {m['product']} (via {m['via']})")
    known = {m["url"] for m in manifest}
    for s in sources:
        if s["url"] not in known:
            name = slug(f"{s['operator']} {s['product']}") + ".json"
            manifest.append({**s, "file": name, **fetch(s["url"], snap / name)})
            print(f"  added:   HTTP {manifest[-1]['status']}  {s['operator']} {s['product']}")
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def newest_snapshot() -> Path:
    snaps = sorted(p for p in SNAPSHOTS.glob("*") if (p / "manifest.json").exists())
    if not snaps:
        raise SystemExit("No snapshot yet: run once without --offline.")
    return snaps[-1]


def parse_ranges(body: bytes, section_start: str = "", section_end: str = "") -> dict:
    """Read one range file: the date it gives, its prefixes, and any signature-like fields.
    For documentation pages, section_start/section_end cut out the part that lists egress addresses."""
    out = {"format": "empty", "created": None, "created_raw": "", "v4": [], "v6": [], "sig_fields": []}
    text = body.decode("utf-8", "replace").strip()
    if section_start and section_start in text:
        text = text[text.index(section_start):]
        if section_end and section_end in text:
            text = text[:text.index(section_end)]
    if not text:
        return out
    try:
        data, out["format"] = json.loads(text), "json"
    except ValueError:
        data, out["format"] = None, "not json"
    strings, keys = [], []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                keys.append(str(k))
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            strings.append(node)

    if data is None:
        strings = re.findall(r"[0-9A-Fa-f:.]+/\d{1,3}", text)
    else:
        walk(data)
        if isinstance(data, dict):
            for k in ("creationTime", "creation_time", "lastUpdated", "last_updated", "updated", "generated_at"):
                if isinstance(data.get(k), str):
                    out["created_raw"] = data[k]
                    break
        out["sig_fields"] = sorted({k for k in keys if SIGNATURE_KEY.search(k)})
    nets = set()
    for s in strings:
        s = s.strip()
        if len(s) > 50 or not any(c in s for c in ".:"):
            continue
        try:
            nets.add(ipaddress.ip_network(s, strict=False))
        except ValueError:
            pass
    out["v4"] = sorted(n for n in nets if n.version == 4)
    out["v6"] = sorted(n for n in nets if n.version == 6)
    if out["created_raw"]:
        try:
            t = datetime.fromisoformat(out["created_raw"].replace("Z", "+00:00"))
            out["created"] = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return out


def rdap_record(j: dict) -> dict:
    """Keep the parts of an RDAP answer that say who holds the network."""
    names = []

    def walk(ents):
        for e in ents or []:
            fn = ""
            vcard = e.get("vcardArray")
            if isinstance(vcard, list) and len(vcard) > 1:
                for item in vcard[1]:
                    if item and item[0] == "fn":
                        fn = str(item[3])
            if fn:
                names.append((e.get("roles", []), fn))
            walk(e.get("entities"))

    walk(j.get("entities"))
    reg = [fn for roles, fn in names if "registrant" in roles] or [fn for _, fn in names]
    return {"name": j.get("name", ""), "handle": j.get("handle", ""), "start": j.get("startAddress", ""),
            "end": j.get("endAddress", ""), "registrants": list(dict.fromkeys(reg))[:4]}


class Rdap:
    """RDAP lookups through rdap.org. Answers are cached on disk, and one answer is reused for every
    later prefix that falls inside the network it describes."""

    def __init__(self, offline: bool):
        self.offline, self.path, self.queries = offline, CACHE / "rdap.json", 0
        self.cache = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def covering(self, net) -> dict | None:
        for rec in self.cache.values():
            try:
                lo, hi = ipaddress.ip_address(rec["start"]), ipaddress.ip_address(rec["end"])
            except (KeyError, ValueError):
                continue
            if lo.version == net.version and lo <= net.network_address and net.broadcast_address <= hi:
                return rec
        return None

    def lookup(self, net) -> dict:
        ip = str(net.network_address)
        hit = self.cache.get(ip)
        if not hit or hit.get("error"):  # prefer a good answer for a covering network; retry failures online
            hit = self.covering(net) or (hit if self.offline else None)
        if hit or self.offline:
            return hit or {"registrants": [], "error": "not in cache"}
        rec = {"error": "no answer"}
        for attempt in range(4):
            r = http_get(f"https://rdap.org/ip/{ip}", timeout=40)
            self.queries += 1
            if r["status"] == 200:
                try:
                    rec = rdap_record(json.loads(r["body"]))
                except ValueError:
                    rec = {"error": "bad json"}
                break
            rec = {"error": f"HTTP {r['status']}"}
            if r["status"] not in (0, 429, 500, 502, 503, 504):
                break
            time.sleep(4 * (attempt + 1))
        rec["query"] = ip
        self.cache[ip] = rec
        CACHE.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")
        time.sleep(0.4)
        return rec


def classify(operator: str, rec: dict) -> tuple[str, bool]:
    """Return (who holds the address space, is that the operator itself?)."""
    text = " ".join([rec.get("name") or "", rec.get("handle") or ""] + rec.get("registrants", [])).lower()
    if not text.strip():
        return "unknown", False
    if any(k in text for k in OPERATOR_KEYS.get(operator, [])):
        return operator, True
    for label, keys in HOLDER_KEYS:
        if any(k in text for k in keys):
            return label, False
    return (rec.get("registrants") or [rec.get("name") or "other"])[0], False


def intervals(nets) -> list[list[int]]:
    merged: list[list[int]] = []
    for lo, hi in sorted((int(n.network_address), int(n.broadcast_address)) for n in nets):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def shared(a, b) -> int:
    """How many addresses two merged interval lists have in common."""
    i = j = total = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo <= hi:
            total += hi - lo + 1
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def verdict(ok: bool, why: str = "") -> str:
    return "PASS" if ok else ("FAIL (" + why + ")" if why else "FAIL")


def score(snap: Path, max_age: int, offline: bool) -> tuple[list[dict], list[dict], dict]:
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    fetched = sorted(datetime.fromisoformat(m["fetched_at"]) for m in manifest)
    files, not_scored = [], []
    for m in manifest:
        parsed = (parse_ranges((snap / m["file"]).read_bytes(), m.get("section_start") or "",
                               m.get("section_end") or "") if m["status"] == 200 else None)
        if parsed and (parsed["v4"] or parsed["v6"]):
            files.append({**m, **parsed})
        else:
            not_scored.append({"operator": m["operator"], "product": m["product"], "url": m["url"],
                               "status": m["status"], "error": m.get("error", "")})
    iv4 = {f["file"]: intervals(f["v4"]) for f in files}
    iv6 = {f["file"]: intervals(f["v6"]) for f in files}
    rdap = Rdap(offline)
    rows, prefix_rows = [], []
    for f in files:
        label = f"{f['operator']} {f['product']}"
        # R1 Current: age when this file was fetched
        age = None if f["created"] is None else (datetime.fromisoformat(f["fetched_at"]) - f["created"]).days
        r1 = verdict(False, "no date in the file") if age is None else verdict(age <= max_age, f"{age} days old")
        # R2 Separate
        others = [g for g in files if g["file"] != f["file"]]
        mine4 = iv4[f["file"]]
        addr4 = sum(hi - lo + 1 for lo, hi in mine4)
        ov4 = shared(mine4, intervals([n for g in others for n in g["v4"]]))
        other6 = intervals([n for g in others for n in g["v6"]])
        ov6 = sum(1 for n in f["v6"] if shared(intervals([n]), other6))
        overlap_with = [f"{g['operator']} {g['product']}" for g in others
                        if shared(mine4, iv4[g["file"]]) or shared(iv6[f["file"]], iv6[g["file"]])]
        why = []
        if ov4 or ov6:
            share = f"{ov4 / addr4:.1%} of its IPv4 addresses" if addr4 else f"{ov6} IPv6 prefixes"
            why.append(f"{share} also listed by: " + "; ".join(overlap_with))
        if "one list" in f["purpose"]:
            why.append("one list covers several bots or services")
        r2 = verdict(not why, "; ".join(why))
        # R3 Dedicated
        held4 = held6 = 0
        rented: dict[str, int] = {}
        for n in f["v4"] + f["v6"]:
            rec = rdap.lookup(n)
            holder, held = classify(f["operator"], rec)
            prefix_rows.append({"operator": f["operator"], "list": f["product"], "prefix": str(n),
                                "ipv4_addresses": n.num_addresses if n.version == 4 else "",
                                "holder": holder, "operator_held": held, "rdap_name": rec.get("name", ""),
                                "rdap_registrant": "; ".join(rec.get("registrants", [])),
                                "rdap_network": f"{rec.get('start', '')} - {rec.get('end', '')}",
                                "rdap_error": rec.get("error", "")})
            if held:
                held4 += n.num_addresses if n.version == 4 else 0
                held6 += 1 if n.version == 6 else 0
            else:
                rented[holder] = rented.get(holder, 0) + (n.num_addresses if n.version == 4 else 0)
        total4 = sum(n.num_addresses for n in f["v4"])
        all_held = held4 == total4 and held6 == len(f["v6"])
        top = sorted(rented.items(), key=lambda kv: -kv[1])
        rented_txt = ", ".join(f"{k} {v / total4:.1%}" if total4 else k for k, v in top)
        r3 = verdict(all_held, f"registered to: {rented_txt}" if rented_txt else "")
        # R4 Signed
        r4 = verdict(bool(f["sig_fields"]), "no signature or version history in the file")
        verdicts = [r1, r2, r3, r4]
        rows.append({"operator": f["operator"], "list": f["product"], "purpose": f["purpose"], "url": f["url"],
                     "prefixes_v4": len(f["v4"]), "prefixes_v6": len(f["v6"]), "ipv4_addresses": total4,
                     "date_in_file": f["created_raw"], "age_days": age,
                     "R1_current": r1, "R2_separate": r2, "R3_dedicated": r3, "R4_signed": r4,
                     "operator_held_ipv4_share": round(held4 / total4, 3) if total4 else "",
                     "overlap_ipv4_share": round(ov4 / addr4, 3) if addr4 else "",
                     "passes": sum(v == "PASS" for v in verdicts)})
        print(f"  scored {label}")
    keys = ("R1_current", "R2_separate", "R3_dedicated", "R4_signed")
    summary = {
        "fetched_utc": [fetched[0].isoformat(), fetched[-1].isoformat()], "snapshot": snap.name,
        "max_age_days": max_age,
        "lists_scored": len(rows), "operators": sorted({r["operator"] for r in rows}),
        "pass_counts": {k: sum(r[k] == "PASS" for r in rows) for k in keys},
        "lists_passing_all_four": [f"{r['operator']} {r['list']}" for r in rows if r["passes"] == 4],
        "ages_days": {f"{r['operator']} {r['list']}": r["age_days"] for r in rows},
        "ipv4_addresses_total": sum(r["ipv4_addresses"] for r in rows),
        "rdap_queries_this_run": rdap.queries, "not_scored": not_scored,
    }
    return rows, prefix_rows, summary


def write_outputs(rows: list[dict], prefix_rows: list[dict], summary: dict) -> str:
    RESULTS.mkdir(exist_ok=True)
    for name, data in (("scorecard.csv", rows), ("prefixes.csv", prefix_rows)):
        with open(RESULTS / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    short = lambda v: "pass" if v == "PASS" else "FAIL"
    t0, t1 = (t[:16].replace("T", " ") for t in summary["fetched_utc"])
    lines = [f"Fetched {t0} to {t1} UTC. Age is measured at each file's fetch time. "
             f"R1 limit: {summary['max_age_days']} days.", "",
             "| Operator | List | IPv4 addresses | Age (days) | R1 Current | R2 Separate | R3 Dedicated | R4 Signed | Passes |",
             "|---|---|---:|---:|---|---|---|---|---:|"]
    for r in rows:
        age = "no date" if r["age_days"] is None else r["age_days"]
        lines.append(f"| {r['operator']} | {r['list']} | {r['ipv4_addresses']:,} | {age} | {short(r['R1_current'])} | "
                     f"{short(r['R2_separate'])} | {short(r['R3_dedicated'])} | {short(r['R4_signed'])} | {r['passes']}/4 |")
    pc = summary["pass_counts"]
    lines += ["", f"{summary['lists_scored']} lists from {len(summary['operators'])} operators. Lists passing: "
              f"R1 {pc['R1_current']}, R2 {pc['R2_separate']}, R3 {pc['R3_dedicated']}, R4 {pc['R4_signed']}. "
              f"All four: {len(summary['lists_passing_all_four'])}."]
    if summary["not_scored"]:
        lines.append("Not scored: " + "; ".join(f"{n['operator']} {n['product']} (HTTP {n['status']})"
                                                for n in summary["not_scored"]))
    text = "\n".join(lines) + "\n"
    (RESULTS / "scorecard.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="re-score the newest snapshot without network access")
    ap.add_argument("--retry-failed", action="store_true",
                    help="reuse the newest snapshot, fetch only files that failed or were added to sources.csv, score")
    ap.add_argument("--max-age", type=int, default=30, help="R1 limit in days (default 30)")
    args = ap.parse_args()
    if args.offline:
        snap = newest_snapshot()
    elif args.retry_failed:
        snap = newest_snapshot()
        update_snapshot(snap, load_sources())
    else:
        print("Fetching the published range files ...")
        snap = take_snapshot(load_sources())
    print(f"Scoring snapshot {snap.name} (RDAP lookups may take a few minutes the first time) ...")
    rows, prefix_rows, summary = score(snap, args.max_age, args.offline)
    print()
    print(write_outputs(rows, prefix_rows, summary))


if __name__ == "__main__":
    main()
