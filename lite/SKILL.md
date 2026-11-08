---
name: termometro-lite
description: A calm, color-graded status line for Claude Code that shows your official 5-hour and weekly plan limits, how heavy the current chat is, and today's tokens against your own normal. Use when the user wants to see their Claude Code limits or token usage in the status line.
version: 2.2.0
license: LICENSE
metadata:
  version: "2.2.0"
  author: Leonardo Magalhães
---

# Termômetro Lite

One Python file, zero dependencies, nothing leaves your machine.

Install (backs up `~/.claude/settings.json` and saves any existing status line):

```bash
python3 "<this skill's directory>/install.py"
```

Undo with `python3 install.py --uninstall` (restores the previous status line).

Language follows the system (English or Portuguese); force with `TERMOMETRO_LANG=en`.
`NO_COLOR=1` removes colors.

**Termômetro Pro** adds the pace forecast ("your week runs out Fri 07:46"), a daily
quota until the reset, desktop alerts, prompt-cache expiry, the API value of each
chat, the `/termometro` command and the full dashboard.
