#!/usr/bin/env python3
"""Termômetro Lite: a calm status line for Claude Code.

Shows your official 5-hour and weekly plan limits, how heavy the current chat
is, and today's tokens against your own normal. One file, zero dependencies.

Termômetro Pro adds: pace forecast ("your week runs out Fri 07:46"), daily
quota until reset, desktop alerts, prompt-cache expiry, the API value of each
chat, the /termometro command and the full dashboard.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# Claude Code reads the status line as UTF-8. Windows pipes default to the ANSI code page, so a single
# block character, accent or emoji would raise UnicodeEncodeError and the bar would silently vanish.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def write_json(path, data):
    """Atomic and safe when several Claude Code chats run the bar at once: a unique temp file per process,
    retries while Windows keeps the target locked by a reader, and never raises (the bar must not vanish)."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        for _ in range(10):
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:
                time.sleep(0.05)
    except OSError:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def read_stdin_json():
    """Claude Code sends UTF-8 JSON. Decode bytes ourselves (Windows would use cp1252) and never crash."""
    try:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
        data = json.loads(raw.decode("utf-8-sig", "replace") or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}

VERSION = "2.3.0-lite"
CLAUDE = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
DATA = os.environ.get("TERMOMETRO_DATA") or os.path.join(CLAUDE, "termometro")
CACHE = os.path.join(DATA, "lite-cache.json")

HUD = [(98, 214, 142), (247, 196, 72), (250, 140, 64), (245, 86, 86)]
LABEL, SUB, BORDER, TRACK_BG = (150, 162, 182), (178, 186, 199), (84, 92, 108), (14, 16, 20)
WHITE = (255, 255, 255)
PLAN_RGB = {"PRO": (196, 104, 74), "MAX": (150, 112, 36), "TEAM": (32, 128, 124), "ENTERPRISE": (74, 86, 112), "API": (70, 96, 140)}
# 24-bit color unless the terminal is known not to have it (macOS Terminal.app does not set COLORTERM and maps to 256)
TRUECOLOR = bool(os.environ.get("TERMOMETRO_TRUECOLOR")) or (
    os.environ.get("COLORTERM", "truecolor").lower() in ("truecolor", "24bit")
    and os.environ.get("TERM_PROGRAM") != "Apple_Terminal" and not os.environ.get("TERMOMETRO_256"))
# background work must never flash a console window on Windows
QUIET = {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}


def light_theme():
    t = os.environ.get("TERMOMETRO_THEME", "").lower()
    if t in ("light", "dark"):
        return t == "light"
    return os.environ.get("COLORFGBG", "").split(";")[-1] in ("7", "15")


if light_theme():
    HUD = [(22, 140, 72), (168, 112, 0), (196, 88, 20), (196, 40, 40)]
    LABEL, SUB, BORDER, TRACK_BG = (96, 104, 118), (96, 104, 118), (168, 174, 186), (222, 226, 232)

T = {
    "en": {"week": "WEEK", "week_s": "WK", "block": "5H", "resets": "resets", "at": "at", "ctx": "CONTEXT", "ctx_s": "CTX",
           "today": "TODAY", "ratio": ["low", "normal", "high", "very high"], "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
           "pro": "+ Termômetro Pro: ≈ msgs left · forecast · dashboard", "name": "termometro lite"},
    "pt": {"week": "SEMANA", "week_s": "SEM", "block": "5H", "resets": "renova", "at": "às", "ctx": "CONTEXTO", "ctx_s": "CTX",
           "today": "HOJE", "ratio": ["baixo", "normal", "alto", "muito alto"], "days": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"],
           "pro": "+ Termômetro Pro: ≈ msgs · previsão · painel", "name": "termômetro lite"},
}


def lang():
    forced = os.environ.get("TERMOMETRO_LANG")
    if forced in T:
        return forced
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if os.environ.get(var):
            return "pt" if os.environ[var].lower().startswith("pt") else "en"
    try:  # Windows and macOS apps often have no LANG; ask the system (Windows says "Portuguese_Brazil")
        import locale
        loc = (locale.getlocale()[0] or "").lower()
    except (ValueError, ImportError):
        loc = ""
    return "pt" if loc.startswith(("pt", "portuguese")) else "en"


def t(k):
    return T[lang()][k]


def _code(rgb, base):
    if TRUECOLOR:
        return f"{base};2;{rgb[0]};{rgb[1]};{rgb[2]}"
    return f"{base};5;{16 + sum(m * round(c / 255 * 5) for m, c in zip((36, 6, 1), rgb))}"


def sty(text, fgc=None, bgc=None, bold=False):
    if os.environ.get("NO_COLOR") or not text:
        return text
    codes = (["1"] if bold else []) + ([_code(fgc, "38")] if fgc else []) + ([_code(bgc, "48")] if bgc else [])
    return f"\033[{';'.join(codes)}m{text}\033[0m" if codes else text


def vlen(text):
    import re
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


def pad(text, n):
    return text + " " * max(0, n - vlen(text))


def kfmt(n):
    if n >= 1_000_000:
        s = f"{n / 1_000_000:.1f}M"
        return s.replace(".", ",") if lang() == "pt" else s
    return f"{n / 1000:.0f}k" if n >= 1_000 else str(int(n))


def bar(pct, level, width):
    if os.environ.get("NO_COLOR"):
        n = max(0, min(width, round(pct / 100 * width)))
        return "█" * n + "░" * (width - n) + " "
    units = max(0, min(width * 8, round(pct / 100 * width * 8)))
    full, part = divmod(units, 8)
    out = sty("▕", TRACK_BG) + sty("█" * full, HUD[level], TRACK_BG)
    if full < width:
        out += sty(" ▏▎▍▌▋▊▉"[part] if part else " ", HUD[level], TRACK_BG) + sty(" " * (width - full - 1), None, TRACK_BG)
    return out + sty("▏", TRACK_BG)


def plan_name():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    for path in ([os.path.join(cfg, ".claude.json")] if cfg else []) + [os.path.join(os.path.expanduser("~"), ".claude.json")]:
        try:
            with open(path, encoding="utf-8") as f:
                acct = json.load(f).get("oauthAccount") or {}
            break
        except (OSError, ValueError, AttributeError):
            acct = {}
    kind = (acct.get("organizationType") or "").lower()
    tier = " ".join(str(acct.get(k) or "") for k in ("userRateLimitTier", "organizationRateLimitTier")).lower()
    if "max" in kind or "max" in tier:
        return "MAX 20×" if "20x" in tier else "MAX 5×" if "5x" in tier else "MAX"
    for key in ("enterprise", "team", "pro"):
        if key in kind:
            return key.upper()
    return "API" if os.environ.get("ANTHROPIC_API_KEY") else None


def when(ts):
    d, now = datetime.fromtimestamp(ts), datetime.now()
    return ("" if d.date() == now.date() else t("days")[d.weekday()] + " ") + f"{t('at')} {d:%H:%M}"


def level_pct(p):
    return 0 if p < 50 else 1 if p < 80 else 2 if p < 95 else 3


def recompute():
    """Tokens per day for today vs your 14-day normal (runs in the background)."""
    seen, days = set(), {}
    for path in glob.glob(os.path.join(CLAUDE, "projects", "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(path) < time.time() - 21 * 86400:
                continue
            fh = open(path, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("message") if isinstance(d.get("message"), dict) else {}
                u, key = msg.get("usage"), d.get("requestId") or msg.get("id")
                if not isinstance(u, dict) or key in seen or not d.get("timestamp"):
                    continue
                seen.add(key)
                try:
                    day = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone().date().isoformat()
                except ValueError:
                    continue
                days[day] = days.get(day, 0) + sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "output_tokens"))
    today = datetime.now().astimezone().date().isoformat()
    before = [v for d, v in sorted(days.items()) if d < today and v][-14:]
    write_json(CACHE, {"day": today, "today": days.get(today, 0), "normal": sum(before) / len(before) if before else 0, "at": time.time()})


def context(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            lines = f.read().decode(errors="ignore").splitlines()
    except (OSError, TypeError):
        return 0
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain") or not isinstance(d.get("message"), dict):
            continue
        u = d["message"].get("usage")
        if u:
            return sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return 0


def render(data, width, mode):
    """mode: full | compact | mini."""
    compact, mini = mode != "full", mode == "mini"
    limits = data.get("rate_limits") or {}
    week, ctxl = (t("week_s"), t("ctx_s")) if mini else (t("week"), t("ctx"))
    w0, w1 = max(len(t("block")), len(t("today"))), max(len(week), len(ctxl))
    gw = 5 if mini else 8 if compact else 12
    lab = lambda x, w: sty(x.ljust(w), LABEL, None, True) + " "
    worst, row1 = 0, []
    for key, label, lw in (("five_hour", t("block"), w0), ("seven_day", week, w1)):
        w = limits.get(key)
        if not isinstance(w, dict) or w.get("used_percentage") is None:
            continue
        used = round(w["used_percentage"])
        lvl = level_pct(used)
        worst = max(worst, lvl)
        cell = lab(label, lw) + bar(used, lvl, gw) + sty(f"{used}%", HUD[lvl] if lvl else None, None, True)
        if w.get("resets_at") and not compact:
            cell += sty(f"  {t('resets')} {when(w['resets_at'])}", SUB)
        row1.append(cell)
    ctx = context(data.get("transcript_path"))
    clvl = 0 if ctx < 100_000 else 1 if ctx < 250_000 else 2 if ctx < 500_000 else 3
    row2 = []
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    today = datetime.now().astimezone().date().isoformat()
    if c.get("day") == today:
        cell = lab(t("today"), w0) + sty(kfmt(c.get("today", 0)), None, None, True)
        if c.get("normal") and not mini:
            r = c["today"] / c["normal"]
            tl = 0 if r < 0.8 else 1 if r < 1.1 else 2 if r < 1.5 else 3
            cell += " " + sty(t("ratio")[tl], HUD[tl] if tl >= 2 else SUB, None, tl >= 2)
        row2.append(cell)
    elif row1:
        row2.append("")   # keep CONTEXT under WEEK while today's total is still being computed
    cell = lab(ctxl, w1) + sty(kfmt(ctx), HUD[clvl] if clvl else None, None, True)
    if clvl >= 2:
        cell += sty(" → /clear", HUD[clvl], None, True)
    if not compact and worst >= 1:   # the moment people care about "will I make it?": show what Pro answers
        cell += "   " + sty(t("pro"), SUB)
    row2.append(cell)
    plan = plan_name()
    pbg = PLAN_RGB.get((plan or "").split()[0], (64, 71, 86)) if plan else None
    rows = [r for r in (row1, row2) if r]
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    widths = [max(vlen(r[i]) for r in rows) for i in range(ncol)]
    bc = BORDER if worst < 2 else HUD[worst]
    sep = " " + sty("│", bc) + " "
    if os.environ.get("NO_COLOR") or mini:
        badge = (sty(f" {plan.split()[0][:3]} ", WHITE, pbg, True) + " ") if plan and not os.environ.get("NO_COLOR") else ""
        return [(badge if i == 0 else " " * vlen(badge)) + sep.join(pad(x, widths[j]) for j, x in enumerate(r)).rstrip()
                for i, r in enumerate(rows)]
    body = [" " + sep.join(pad(x, widths[i]) for i, x in enumerate(r)) + " " for r in rows]
    inner = max(vlen(x) for x in body)
    left = sty(f" ◆ {plan} ", WHITE, pbg, True) if plan else ""
    right = sty(f" {t('name')} ", LABEL)
    inner = max(inner, vlen(left) + vlen(right) + 3)
    room = inner - vlen(left) - vlen(right) - 1
    b = lambda x: sty(x, bc)
    return ([b("╭─") + left + b("─" * max(1, room - 1)) + right + b("─╮")] + [b("│") + pad(x, inner) + b("│") for x in body]
            + [b("╰" + "─" * inner + "╯")])


def main():
    if sys.argv[1:2] == ["--version"]:
        print("termometro", VERSION)
        return
    if sys.argv[1:2] == ["--recompute"]:
        recompute()
        return
    data = read_stdin_json()
    width = int(os.environ.get("COLUMNS") or 0) or shutil.get_terminal_size((140, 20)).columns
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    if c.get("day") != datetime.now().astimezone().date().isoformat() or time.time() - c.get("at", 0) > 300:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--recompute"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **QUIET)
    for mode in ("full", "compact", "mini"):
        out = render(data, width, mode)
        if max(vlen(x) for x in out) <= width or mode == "mini":
            break
    print("\n".join(out))

if __name__ == "__main__":
    try:
        main()
    except Exception as _e:  # never leave Claude Code with an empty bar; say how to diagnose instead
        if "--recompute" not in sys.argv and "--timer" not in sys.argv:
            print(f"Termômetro: {type(_e).__name__}. Run install.py --doctor")
