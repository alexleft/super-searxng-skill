---
name: searxng
description: Search the web via the user's SearXNG instance (default https://s.gba.fan/) — a privacy-respecting metasearch engine aggregating 250+ engines (Bing, Yandex, Baidu, Sogou, DuckDuckGo, Wikipedia, GitHub, arXiv, MDN, Stack Overflow, news, images, videos, etc.). Use this for any web search, fact lookup, current-events query, documentation lookup, image/news search, or when `web_search` is unavailable. HTTP/TLS and concurrency are handled by a Python backend (stdlib urllib + ThreadPoolExecutor) — no PowerShell .NET HTTP stack, no temp files, works identically in FullLanguage and ConstrainedLanguage.
---

# SearXNG Search

Backend: **Python 3 stdlib only** (`urllib`, `concurrent.futures`, `json`). Python uses the OS-native TLS stack (SChannel on Windows, OpenSSL on Unix), so this skill does not suffer from Windows PowerShell 5.1 / ConstrainedLanguage TLS failures.

The base directory of this skill is provided in `<skill_resources>` when the skill is loaded. Resolve every script path against that base directory — do not hardcode `C:\Users\...`.

## How to search (Windows / PowerShell)

Invoke `searxng.ps1` with **named parameters** through the `pwsh` tool. Use `$skillBase` for the directory the skill loader gives you:

```powershell
$skillBase = "<skill_resources base directory>"  # provided by the skill loader
& "$skillBase\searxng.ps1" -Query "deepseek v3 发布" -Language zh-CN
```

Typical invocations:

```powershell
# Single query
& "$skillBase\searxng.ps1" -Query "deepseek v3 发布" -Language zh-CN

# Multiple queries in parallel (fan-out, merged + deduplicated)
& "$skillBase\searxng.ps1" -Queries @("q1","q2","q3") -Merge -Limit 8 -MaxConcurrency 3

# Programming / technical
& "$skillBase\searxng.ps1" -Query "typescript 5.5 release notes" -Category it -Language en

# Recent news
& "$skillBase\searxng.ps1" -Query "AI regulation EU" -Category news -TimeRange week -Language en

# Image search
& "$skillBase\searxng.ps1" -Query "system architecture diagram" -Category images -Limit 8

# Constrain to specific engines
& "$skillBase\searxng.ps1" -Query "react useEffect cleanup" -Engines "bing,mdn,stackoverflow"
```

## How to search (Unix / bash)

There is a POSIX launcher at `bin/searxng` that resolves `python3`/`python` and forwards arguments. The parameter names are the same; use GNU-style long options:

```bash
SKILL_BASE=/path/to/super-searxng-skill
"$SKILL_BASE/bin/searxng" --query "deepseek v3 发布" --language zh-CN
"$SKILL_BASE/bin/searxng" --queries "q1" "q2" "q3" --merge --limit 8 --max-concurrency 3
```

Python is required (3.8+). The script itself has no third-party dependencies.

## Direct Python invocation

The launcher is a thin wrapper around `searxng.py`. You can call it directly if you already have a Python interpreter:

```bash
python3 searxng.py "query" --language en
python3 searxng.py --queries q1 q2 q3 --merge
python3 searxng.py --stdin < request.json   # JSON on stdin
```

## Parameters

| Parameter (PS / bash) | CLI flag | Default | Notes |
|---|---|---|---|
| `-Query` / `--query` | positional | — | Single search string (mutually exclusive with `-Queries`). |
| `-Queries` / `--queries` | `--queries` | — | Array of queries; run concurrently via Python ThreadPoolExecutor. |
| `-Category` / `--category` | `--category` | `general` | `general`, `news`, `images`, `videos`, `it`, `science`, `files`, `music`, `books`, `social media`, `maps`, `repos`, `software wikis`, `scientific publications`, ... |
| `-Language` / `--language` | `--language` | `all` | `zh-CN`, `en`, `en-US`, `ja`, etc. |
| `-Page` / `--page` | `--page` | 1 | Result page (1-based). |
| `-TimeRange` / `--time-range` | `--time-range` | _(none)_ | `day`, `week`, `month`, `year`. |
| `-SafeSearch` / `--safesearch` | `--safesearch` | 1 | `0` off / `1` moderate / `2` strict. |
| `-Engines` / `--engines` | `--engines` | _(all)_ | Comma-separated engines. Setting this disables the auto-fallback. |
| `-Limit` / `--limit` | `--limit` | 10 | Results per query (or total in merged mode). |
| `-Merge` / `--merge` | `--merge` | off | Fan-out: deduplicate by URL and tag each result with its origin query. |
| `-MaxConcurrency` / `--max-concurrency` | `--max-concurrency` | 4 | Parallel threads (1..12). |
| `-Timeout` / `--timeout` | `--timeout` | 25 | Per-request HTTP timeout in seconds. |
| `-BaseUrl` / `--base-url` | `--base-url` | `https://s.gba.fan/` | Override instance (also honors `$SEARXNG_URL`). |
| `-FallbackEngines` / `--fallback-engines` | `--fallback-engines` | built-in | Engines to retry with when the default pool returns 0 results. Default: `bing,yandex,sogou,duckduckgo,mdn,stackoverflow,wikipedia`. |
| `-NoFallbackEngines` / `--no-fallback-engines` | `--no-fallback-engines` | off | Disable automatic fallback retry. |
| `-Raw` / `--raw` | `--raw` | off | Emit JSON instead of Markdown. |
| `-Stdin` / `--stdin` | `--stdin` | off | Read a JSON request from stdin instead of CLI args. |

Python interpreter resolution (PS launcher): `$env:SEARXNG_PYTHON` → `python.exe` / `py.exe` (Windows) → `python3` / `python` (Unix). The bash launcher uses `$SEARXNG_PYTHON` if set, else `python3`.

## When to fan out

Use `-Queries @(...)` whenever you would otherwise run two or more related searches. Typical wall-clock for 5 parallel queries is ~5–7 seconds (bounded by the slowest engine) versus ~25 s serial. Fan-out uses Python `ThreadPoolExecutor`, not PowerShell runspaces, so it works regardless of language mode.

Use `-Merge` for cross-query research (comparisons, multi-angle investigation) so duplicate URLs collapse and each hit carries `_(from: <query>)_`. Leave it off for unrelated queries that should appear as separate sections.

## Working effectively

1. **Language.** Chinese queries → `-Language zh-CN`; programming/English-primary topics → `-Language en`. The fallback engine list includes `sogou` and `yandex`, both of which return solid Chinese results on the default instance.
2. **`-Category it` for coding questions.** Surfaces MDN, Stack Overflow, GitHub, wikis.
3. **`-TimeRange` for anything time-sensitive** (releases, news, "latest X").
4. **Pin `-Engines` when you know the source** (`bing`, `wikipedia`, `github`, `mdn`, `arxiv`). Pinning disables fallback because the user has made an explicit choice.
5. **Per-query overrides** (different category/language per query in one fan-out) are not exposed in the wrappers; use `-Stdin` with a JSON payload. See `examples/request.schema.json` and `examples/request.json`.
6. The `transport: python-urllib` line in the output confirms Python handled the request end-to-end.
7. **No temp files are written.** All response bodies live in memory; stdout is reconfigured to UTF-8 so Chinese and other non-ASCII render correctly on every Windows code page.

## Why Python and not PowerShell `Invoke-WebRequest` or curl.exe?

Earlier PowerShell-only versions hit two ConstrainedLanguage problems:

- `Invoke-WebRequest` in Windows PowerShell 5.1 uses `.NET HttpWebRequest`, whose TLS version is controlled by `[Net.ServicePointManager]::SecurityProtocol` — a property that ConstrainedLanguage blocks from being set, producing `基础连接已经关闭: 接收时发生错误` against modern TLS 1.2+ endpoints.
- `curl.exe` solved TLS but needed temp files for response bodies (PowerShell's pipeline mangles UTF-8 under ConstrainedLanguage because `[Console]::OutputEncoding` is locked), and retries/concurrency had to be hand-rolled in runspaces that ConstrainedLanguage also blocks.

Python's `urllib` sidesteps both: OS-native TLS negotiation, in-memory response handling, native JSON, and standard-library threading. The PowerShell launcher is a thin argument translator with no .NET type usage that ConstrainedLanguage would block.

## When to fall back to `web_search`

If the built-in `web_search` tool returns an auth error or timeout, use this skill. If SearXNG itself returns an HTTP/network error that survives all three retries AND the fallback-engine retry, then fall back to `web_search`. Do not blame language mode — this skill has no PowerShell-language-mode dependencies.
