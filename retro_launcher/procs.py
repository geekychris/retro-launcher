# SPDX-License-Identifier: MIT
"""Start, watch and stop the emulator processes.

Each platform launch is a short list of steps: the optional "prepare"
shell commands (run to completion, in order) and then the emulator
itself, which keeps running. Output from every step goes to a log file
per platform so a failed start can be read from the config screen.
"""
import os
import shlex
import signal
import subprocess
import sys
import threading
import time

WINDOWS = sys.platform.startswith("win")


def split(cmd):
    """A command is either a list or one shell-style string."""
    if isinstance(cmd, (list, tuple)):
        return [str(c) for c in cmd]
    return shlex.split(cmd, posix=not WINDOWS)


class Launch:
    """One platform's running (or finished) launch."""

    def __init__(self, key, log_path):
        self.key = key
        self.log_path = log_path
        self.proc = None
        self.state = "idle"       # idle, preparing, running, exited, failed
        self.message = ""
        self.started = 0.0
        self.stop_requested = False
        self._thread = None

    @property
    def alive(self):
        return self.state in ("preparing", "running")

    def uptime(self):
        return time.time() - self.started if self.alive else 0.0

    def _log(self, text):
        with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(text)

    def start(self, prepare, command, cwd, env):
        if self.alive:
            return
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("== %s  %s\n" % (self.key, time.strftime("%Y-%m-%d %H:%M:%S")))
        self.stop_requested = False
        self.started = time.time()
        self.state = "preparing"
        self.message = "starting"
        self._thread = threading.Thread(
            target=self._run, args=(prepare, command, cwd, env), daemon=True)
        self._thread.start()

    def _popen(self, argv, cwd, env):
        out = open(self.log_path, "a", encoding="utf-8", errors="replace")
        kw = {}
        if WINDOWS:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        try:
            return subprocess.Popen(argv, cwd=cwd or None, env=env, stdout=out,
                                    stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, **kw)
        finally:
            out.close()

    def _run(self, prepare, command, cwd, env):
        try:
            for step in prepare:
                if self.stop_requested:
                    self.state, self.message = "exited", "cancelled"
                    return
                argv = split(step)
                if not argv:
                    continue
                self._log("\n$ %s\n" % " ".join(shlex.quote(a) for a in argv))
                self.message = "preparing: " + os.path.basename(argv[0])
                p = self._popen(argv, cwd, env)
                self.proc = p
                rc = p.wait()
                if rc != 0:
                    self.state = "failed"
                    self.message = "%s exited %d" % (os.path.basename(argv[0]), rc)
                    self._log("\n[exit %d]\n" % rc)
                    return
            argv = split(command)
            self._log("\n$ %s\n" % " ".join(shlex.quote(a) for a in argv))
            self.proc = self._popen(argv, cwd, env)
            self.state, self.message = "running", "running"
            rc = self.proc.wait()
            self._log("\n[exit %d]\n" % rc)
            if self.stop_requested or rc == 0:
                self.state, self.message = "exited", "stopped"
            else:
                self.state, self.message = "failed", "exited with code %d" % rc
        except FileNotFoundError as e:
            self.state = "failed"
            self.message = "not found: %s" % (e.filename or e)
            self._log("\n%s\n" % e)
        except Exception as e:  # keep the UI alive whatever happens
            self.state, self.message = "failed", str(e)
            self._log("\n%s\n" % e)

    def stop(self, grace=4.0):
        self.stop_requested = True
        p = self.proc
        if not p or p.poll() is not None:
            return
        try:
            if WINDOWS:
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(p.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

        def reap():
            try:
                p.wait(grace)
            except subprocess.TimeoutExpired:
                try:
                    if WINDOWS:
                        p.kill()
                    else:
                        os.killpg(p.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        threading.Thread(target=reap, daemon=True).start()

    def tail(self, lines=14):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-lines:]
        except OSError:
            return []


def find_processes(pattern):
    """PIDs (other than ours) whose command line contains `pattern`."""
    if not pattern:
        return []
    me = os.getpid()
    try:
        if WINDOWS:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | ForEach-Object "
                 "{ \"$($_.ProcessId) $($_.CommandLine)\" }"],
                capture_output=True, text=True, timeout=8).stdout
        else:
            out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True,
                                 text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    # The pattern's first word must be in the program or its first argument
    # (an interpreter's script), so a shell or editor whose command line
    # merely mentions the emulator doesn't count.
    first = pattern.split()[0]
    pids = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit() or pattern not in parts[1]:
            continue
        head = parts[1].split()[:2]
        if not any(first in h for h in head):
            continue
        pid = int(parts[0])
        if pid != me and "retro_launcher" not in parts[1]:
            pids.append(pid)
    return pids


def descendants(pid):
    """`pid` and every process under it (a start script's emulator)."""
    if WINDOWS:
        return [pid]
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return [pid]
    children = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [pid]
    while todo:
        p = todo.pop(0)
        found.append(p)
        todo.extend(children.get(p, []))
    return found


def _focus_one(pid):
    """Bring the window of process `pid` to the front; True if it worked."""
    try:
        if sys.platform == "darwin":
            script = (
                'tell application "System Events"\n'
                '  set p to first process whose unix id is %d\n'
                '  try\n'
                '    repeat with w in (every window of p)\n'
                '      set value of attribute "AXMinimized" of w to false\n'
                '    end repeat\n'
                '  end try\n'
                '  set frontmost of p to true\n'
                'end tell' % pid)
            r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return r.returncode == 0
        if WINDOWS:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(New-Object -ComObject WScript.Shell).AppActivate(%d)" % pid],
                capture_output=True, text=True, timeout=8)
            return r.stdout.strip().lower() == "true"
        # Linux / X11: wmctrl, else xdotool
        try:
            out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True,
                                 timeout=5).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) > 2 and parts[2] == str(pid):
                    subprocess.run(["wmctrl", "-ia", parts[0]], timeout=5)
                    return True
        except OSError:
            pass
        r = subprocess.run(["xdotool", "search", "--pid", str(pid), "windowactivate"],
                           capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def focus_pids(pids):
    """Bring forward the first of `pids` that owns a window."""
    for pid in pids:
        if _focus_one(pid):
            return True
    return False


def kill_pids(pids):
    for pid in pids:
        try:
            if WINDOWS:
                subprocess.run(["taskkill", "/PID", str(pid), "/T"], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


class Watcher:
    """Polls the process table in the background: which platforms have an
    emulator running that this launcher didn't start."""

    def __init__(self, patterns, interval=2.0):
        self.patterns = dict(patterns)      # key -> pattern
        self.found = {}                      # key -> [pids]
        self.interval = interval
        self._stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            found = {}
            for key, pat in list(self.patterns.items()):
                found[key] = find_processes(pat)
            self.found = found
            time.sleep(self.interval)

    def stop(self):
        self._stop = True
