"""Check which AI operators publish a Web Bot Auth key directory, i.e. sign their agents' requests.

With Web Bot Auth (HTTP Message Signatures, RFC 9421) an agent signs each request, and its operator
publishes the public keys at /.well-known/http-message-signatures-directory. Signed requests are the
second half of a declared-egress standard: unsigned traffic from a declared agent range is a red flag.

A "no" below only means no directory was found at that domain; an operator may sign from another domain.

  python signing_check.py      writes results/signing.csv and results/signing.md
"""
import csv
import json
from datetime import datetime, timezone

from scorecard import RESULTS, http_get

PATH = "/.well-known/http-message-signatures-directory"
DOMAINS = [
    ("OpenAI", "chatgpt.com"), ("OpenAI", "openai.com"),
    ("Anthropic", "claude.ai"), ("Anthropic", "claude.com"), ("Anthropic", "anthropic.com"),
    ("Google", "agent.bot.goog"), ("Google", "google.com"), ("Google", "gemini.google.com"),
    ("Microsoft", "bing.com"), ("Microsoft", "copilot.microsoft.com"),
    ("Apple", "apple.com"), ("Perplexity", "perplexity.ai"), ("Perplexity", "www.perplexity.com"),
    ("Mistral", "mistral.ai"), ("Meta", "meta.ai"), ("Meta", "www.meta.com"),
    ("xAI", "x.ai"), ("xAI", "grok.com"), ("Common Crawl", "commoncrawl.org"), ("DuckDuckGo", "duckduckgo.com"),
]


def main() -> None:
    rows = []
    for operator, domain in DOMAINS:
        r = http_get(f"https://{domain}{PATH}", timeout=20)
        keys = 0
        try:
            data = json.loads(r["body"])
            keys = len(data.get("keys", [])) if isinstance(data, dict) else 0
        except (ValueError, TypeError):
            pass
        rows.append({"operator": operator, "domain": domain, "http_status": r["status"],
                     "content_type": r["type"].split(";")[0], "keys": keys,
                     "directory_found": "yes" if keys else "no",
                     "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"  {domain:<24} HTTP {r['status']:<4} keys {keys}")
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "signing.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    found = [r for r in rows if r["keys"]]
    lines = [f"Checked {len(rows)} domains of {len({r['operator'] for r in rows})} operators for {PATH}.",
             "Key directories found: " + (", ".join(f"{r['domain']} ({r['operator']}, {r['keys']} keys)"
                                                     for r in found) or "none")]
    (RESULTS / "signing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
