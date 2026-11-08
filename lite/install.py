#!/usr/bin/env python3
"""Install or remove the Termômetro Lite status line in Claude Code.

  python3 install.py              # install (backs up settings.json first)
  python3 install.py --uninstall  # restore your previous status line
  python3 install.py --check      # show what is configured, change nothing
"""
import json
import os
import shutil
import sys
import time

CLAUDE = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
DATA = os.environ.get("TERMOMETRO_DATA") or os.path.join(CLAUDE, "termometro")

SETTINGS = os.path.join(CLAUDE, "settings.json")
SAVED = os.path.join(DATA, "previous-statusline.json")
STATUSLINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")
def quote(path):
    return f'"{path}"' if " " in path else path


def load():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError:
        sys.exit(f"{SETTINGS} is not valid JSON. Nothing was changed.")


def save(settings):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    if os.path.exists(SETTINGS):
        backup = f"{SETTINGS}.termometro-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(SETTINGS, backup)
        print(f"Backup: {backup}")
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def ours(entry):
    return isinstance(entry, dict) and "statusline.py" in str(entry.get("command", "")) and "termometro" in str(entry.get("command", "")).lower()


def install():
    settings = load()
    current = settings.get("statusLine")
    if current and not ours(current):
        os.makedirs(DATA, exist_ok=True)
        with open(SAVED, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        print(f"Your previous status line was saved to {SAVED}")
    settings["statusLine"] = {"type": "command", "command": f"{quote(sys.executable)} {quote(STATUSLINE)}", "padding": 0}
    save(settings)
    print("Termômetro status line installed. It appears on your next Claude Code message.")


def uninstall():
    settings = load()
    if not ours(settings.get("statusLine")):
        print("Termômetro is not the active status line. Nothing to do.")
        return
    if os.path.exists(SAVED):
        with open(SAVED, encoding="utf-8") as f:
            settings["statusLine"] = json.load(f)
        print("Restored your previous status line.")
    else:
        settings.pop("statusLine", None)
    save(settings)
    print("Termômetro status line removed. Your history in", DATA, "was kept.")


def check():
    entry = load().get("statusLine")
    print("settings:", SETTINGS)
    print("status line:", json.dumps(entry) if entry else "(none)")
    print("termometro active:", ours(entry))


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    elif "--check" in sys.argv:
        check()
    else:
        install()
