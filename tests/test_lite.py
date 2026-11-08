"""Tests for Termômetro Lite. Standard library only; every test runs in a throwaway config dir."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSLINE = os.path.join(ROOT, "lite", "statusline.py")
INSTALL = os.path.join(ROOT, "lite", "install.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=self.home, HOME=self.home, USERPROFILE=self.home,
                        NO_COLOR="1", COLUMNS="160", TERMOMETRO_LANG="en", PYTHONIOENCODING="utf-8")
        self.env.pop("ANTHROPIC_API_KEY", None)

    def tearDown(self):
        time.sleep(0.2)          # let the background --recompute finish before the temp dir goes away
        self.tmp.cleanup()

    def run_py(self, script, *args, stdin=""):
        p = subprocess.run([sys.executable, script, *args], input=stdin, capture_output=True, text=True,
                           env=self.env, encoding="utf-8", timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def status(self, payload, columns=160):
        self.env["COLUMNS"] = str(columns)
        return self.run_py(STATUSLINE, stdin=json.dumps(payload))


class StatusLine(Base):
    def test_version(self):
        self.assertIn("termometro", self.run_py(STATUSLINE, "--version"))

    def test_shows_official_limits(self):
        out = self.status({"rate_limits": {"five_hour": {"used_percentage": 42.4}, "seven_day": {"used_percentage": 71}}})
        self.assertIn("42%", out)
        self.assertIn("71%", out)

    def test_empty_input_does_not_crash(self):
        self.run_py(STATUSLINE, stdin="")
        self.run_py(STATUSLINE, stdin="not json")

    def test_narrow_terminal_fits(self):
        out = self.status({"rate_limits": {"five_hour": {"used_percentage": 97}, "seven_day": {"used_percentage": 88}}}, 60)
        self.assertTrue(all(len(line) <= 60 for line in out.splitlines()), out)

    def test_heavy_chat_suggests_clear(self):
        path = os.path.join(self.home, "chat.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"message": {"usage": {"input_tokens": 300_000, "cache_read_input_tokens": 250_000}}}) + "\n")
        out = self.status({"transcript_path": path})
        self.assertIn("/clear", out)

    def test_todays_tokens_from_local_logs(self):
        proj = os.path.join(self.home, "projects", "demo")
        os.makedirs(proj)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"requestId": f"r{i}", "timestamp": now,
                                    "message": {"usage": {"input_tokens": 1000, "output_tokens": 500}}}) + "\n")
            f.write(json.dumps({"requestId": "r0", "timestamp": now,          # duplicate request: counted once
                                "message": {"usage": {"input_tokens": 1000, "output_tokens": 500}}}) + "\n")
        self.run_py(STATUSLINE, "--recompute")
        with open(os.path.join(self.home, "termometro", "lite-cache.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["today"], 4500)


class Installer(Base):
    def settings(self):
        with open(os.path.join(self.home, "settings.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_install_backs_up_and_uninstall_restores(self):
        previous = {"type": "command", "command": "echo my-old-line"}
        with open(os.path.join(self.home, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"statusLine": previous, "theme": "dark"}, f)
        self.run_py(INSTALL)
        s = self.settings()
        self.assertIn("statusline.py", s["statusLine"]["command"])
        self.assertEqual(s["theme"], "dark")                       # other settings untouched
        self.assertTrue(any(n.startswith("settings.json.termometro-backup-") for n in os.listdir(self.home)))
        self.run_py(INSTALL, "--uninstall")
        self.assertEqual(self.settings()["statusLine"], previous)

    def test_check_changes_nothing(self):
        self.run_py(INSTALL, "--check")
        self.assertFalse(os.path.exists(os.path.join(self.home, "settings.json")))


if __name__ == "__main__":
    unittest.main()
