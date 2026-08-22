#!/usr/bin/env python3
"""
SearXNG search backend for the super-searxng-skill.

Transport: stdlib urllib only (no third-party deps). Uses the OS-native TLS
stack via Python's ssl module (SChannel / OS root certs on Windows, OpenSSL
elsewhere) -- no PowerShell .NET HttpWebRequest, no language-mode constraints,
no temp files.

Concurrency: concurrent.futures.ThreadPoolExecutor for fan-out.

Usage:
    python searxng.py "query" [--category it] [--language en] [...]
    python searxng.py --queries q1 q2 q3 --merge --limit 8
    python searxng.py --stdin < request.json
    python searxng.py --help
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = os.environ.get("SEARXNG_URL", "https://s.gba.fan/")
DEFAULT_FALLBACK_ENGINES = "bing,yandex,sogou,duckduckgo,mdn,stackoverflow,wikipedia"
USER_AGENT = "super-searxng-skill/1.0 (+https://github.com/deepseek-ai/dsh)"
MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = (0.3, 0.6)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _post_form(url: str, fields: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    """POST application/x-www-form-urlencoded; return parsed JSON.

    Retries transient network/5xx/408/429 errors. Raises RuntimeError on
    persistent failure.
    """
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    last_err: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                body = resp.read()
            return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (408, 429) and 400 <= e.code < 500:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
            last_err = f"HTTP {e.code}: {e.reason}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON parse error: {e}") from e
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
    raise RuntimeError(last_err or "unknown error")


def _one_search(spec: dict[str, Any], base_url: str, timeout_sec: int,
                fallback_engines: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "q": spec["q"],
        "format": "json",
        "pageno": str(spec.get("page", 1)),
        "language": spec.get("language", "all"),
        "safesearch": str(spec.get("safesearch", 1)),
    }
    cat = spec.get("category", "")
    if cat:
        fields["categories"] = cat
    tr = spec.get("time_range", "")
    if tr:
        fields["time_range"] = tr
    eng = spec.get("engines", "")
    if eng:
        fields["engines"] = eng

    t0 = time.time()
    try:
        data = _post_form(base_url.rstrip("/") + "/search", fields, timeout_sec)
    except Exception as e:
        return _err_result(spec, str(e), cat, int((time.time() - t0) * 1000))

    # Auto-fallback: if the default engine pool returned 0 results and the
    # caller did not pin engines, retry with the curated reliable set.
    results = list(data.get("results") or [])
    if (not results and not eng and fallback_engines
            and spec.get("allow_fallback", True)):
        fields["engines"] = fallback_engines
        try:
            data2 = _post_form(base_url.rstrip("/") + "/search", fields, timeout_sec)
            results2 = list(data2.get("results") or [])
            if results2:
                data, results = data2, results2
        except Exception:
            pass  # keep original (empty) result

    reported = data.get("number_of_results") or 0
    if not reported and results:
        reported = len(results)

    return {
        "ok": True,
        "query": spec["q"],
        "category": cat,
        "language": spec.get("language", "all"),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "number_of_results": reported,
        "results": results,
        "answers": list(data.get("answers") or []),
        "infoboxes": list(data.get("infoboxes") or []),
        "suggestions": list(data.get("suggestions") or []),
        "corrections": list(data.get("corrections") or []),
        "unresponsive_engines": list(data.get("unresponsive_engines") or []),
    }


def _err_result(spec: dict[str, Any], message: str, cat: str,
                elapsed_ms: int) -> dict[str, Any]:
    return {
        "ok": False,
        "query": spec["q"],
        "error": message,
        "elapsed_ms": elapsed_ms,
        "category": cat,
        "language": spec.get("language", "all"),
        "number_of_results": 0,
        "results": [],
        "answers": [],
        "infoboxes": [],
        "suggestions": [],
        "corrections": [],
        "unresponsive_engines": [],
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _format_hit(hit: dict[str, Any], idx: int, origin: str | None = None) -> str:
    title = (hit.get("title") or "(untitled)").strip()
    engine = hit.get("engine", "?")
    tag = f"  _(from: {origin})_" if origin else ""
    lines = [f"{idx}. {title}  [{engine}]{tag}", f"   {hit.get('url', '')}"]
    if hit.get("publishedDate"):
        lines.append(f"   published: {hit['publishedDate']}")
    if hit.get("img_src"):
        lines.append(f"   img: {hit['img_src']}")
    if hit.get("source"):
        lines.append(f"   src: {hit['source']}")
    content = (hit.get("content") or "").strip()
    if content:
        if len(content) > 300:
            content = content[:297] + "..."
        lines.append(f"   {content}")
    return "\n".join(lines)


def _render_single(r: dict[str, Any], limit: int, page: int,
                   time_range: str, engines: str) -> str:
    out: list[str] = [f"## SearXNG: {r['query']}"]
    meta = []
    if r.get("category") and r["category"] != "general":
        meta.append(f"category={r['category']}")
    if r.get("language") and r["language"] != "all":
        meta.append(f"lang={r['language']}")
    if page > 1:
        meta.append(f"page={page}")
    if time_range:
        meta.append(f"time={time_range}")
    if engines:
        meta.append(f"engines={engines}")
    if meta:
        out.append("(" + ", ".join(meta) + ")")
    out.append(f"_took {r['elapsed_ms']} ms_  _(transport: python-urllib)_")
    out.append("")

    if not r["ok"]:
        out.append(f"**ERROR:** {r['error']}")
        return "\n".join(out)

    for a in r.get("answers", []):
        out.append(f"- {a}")
    if r.get("answers"):
        out.append("")

    for box in r.get("infoboxes", []):
        out.append(f"### Infobox: {box.get('infobox_type', '')}")
        if box.get("content"):
            out.append(box["content"])
        for u in box.get("urls", []):
            out.append(f"- {u.get('title', '')}: {u.get('url', '')}")
        out.append("")

    results = r.get("results", [])
    if 0 < limit < len(results):
        results = results[:limit]
    heading = "Images" if r.get("category", "").lower() == "images" else "Results"
    out.append(f"### {heading} ({len(r.get('results', []))} total, showing {len(results)})")
    for i, hit in enumerate(results, 1):
        out.append(_format_hit(hit, i))
        out.append("")

    if r.get("suggestions"):
        out.append("### Suggestions")
        out.extend(f"- {s}" for s in r["suggestions"])
        out.append("")
    if r.get("corrections"):
        out.append("### Corrections")
        out.extend(f"- {c}" for c in r["corrections"])
        out.append("")
    if r.get("unresponsive_engines"):
        names = [u[0] if isinstance(u, (list, tuple)) else str(u)
                 for u in r["unresponsive_engines"]]
        out.append(f"_(Unresponsive engines: {', '.join(names)})_")
    return "\n".join(out)


def _render_merged(responses: list[dict[str, Any]], limit: int,
                   parallel: bool) -> str:
    wall = (max(r["elapsed_ms"] for r in responses) if parallel
            else sum(r["elapsed_ms"] for r in responses))
    ok_count = sum(1 for r in responses if r["ok"])
    out = [
        f"## SearXNG (merged {ok_count}/{len(responses)} queries, "
        f"wall ~{wall}ms, transport: python-urllib)",
        "",
    ]

    for r in responses:
        if not r["ok"]:
            continue
        for a in r.get("answers", []):
            out.append(f"### Answer ({r['query']})\n- {a}\n")
        for box in r.get("infoboxes", []):
            out.append(f"### Infobox ({r['query']}): {box.get('infobox_type', '')}")
            if box.get("content"):
                out.append(box["content"])
            out.append("")

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for r in responses:
        if not r["ok"]:
            continue
        for hit in r.get("results", []):
            url = (hit.get("url") or "").rstrip("/").lower()
            if not url or url in seen:
                continue
            seen.add(url)
            hit["_origin"] = r["query"]
            merged.append(hit)

    display = merged[:limit] if 0 < limit < len(merged) else merged
    out.append(f"### Results ({len(merged)} unique, showing {len(display)})")
    for i, hit in enumerate(display, 1):
        out.append(_format_hit(hit, i, hit.get("_origin")))
        out.append("")
    out.append("---")
    out.append("### Per-query stats")
    for r in responses:
        if r["ok"]:
            out.append(
                f'- "{r["query"]}": {len(r.get("results", []))} results '
                f'in {r["elapsed_ms"]} ms'
            )
        else:
            out.append(
                f'- "{r["query"]}": ERROR {r["error"]} after {r["elapsed_ms"]} ms'
            )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def run(req: dict[str, Any]) -> dict[str, Any]:
    base_url = req.get("base_url") or DEFAULT_BASE_URL
    queries = req["queries"]
    max_c = max(1, min(int(req.get("max_concurrency", 4)), 12, len(queries)))
    timeout = int(req.get("timeout_sec", 25))
    fallback = req.get("fallback_engines", DEFAULT_FALLBACK_ENGINES)
    if req.get("no_fallback_engines"):
        fallback = None

    parallel = len(queries) > 1 and max_c > 1
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_c) as ex:
            futures = [ex.submit(_one_search, q, base_url, timeout, fallback)
                       for q in queries]
            responses = [f.result() for f in futures]
    else:
        responses = [_one_search(q, base_url, timeout, fallback) for q in queries]

    return {
        "responses": responses,
        "wall_ms": (max(r["elapsed_ms"] for r in responses) if parallel
                    else sum(r["elapsed_ms"] for r in responses)),
        "parallel": parallel,
    }


def _print_result(result: dict[str, Any], req: dict[str, Any]) -> None:
    responses = result["responses"]
    limit = int(req.get("limit", 10))
    if req.get("raw"):
        sys.stdout.write(json.dumps(responses, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return

    if len(responses) == 1:
        r = responses[0]
        out = _render_single(
            r, limit,
            int(req["queries"][0].get("page", 1)),
            req["queries"][0].get("time_range", ""),
            req["queries"][0].get("engines", ""),
        )
    elif req.get("merge"):
        out = _render_merged(responses, limit, result["parallel"])
    else:
        chunks = [
            f"## SearXNG: {len(responses)} "
            f"{'parallel' if result['parallel'] else 'serial'} queries "
            f"(wall {result['wall_ms']}ms, transport: python-urllib)",
            "",
        ]
        for r in responses:
            chunks.append(_render_single(
                r, limit,
                int(r.get("page", 1)),
                r.get("time_range", ""),
                r.get("engines", ""),
            ))
            chunks.extend(["", "---", ""])
        out = "\n".join(chunks)
    sys.stdout.write(out + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SearXNG search via Python urllib (stdlib only).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("query", nargs="?", help="Single search query")
    p.add_argument("--queries", nargs="+", help="Multiple queries for fan-out")
    p.add_argument("--stdin", action="store_true",
                   help="Read a JSON request from stdin instead of CLI args")
    p.add_argument("--category", default="general")
    p.add_argument("--language", default="all")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--time-range", default="",
                   choices=["", "day", "week", "month", "year"])
    p.add_argument("--safesearch", type=int, default=1, choices=[0, 1, 2])
    p.add_argument("--engines", default="")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--merge", action="store_true")
    p.add_argument("--max-concurrency", type=int, default=4)
    p.add_argument("--timeout", type=int, default=25)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--fallback-engines", default=DEFAULT_FALLBACK_ENGINES)
    p.add_argument("--no-fallback-engines", action="store_true")
    p.add_argument("--raw", action="store_true")
    return p


def _spec_from_args(a: argparse.Namespace, q: str) -> dict[str, Any]:
    return {
        "q": q, "category": a.category, "language": a.language,
        "page": a.page, "time_range": a.time_range,
        "safesearch": a.safesearch, "engines": a.engines,
    }


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 I/O on Windows so Chinese etc. render correctly regardless
    # of the console code page (Python 3.7+).
    for stream_name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    args = _build_parser().parse_args(argv)

    if args.stdin or (not args.query and not args.queries and not sys.stdin.isatty()):
        try:
            req = json.load(sys.stdin)
        except Exception as e:
            sys.stderr.write(f"Failed to parse stdin JSON: {e}\n")
            return 2
        result = run(req)
        _print_result(result, req)
        return 0

    if not args.query and not args.queries:
        sys.stderr.write("Provide a query or --queries or pipe JSON via stdin.\n")
        return 2

    qs = args.queries if args.queries else [args.query]
    req = {
        "base_url": args.base_url,
        "queries": [_spec_from_args(args, q) for q in qs],
        "limit": args.limit,
        "merge": args.merge,
        "max_concurrency": args.max_concurrency,
        "timeout_sec": args.timeout,
        "fallback_engines": args.fallback_engines,
        "no_fallback_engines": args.no_fallback_engines,
        "raw": args.raw,
    }
    result = run(req)
    _print_result(result, req)
    return 0


if __name__ == "__main__":
    sys.exit(main())
