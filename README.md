# Declared Egress: the Registry Scorecard

**Whose agent is this?** When an AI agent misbehaves on a website, the site can only tell whose agent it was if the operator has declared where its agents' traffic comes from. This repository measures how far today's declarations are from four checkable requirements, shows how a site would use them, and backs a proposal for a German-led **Declared Egress Standard**.

Entry for the Middle Powers hackathon (Mangrove, 31 Oct to 1 Nov 2026), Track A: Regulation. Lead country: Germany, with Canada and Australia.

- Proposal (8 pages): [`Shashank_Kumar_Declared_Egress_Germany.pdf`](Shashank_Kumar_Declared_Egress_Germany.pdf)
- Results: [`results/`](results/)
- Log-check demo: [`demo/`](demo/)

## Why it matters

In 2026, agents trained or evaluated at OpenAI reached the live internet and hit third parties: the German-language wiki DseWiki, Hugging Face, and Australia's Medicare statistics portal, among more than 100 organisations notified by 1 October. Victims learned whose agents they were after 84 days (Medicare) and over 100 days (DseWiki). The published IP lists cover crawlers, fetchers and user-directed agents, not research and evaluation agents, and the lists that exist fail basic checks. Sources are in the proposal.

## Results (files fetched 31 October 2026, 11:48 to 12:49 UTC)

Age is measured at the time each file was fetched. The generated version is [`results/scorecard.md`](results/scorecard.md); the rows below are the same, grouped by operator.

| Operator | List | IPv4 addresses | Age (days) | R1 Current | R2 Separate | R3 Dedicated | R4 Signed | Passes |
|---|---|---:|---:|---|---|---|---|---:|
| OpenAI | GPTBot | 2,704 | 39 | FAIL | FAIL | FAIL | FAIL | 0/4 |
| OpenAI | OAI-SearchBot | 2,560 | 302 | FAIL | FAIL | FAIL | FAIL | 0/4 |
| OpenAI | ChatGPT-User | 69,280 | 3 | pass | FAIL | FAIL | FAIL | 1/4 |
| OpenAI | OAI-AdsBot | 256 | 172 | FAIL | pass | FAIL | FAIL | 1/4 |
| OpenAI | ChatGPT connectors | 69,227 | 3 | pass | FAIL | FAIL | FAIL | 1/4 |
| OpenAI | ChatGPT agents (Codex cloud) | 94,096 | 1 | pass | FAIL | FAIL | FAIL | 1/4 |
| Anthropic | ClaudeBot, Claude-SearchBot, Claude-User | 1,037 | 11 | pass | FAIL | FAIL | FAIL | 1/4 |
| Anthropic | Claude API outbound | 2,048 | no date | FAIL | FAIL | pass | FAIL | 1/4 |
| Google | Common crawlers (Googlebot) | 5,088 | 0 | pass | pass | pass | FAIL | 3/4 |
| Google | Special-case crawlers | 4,352 | 0 | pass | pass | pass | FAIL | 3/4 |
| Google | User-triggered fetchers | 17,088 | 0 | pass | pass | pass | FAIL | 3/4 |
| Google | User-triggered fetchers (Google) | 8,064 | 0 | pass | pass | pass | FAIL | 3/4 |
| Google | User-triggered agents (Google-Agent) | 67,840 | 242 | FAIL | pass | pass | FAIL | 2/4 |
| Microsoft | Bingbot | 4,736 | 1032 | FAIL | pass | FAIL | FAIL | 1/4 |
| Apple | Applebot | 4,752 | 46 | FAIL | pass | pass | FAIL | 2/4 |
| Perplexity | PerplexityBot | 13 | 2 | pass | pass | FAIL | FAIL | 2/4 |
| Perplexity | Perplexity-User | 10 | 2 | pass | pass | FAIL | FAIL | 2/4 |
| Mistral | MistralAI-Index | 2 | 194 | FAIL | pass | FAIL | FAIL | 1/4 |
| Mistral | MistralAI-User | 4 | 618 | FAIL | pass | FAIL | FAIL | 1/4 |
| Common Crawl | CCBot | 28 | 80 | FAIL | pass | FAIL | FAIL | 1/4 |
| DuckDuckGo | DuckAssistBot | 486 | 59 | FAIL | pass | FAIL | FAIL | 1/4 |

- 21 lists from 9 operators. **None passes all four; none is signed or keeps a version history.**
- 11 lists are undated or more than 30 days old. Bingbot's is dated January 2024. Anthropic's API page gives no date.
- OpenAI lists 104,027 distinct IPv4 addresses across six lists. 98.7% are registered to Microsoft and 0.7% (728) to OpenAI itself. The rest are registered to 35 other organisations (614 addresses, mostly internet providers) and Amazon (21).
- The lists overlap. 98% of ChatGPT-User's addresses are also in the ChatGPT connectors list, 70% of the Codex cloud list is in both, and 28% of GPTBot's addresses are in OAI-SearchBot's list. Anthropic uses one list for three bots and says its API outbound range is shared across its services.
- Google and Apple hold all of their addresses. Anthropic's API outbound block (160.79.104.0/21) is registered to Anthropic, and 98.7% of its crawler addresses are in a block that Amazon has assigned to Anthropic by name (216.73.216.0/22, "AWS-ANTHROPIC"). Perplexity, Mistral, Common Crawl and DuckDuckGo list only rented cloud addresses.
- No list covers research, training or evaluation runs. No IP list was found for Meta or xAI.
- Web Bot Auth key directories (for signed requests) were found at 3 of 20 domains checked: `chatgpt.com` (OpenAI, 1 key), `agent.bot.goog` (Google, 5 keys) and `www.meta.com` (Meta, 5 keys).

Per-list reasons are in [`results/scorecard.csv`](results/scorecard.csv); every prefix and its registry holder is in [`results/prefixes.csv`](results/prefixes.csv); the signing check is in [`results/signing.csv`](results/signing.csv).

## The four requirements

| | Requirement | How the scorecard checks it |
|---|---|---|
| R1 | **Current**: the file is dated and at most 30 days old | the file's own `creationTime` against the fetch time (`--max-age`) |
| R2 | **Separate**: one purpose per list, no address in two lists | exact address overlap between all lists, plus lists documented as covering several bots or services |
| R3 | **Dedicated**: every address registered to the operator itself | an RDAP lookup for every prefix, via rdap.org |
| R4 | **Signed**: the file is signed or keeps an append-only version history | a search of the file for signature, proof or history fields |

The requirements come from my earlier paper, *Attestation Gaps* (Apart Research, September 2026). The scorecard, the signing check, the log check and these measurements are new for this hackathon.

## Run it

Python 3.11 or later, standard library only.

```
python scorecard.py                 # fetch the live lists into snapshots/<UTC date>/ and score them
python scorecard.py --retry-failed  # keep the newest snapshot, fetch only files that failed or are new, score
python scorecard.py --offline       # reproduce every number from the saved snapshot, no network
python signing_check.py             # look for Web Bot Auth key directories on 20 domains
python check_log.py access.log      # check a web server log against every declared range
```

## The log check

`check_log.py` is the daily check a website or national CERT would run under the standard. It reads a log in the common or combined format, finds the declared list (operator and purpose) for each source address using `results/prefixes.csv`, and raises three flags:

- `RESEARCH-RANGE`: a request from a range declared for research, training or evaluation runs;
- `WRITE-FROM-DECLARED`: a write (POST, PUT, PATCH, DELETE, or an editing GET) from a declared range;
- `CLAIMED-NOT-DECLARED`: a user agent that names an operator's bot, from outside all of that operator's declared ranges.

`--extra` adds registry files in the format proposed in Appendix A3 of the proposal, and `--out` saves the report.

```
python check_log.py demo/access_log.txt --extra demo/research_registry.json
```

The demo log is synthetic and the research range is a hypothetical declaration on addresses reserved for documentation, because no operator publishes one today. Of 10 requests checked against 5,121 declared ranges, 5 are flagged: a fake GPTBot, a write from an address declared in both ChatGPT-User and ChatGPT connectors, two DseWiki-style edits from the research range (report within 24 hours), and one read from the research range. The output is in [`demo/check_log_result.txt`](demo/check_log_result.txt).

## What is in here

- `sources.csv`: the 21 list URLs (20 files and one documentation page), taken from the operators' own documentation
- `scorecard.py`, `signing_check.py`, `check_log.py`: the three checks
- `snapshots/2026-10-31/`: the raw files, saved exactly as fetched, and a manifest with SHA-256 hashes and fetch times (Anthropic's documentation page is HTML, although its file name ends in `.json`)
- `cache/rdap.json`: all 271 registry answers used for R3
- `results/`: `scorecard.csv`, `scorecard.md`, `prefixes.csv`, `summary.json`, `signing.csv`, `signing.md`
- `demo/`: the synthetic log, the hypothetical research registry and the log-check output

## Limits

- One snapshot in time. Lists change; rerun to update.
- Registry holders are matched to operators by name. The raw answers are saved so anyone can check them.
- The search for lists may have missed some. For Anthropic's API documentation page, only the "Outbound IP addresses" section is read; other product pages may list more addresses. A "no" in the signing check only means no key directory was found at the domains checked.
- On Windows, Python could not complete Apple's certificate chain, so that one file was fetched with PowerShell; the manifest records this.

## AI use

I used Claude (Anthropic) as a coding and research assistant: it wrote and ran this code (the scorecard, the signing check and the log check), searched for and checked sources, and drafted the proposal and this README. I chose the country, the track and the proposal, and reviewed every claim before submitting.

## License

MIT. See [LICENSE](LICENSE).
