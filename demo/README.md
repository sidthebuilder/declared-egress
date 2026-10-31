# Demo: the daily log check

`access_log.txt` is a **synthetic** ten-line web server log for a wiki, written to show what `check_log.py`
does. Addresses of declared AI operators come from their real published lists; every other address is from
the ranges reserved for documentation (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).

`research_registry.json` is a **hypothetical** declaration in the proposed format (Appendix A3 of the
proposal) for a research-and-evaluation range, `203.0.113.0/24`. No operator publishes one today.

```
python check_log.py demo/access_log.txt --extra demo/research_registry.json
```

What it shows:
- a request that claims to be GPTBot from outside OpenAI's declared addresses is flagged as spoofed;
- a write from a declared user-directed agent range is flagged for a check;
- DseWiki-style edits (writes through ordinary page requests) from the declared research range are flagged for
  a report within 24 hours, which is the case the standard is built for;
- normal visitors and declared crawlers that only read are not flagged.
