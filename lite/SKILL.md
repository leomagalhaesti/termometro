---
name: termometro-lite
description: A calm, color-graded status line for Claude Code that shows your official 5-hour and weekly plan limits, how heavy the current chat is, and today's tokens against your own normal. Use when the user wants to see their Claude Code limits or token usage in the status line.
version: 2.3.0
license: LICENSE
metadata:
  version: "2.3.0"
  author: Leonardo Magalhães
---

# Termômetro Lite

One Python file, zero dependencies, nothing leaves your machine.

Pick the Python command that works on this machine: try `python3 --version`, then `python --version`,
then `py --version` (Windows). On Windows, skip a `python`/`python3` that prints nothing or opens the
Microsoft Store: that is an alias, not Python. Then run once, with the path in quotes:

```bash
python3 "<this skill's directory>/install.py"
```

It backs up `~/.claude/settings.json`, saves any existing status line, activates Termômetro and then
**tests the bar exactly the way Claude Code runs it** (Git Bash on Windows). Expect `Self-test passed`.
No restart is needed: the bar shows up on the next message.

If the self-test fails or the bar is missing, run `python3 "<this skill's directory>/install.py" --doctor`
and follow the line that starts with `->`. Never edit the status line command by hand on Windows: Git Bash
deletes backslashes, so the installer writes forward slashes (`C:/Users/...`) on purpose.

Undo with `install.py --uninstall` (restores the previous status line). `--check` shows what is configured.

Language follows the system (English or Portuguese); force with `TERMOMETRO_LANG=en`.
`NO_COLOR=1` removes colors.

**Termômetro Pro** adds the pace forecast ("your week runs out Fri 07:46"), a daily
quota until the reset, desktop alerts, prompt-cache expiry, the API value of each
chat, the `/termometro` command and the full dashboard.
