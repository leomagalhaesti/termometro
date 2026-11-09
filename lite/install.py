#!/usr/bin/env python3
"""Install or remove the Termômetro Lite status line in Claude Code (Windows, macOS, Linux).

  python3 install.py              # install, then test the bar exactly the way Claude Code runs it
  python3 install.py --uninstall  # restore your previous status line
  python3 install.py --doctor     # diagnose a missing bar and print the fix (changes nothing)
  python3 install.py --check      # show what is configured (changes nothing)

On Windows use `py install.py` or `python install.py`. No restart is needed: the bar appears on your
next Claude Code message.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

if sys.version_info < (3, 8):
    sys.exit("Termômetro needs Python 3.8 or newer. You are running " + platform.python_version() + ".")

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
# Every environment variable read here is listed; nothing else from the environment is read.
_SETTINGS = ("CLAUDE_CONFIG_DIR", "TERMOMETRO_DATA", "CLAUDE_CODE_GIT_BASH_PATH", "ProgramFiles", "ProgramFiles(x86)",
             "LOCALAPPDATA")


class core:  # same names as the Pro core module, kept tiny for Lite
    @staticmethod
    def setting(name, default=None):
        if name not in _SETTINGS:
            raise KeyError(name)
        return os.getenv(name, default)


core.CLAUDE = core.setting("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
core.DATA = core.setting("TERMOMETRO_DATA") or os.path.join(core.CLAUDE, "termometro")

SETTINGS = os.path.join(core.CLAUDE, "settings.json")
SAVED = os.path.join(core.DATA, "previous-statusline.json")
STATUSLINE = os.path.join(HERE, "statusline.py")
WINDOWS = os.name == "nt"


# ---------------------------------------------------------------- paths and the command line
def python_exe():
    """The interpreter running this installer, with a console (pythonw.exe has no stdout)."""
    exe = sys.executable or shutil.which("python3") or shutil.which("python") or "python3"
    folder, name = os.path.split(exe)
    if name.lower() == "pythonw.exe" and os.path.exists(os.path.join(folder, "python.exe")):
        exe = os.path.join(folder, "python.exe")
    return exe


def shell_path(path):
    """A path that survives the shell Claude Code uses (Git Bash on Windows, sh/bash/zsh elsewhere).

    Git Bash deletes backslashes (C:\\Users\\Ana -> C:UsersAna), so Windows paths use forward slashes,
    which Windows itself accepts. Spaces and shell characters are quoted for bash."""
    path = os.path.abspath(path)
    if WINDOWS:
        path = path.replace("\\", "/")
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,~-]+", path):
        return path
    return '"' + re.sub(r'(["$`\\])', r"\\\1", path) + '"'


def status_command():
    return f"{shell_path(python_exe())} {shell_path(STATUSLINE)}"


def ours(entry):
    if not isinstance(entry, dict):
        return False
    cmd = str(entry.get("command", "")).replace("\\", "/").lower()
    mine = os.path.abspath(STATUSLINE).replace("\\", "/").lower()
    return mine in cmd or ("statusline.py" in cmd and "termometro" in cmd)


# ---------------------------------------------------------------- settings.json, safely
def load():
    """Reads settings.json. utf-8-sig accepts the BOM that Notepad and PowerShell 5 add."""
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError:
        sys.exit(f"{SETTINGS} is not UTF-8 text. Nothing was changed. Open it, save it as UTF-8 and run again.")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        sys.exit(f"{SETTINGS} is not valid JSON ({e}). Nothing was changed. Fix that line and run again.")
    if not isinstance(data, dict):
        sys.exit(f"{SETTINGS} does not contain a JSON object. Nothing was changed.")
    return data


def save(settings):
    target = os.path.realpath(SETTINGS)  # keep a symlinked settings.json (dotfiles) as a symlink
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        backup = f"{SETTINGS}.termometro-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")
    tmp = target + ".termometro-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:  # UTF-8 without BOM, accents kept as-is
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    for attempt in range(10):  # Windows: the file may be open in an editor or in Claude Code for a moment
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            time.sleep(0.3)
    os.remove(tmp)
    sys.exit(f"Could not write {SETTINGS} (it is locked by another program). Close editors using it and run again.")


# ---------------------------------------------------------------- self-test: run the bar like Claude Code does
def find_shell():
    """The shell Claude Code uses for status line commands, or None."""
    if not WINDOWS:
        return shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    cands = [core.setting("CLAUDE_CODE_GIT_BASH_PATH")]
    for base in (core.setting("ProgramFiles"), core.setting("ProgramFiles(x86)"),
                 os.path.join(core.setting("LOCALAPPDATA") or "", "Programs")):
        if base:
            cands.append(os.path.join(base, "Git", "bin", "bash.exe"))
    found = shutil.which("bash")
    if found and "system32" not in found.lower():  # System32\\bash.exe is WSL, not Git Bash
        cands.append(found)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


SAMPLE = {"model": {"display_name": "Opus · test ünïcode"}, "workspace": {"current_dir": "C:/Users/José Ávila/projeto"},
          "rate_limits": {}, "session_id": "termometro-self-test"}


def self_test(command):
    """Runs the exact command from settings.json through Claude Code's shell, with a sample stdin.
    Uses a throwaway config folder so nothing is written to your real history."""
    shell = find_shell()
    if WINDOWS and not shell:
        return False, ("Git Bash was not found. Claude Code on Windows runs the status line through Git Bash: "
                       "install Git for Windows (git-scm.com) or set CLAUDE_CODE_GIT_BASH_PATH to bash.exe.")
    tmp = tempfile.mkdtemp(prefix="termometro-test-")
    env = dict(os.environ)  # passed through unchanged; only the config folder is redirected to the temp folder
    env.update({"CLAUDE_CONFIG_DIR": tmp, "TERMOMETRO_DATA": os.path.join(tmp, "data"), "COLUMNS": "120",
                "TERMOMETRO_NO_NOTIFY": "1"})
    try:
        r = subprocess.run([shell, "-c", command], input=json.dumps(SAMPLE, ensure_ascii=False).encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "The bar took more than 30 s to answer (antivirus scanning Python?). Run the doctor again."
    except OSError as e:
        return False, f"Could not start {shell}: {e}"
    finally:
        time.sleep(0.5)
        shutil.rmtree(tmp, ignore_errors=True)
    out = r.stdout.decode("utf-8", "replace").strip()
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode == 0 and out:
        return True, out
    hint = err.splitlines()[-1] if err else f"exit code {r.returncode}, no output"
    if "No such file" in err or "not found" in err or "cannot find" in err.lower():
        hint += "  -> a path in the command is wrong; run `install.py` again from the skill folder."
    return False, hint


def report_test(command):
    ok, info = self_test(command)
    if ok:
        print("Self-test passed: Claude Code will show the bar on your next message.")
    else:
        print("Self-test FAILED:", info)
        print("Run `install.py --doctor` for a full report.")
    return ok


# ---------------------------------------------------------------- actions
def install():
    settings = load()
    current = settings.get("statusLine")
    if current and not ours(current):
        os.makedirs(core.DATA, exist_ok=True)
        with open(SAVED, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        print(f"Your previous status line was saved to {SAVED}")
    settings["statusLine"] = {"type": "command", "command": status_command(), "padding": 0}
    save(settings)
    print("Termômetro status line installed. No restart needed.")
    ok = report_test(status_command())
    warn_overrides()
    return ok


def uninstall():
    settings = load()
    if not ours(settings.get("statusLine")):
        print("Termômetro is not the active status line. Nothing to do.")
        return
    if os.path.exists(SAVED):
        with open(SAVED, encoding="utf-8-sig") as f:
            settings["statusLine"] = json.load(f)
        print("Restored your previous status line.")
    else:
        settings.pop("statusLine", None)
    save(settings)
    print("Termômetro status line removed. Your history in", core.DATA, "was kept.")


def warn_overrides():
    """Project settings win over user settings: a statusLine there hides ours in that project."""
    for name in ("settings.json", "settings.local.json"):
        p = os.path.join(os.getcwd(), ".claude", name)
        try:
            with open(p, encoding="utf-8-sig") as f:
                if "statusLine" in json.load(f):
                    print(f"Note: {p} defines its own statusLine, which replaces Termômetro in this project.")
        except (OSError, ValueError):
            pass


def check():
    entry = load().get("statusLine")
    print("settings:", SETTINGS)
    print("status line:", json.dumps(entry, ensure_ascii=False) if entry else "(none)")
    print("termometro active:", ours(entry))


def doctor():
    print("Termômetro Lite doctor")
    print("system:", platform.system(), platform.release(), "| python:", platform.python_version(), python_exe())
    print("shell used by Claude Code:", find_shell() or "NOT FOUND")
    print("settings:", SETTINGS, "(exists)" if os.path.exists(SETTINGS) else "(missing)")
    if os.path.exists(SETTINGS):
        with open(SETTINGS, "rb") as f:
            if f.read(3) == b"\xef\xbb\xbf":
                print("  settings.json starts with a BOM (harmless for Termômetro; rewritten without it on install)")
    entry = load().get("statusLine")
    print("status line:", json.dumps(entry, ensure_ascii=False) if entry else "(none)")
    if not ours(entry):
        print("-> Termômetro is not installed as your status line. Run: install.py")
        return False
    cmd = entry.get("command", "")
    if WINDOWS and "\\" in cmd:
        print("-> The command uses backslashes, which Git Bash deletes. Run install.py again to fix it.")
    ok = report_test(cmd)
    warn_overrides()
    if ok:
        print("Everything looks right. If the bar is still missing, send any message in Claude Code to refresh it.")
    return ok


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    elif "--doctor" in sys.argv:
        sys.exit(0 if doctor() else 1)
    elif "--check" in sys.argv:
        check()
    else:
        sys.exit(0 if install() else 1)
