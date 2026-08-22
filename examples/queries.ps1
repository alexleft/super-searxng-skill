# Example queries for super-searxng-skill
#
# These are illustrative -- copy/paste and adapt. The examples assume the
# skill is installed at C:\Users\<you>\.dsh\skills\searxng (Windows) or
# ~/.dsh/skills/searxng (Unix); substitute your own install path.

# --- Windows / PowerShell ---------------------------------------------------

# Single Chinese query
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "DeepSeek V4 Flash 评测" -Language zh-CN -Limit 5

# Single English programming query, IT category
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "typescript 5.5 release notes" -Category it -Language en

# Image search
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "system architecture diagram" -Category images -Limit 8

# Recent news (last week)
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "AI regulation EU" -Category news -TimeRange week -Language en

# Fan-out: 5 queries in parallel, merged + deduplicated
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Queries @(
        "Qwen3.8-27b benchmark",
        "deepseek-v4-flash 0731 benchmark",
        "Qwen3.8 27b vs deepseek benchmark comparison",
        "deepseek-v4-flash 评测 benchmark",
        "Qwen3.8-27b 评测 基准测试"
    ) `
    -Language en -Merge -Limit 8 -MaxConcurrency 5 -Timeout 25

# Pin engines (disables auto-fallback)
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "react useEffect cleanup" -Engines "bing,mdn,stackoverflow"

# Raw JSON output (for programmatic consumption)
& "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" `
    -Query "test" -Raw | ConvertFrom-Json

# JSON request via stdin (different category/language per query)
Get-Content examples\request.json -Raw |
    & "$env:USERPROFILE\.dsh\skills\searxng\searxng.ps1" -Stdin

# --- Unix / bash ------------------------------------------------------------

# Single query
~/.dsh/skills/searxng/bin/searxng "DeepSeek V4 Flash 评测" --language zh-CN

# Fan-out, merged
~/.dsh/skills/searxng/bin/searxng \
    --queries "Qwen3.8 benchmark" "DeepSeek V4 benchmark" \
    --merge --limit 8 --max-concurrency 3

# JSON via stdin
~/.dsh/skills/searxng/bin/searxng --stdin < examples/request.json
