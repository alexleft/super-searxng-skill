# super-searxng-skill

A [DSH](https://github.com/deepseek-ai/dsh) skill that lets the agent search the web through your own [SearXNG](https://github.com/searxng/searxng) instance. The entire HTTP, TLS, concurrency, and rendering stack runs in **Python 3 stdlib only** (`urllib`, `concurrent.futures`, `json`) — there is no PowerShell `Invoke-WebRequest`, no `.NET HttpWebRequest`, no `curl.exe`, and **no temp files**.

This design is a deliberate reaction to earlier PowerShell-only versions that kept dying under Windows ConstrainedLanguage with `基础连接已经关闭: 接收时发生错误` (TLS handshake failure) because `[Net.ServicePointManager]::SecurityProtocol` is locked. Python uses the OS-native TLS stack (SChannel on Windows, OpenSSL on Unix) and is unaffected.

## Layout

```
super-searxng-skill/
├── SKILL.md              # Skill manifest + documentation (read by DSH)
├── searxng.py            # Python backend (urllib + ThreadPoolExecutor)
├── searxng.ps1           # Windows / PowerShell launcher
├── bin/
│   └── searxng           # Unix / bash launcher
├── examples/
│   ├── queries.ps1       # Copy/paste example invocations
│   ├── request.json      # Example stdin JSON payload
│   └── request.schema.json  # JSON Schema for the stdin payload
├── install.ps1           # Windows installer (copies to ~/.dsh/skills/searxng)
├── install.sh            # Unix installer
├── skill.json            # Machine-readable metadata / defaults
└── README.md             # This file
```

## Requirements

- Python **3.8+** on `PATH` (the Windows launcher checks `python.exe`, `py.exe`, `python3.exe`; the Unix launcher checks `python3`, `python`).
- No `pip install` needed — stdlib only.
- A reachable SearXNG instance. The default is `https://s.gba.fan/`; override with `-BaseUrl` / `--base-url` or the `SEARXNG_URL` environment variable.
- To point at a non-default Python interpreter, set `SEARXNG_PYTHON` to its full path.

## Install

### Windows

```powershell
cd C:\app\super-searxng-skill
.\install.ps1
# or to a custom location:
.\install.ps1 -Target D:\dsh\skills\searxng
```

The installer copies `SKILL.md`, `searxng.py`, and `searxng.ps1` into the target directory. If those files already exist they are backed up with a `.bak-<timestamp>` suffix first.

### Unix

```bash
cd /path/to/super-searxng-skill
./install.sh
# or to a custom location:
./install.sh /custom/skills/path/searxng
```

Reload the DSH session (or start a new one). The `searxng` skill will appear in the catalog.

## Usage

The skill is invoked by the agent (not manually by the user), but here are direct smoke tests:

### Windows

```powershell
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "DeepSeek V4 Flash 评测" -Language zh-CN

& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Queries @("Qwen3.8 benchmark","DeepSeek V4 benchmark") `
    -Merge -Limit 8 -MaxConcurrency 3
```

### Unix

```bash
~/.dsh/skills/searxng/bin/searxng "DeepSeek V4 Flash 评测" --language zh-CN
~/.dsh/skills/searxng/bin/searxng --queries "Qwen3.8 benchmark" "DeepSeek V4 benchmark" \
    --merge --limit 8 --max-concurrency 3
```

### Direct Python

```bash
python searxng.py "query" --language en
python searxng.py --queries q1 q2 q3 --merge
python searxng.py --stdin < examples/request.json
python searxng.py --help
```

### JSON over stdin

For fan-out with different category/language per query, pipe a JSON request:

```powershell
Get-Content examples\request.json -Raw |
    & "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" -Stdin
```

The schema lives in [`examples/request.schema.json`](examples/request.schema.json).

## Parameters

The full parameter list (PowerShell name / bash flag / default):

| PowerShell | bash | Default | Purpose |
|---|---|---|---|
| `-Query` | positional | — | Single query string |
| `-Queries` | `--queries` | — | Array of queries (fan-out) |
| `-Category` | `--category` | `general` | `general`/`news`/`images`/`videos`/`it`/... |
| `-Language` | `--language` | `all` | `zh-CN`, `en`, etc. |
| `-Page` | `--page` | 1 | Result page |
| `-TimeRange` | `--time-range` | _(none)_ | `day`/`week`/`month`/`year` |
| `-SafeSearch` | `--safesearch` | 1 | 0 / 1 / 2 |
| `-Engines` | `--engines` | _(all)_ | Comma-separated engines (disables fallback) |
| `-Limit` | `--limit` | 10 | Results per query / total in merged mode |
| `-Merge` | `--merge` | off | Deduplicate fan-out results by URL |
| `-MaxConcurrency` | `--max-concurrency` | 4 | Parallel threads (1..12) |
| `-Timeout` | `--timeout` | 25 | Per-request HTTP timeout (s) |
| `-BaseUrl` | `--base-url` | `https://s.gba.fan/` | SearXNG root URL |
| `-FallbackEngines` | `--fallback-engines` | built-in | Auto-retry engine set on 0 results |
| `-NoFallbackEngines` | `--no-fallback-engines` | off | Disable the fallback retry |
| `-Raw` | `--raw` | off | Emit JSON instead of Markdown |
| `-Stdin` | `--stdin` | off | Read JSON request from stdin |

## Why the Python rewrite

Earlier versions of this skill used PowerShell `Invoke-WebRequest` and then `curl.exe` from PowerShell. Both failed under ConstrainedLanguage:

1. **`Invoke-WebRequest` (.NET `HttpWebRequest`)** — TLS version is governed by `[Net.ServicePointManager]::SecurityProtocol`, which ConstrainedLanguage blocks writes to, so modern TLS 1.2+ endpoints fail with `基础连接已经关闭: 接收时发生错误`.
2. **`curl.exe`** — TLS worked (Schannel), but response bodies had to be written to temp files because PowerShell's pipeline encoding is locked in ConstrainedLanguage and mangled UTF-8. Retries and parallelism also had to be hand-rolled with runspaces that ConstrainedLanguage blocks.

The Python backend eliminates all three problems at once: OS-native TLS, in-memory response handling, and `ThreadPoolExecutor` for parallelism.

## Design notes

- **Zero temp files.** Everything is held in memory; stdout is reconfigured to UTF-8 (`sys.stdout.reconfigure(encoding="utf-8")`) on Python 3.7+.
- **No language-mode dependencies.** The PowerShell launcher uses only cmdlets, basic arrays/strings, and process spawning. No `[System.Net.*]`, no `runspacefactory`, no `Add-Type`, no `New-Object System.*`.
- **Retry with backoff.** Network errors, 5xx, 408, and 429 responses retry up to 3 times with 300 ms / 600 ms backoff.
- **Auto-fallback engines.** The default engine pool on many public SearXNG instances has chronically unresponsive engines (aol, baidu, brave, duckduckgo, karmasearch, startpage). When the first request returns 0 results and the user did not pin engines, the backend retries with a curated reliable set (`bing,yandex,sogou,duckduckgo,mdn,stackoverflow,wikipedia`). `sogou` and `yandex` are included because they return solid Chinese results.
- **Merged fan-out dedupes by URL.** Each surviving result is tagged with `_(from: <query>)_` so you can see which query produced it.

## License

MIT.
