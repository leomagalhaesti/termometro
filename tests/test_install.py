"""End-to-end install test, run on Linux, macOS and Windows by CI.

Reproduces the real-world failures we have seen on Windows:
  * Git Bash deletes backslashes, so the status line command must use forward slashes
  * settings.json saved by Notepad / PowerShell 5 starts with a UTF-8 BOM
  * folders with spaces and accents (C:/Users/José Ávila/...)
  * the console code page is not UTF-8, so printing block characters used to crash the bar
Everything runs in throwaway folders; the real ~/.claude is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "lite") if os.path.isdir(os.path.join(REPO, "lite")) else os.path.join(REPO, "scripts")
SAMPLE = {
    "model": {"display_name": "Opus · ünïcode"},
    "workspace": {"current_dir": "C:/Users/José Ávila/projeto"},
    "session_id": "ci",
    "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": 4102444800},
                    "seven_day": {"used_percentage": 67, "resets_at": 4102444800}},
}


def run(args, env, stdin=b""):
    return subprocess.run(args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=90)


class InstallEndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="termo ção ")
        ignore = shutil.ignore_patterns("__pycache__", "*.bak*", ".pytest_cache", "tests", "dist", "marketing")
        dest = os.path.join(self.root, "skill folder ção", "termometro")
        if SRC.endswith("scripts"):  # Pro: copy the whole skill (VERSION, pricing.json next to scripts/)
            shutil.copytree(os.path.dirname(SRC), dest, ignore=ignore)
            self.skill = os.path.join(dest, "scripts")
        else:
            shutil.copytree(SRC, dest, ignore=ignore)
            self.skill = dest
        self.cfg = os.path.join(self.root, "config José")
        os.makedirs(self.cfg)
        self.settings = os.path.join(self.cfg, "settings.json")
        previous = {"type": "command", "command": "echo previous"}
        with open(self.settings, "wb") as f:  # BOM + accents, like PowerShell 5 / Notepad
            f.write(b"\xef\xbb\xbf" + json.dumps({"nota": "ação", "statusLine": previous}, ensure_ascii=False).encode("utf-8"))
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, TERMOMETRO_DATA=os.path.join(self.root, "data"),
                        TERMOMETRO_NO_NOTIFY="1", COLUMNS="120", PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        self.installer = os.path.join(self.skill, "install.py")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def settings_json(self):
        with open(self.settings, encoding="utf-8-sig") as f:
            return json.load(f)

    def test_install_selftest_doctor_uninstall(self):
        r = run([sys.executable, self.installer], self.env)
        out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("Self-test passed", out)

        data = self.settings_json()
        self.assertEqual(data["nota"], "ação")  # accents preserved
        cmd = data["statusLine"]["command"]
        self.assertNotIn("\\", cmd, "backslashes are deleted by Git Bash on Windows")
        with open(self.settings, "rb") as f:
            self.assertNotEqual(f.read(3), b"\xef\xbb\xbf", "written without BOM")

        sys.path.insert(0, self.skill)
        try:
            import install as inst  # noqa: E402  (same module the user runs)
            shell = inst.find_shell()
        finally:
            sys.path.remove(self.skill)
            sys.modules.pop("install", None)
            sys.modules.pop("termometro_core", None)
        self.assertTrue(shell, "Git Bash must be found on Windows runners")
        bar = run([shell, "-c", cmd], self.env, json.dumps(SAMPLE, ensure_ascii=False).encode("utf-8"))
        text = bar.stdout.decode("utf-8")  # must be valid UTF-8 even with a cp1252 console
        self.assertEqual(bar.returncode, 0, bar.stderr.decode("utf-8", "replace"))
        self.assertIn("42", text)
        self.assertIn("67", text)

        d = run([sys.executable, self.installer, "--doctor"], self.env)
        self.assertEqual(d.returncode, 0, d.stdout.decode("utf-8", "replace"))

        u = run([sys.executable, self.installer, "--uninstall"], self.env)
        self.assertEqual(u.returncode, 0, u.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.settings_json()["statusLine"]["command"], "echo previous")

    def test_broken_json_is_never_overwritten(self):
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write('{"oops": ')
        r = run([sys.executable, self.installer], self.env)
        self.assertNotEqual(r.returncode, 0)
        with open(self.settings, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"oops": ')

    def test_bar_survives_garbage_stdin(self):
        sl = os.path.join(self.skill, "statusline.py")
        for payload in (b"", b"not json", b"\xff\xfe\x00bad", b"[]"):
            r = run([sys.executable, sl], self.env, payload)
            self.assertEqual(r.returncode, 0, (payload, r.stderr.decode("utf-8", "replace")))

    def test_many_chats_at_once(self):
        """Several Claude Code chats refresh the bar at the same moment (and a background recompute writes
        the cache). On Windows a file being read cannot be replaced; the bar must still never be empty."""
        sl = os.path.join(self.skill, "statusline.py")
        stdin = json.dumps(SAMPLE, ensure_ascii=False).encode("utf-8")
        for _ in range(3):
            procs = [subprocess.Popen([sys.executable, sl], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, env=self.env) for _ in range(8)]
            procs += [subprocess.Popen([sys.executable, sl, "--recompute"], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env) for _ in range(2)]
            for p in procs:
                out, err = p.communicate(None if p.stdin is None else stdin, timeout=90)
                self.assertEqual(p.returncode, 0, err.decode("utf-8", "replace"))
                if p.args[-1] != "--recompute":
                    self.assertTrue(out.strip(), "empty bar")
                    self.assertNotIn(b"Run install.py --doctor", out, out.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
