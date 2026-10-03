"""Runner-only helpers and local test adapter for the actual POSIX shell backend.

This file is never sent to Helios. Production SSH sends only .sh sources.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

MARKER = "PYWEB_LAB1_DEPLOYMENT_OK"


def identifier(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", value):
        raise ValueError("Invalid release/channel identifier")
    return value


def metadata(directory):
    path = directory / "deployment.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if (directory / "index.html").is_file():
        return {"release": "legacy", "marker": MARKER}
    return None


def shell_executable():
    candidate = shutil.which("sh")
    if candidate:
        return candidate
    if os.name == "nt":
        for directory in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("LOCALAPPDATA", "")):
            candidate = Path(directory) / "Git/bin/sh.exe"
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError("Local release tests require POSIX sh (Linux or Git for Windows)")


def shell_path(path):
    path = Path(path).absolute().as_posix()
    if os.name == "nt" and re.match(r"^[A-Za-z]:/", path):
        return "/" + path[0].lower() + path[2:]
    return path


class ReleaseStore:
    """Local adapter; every operation executes the same shell code as SSH.

    Failure injection rewrites comment hooks in the local in-memory fixture,
    not production files or a remote configuration flag.
    """

    def __init__(self, root, state, failpoint=None):
        self.root = Path(root).absolute()
        self.state = Path(state).absolute()
        self.failpoint = failpoint or (lambda _: None)

    def target(self, channel):
        identifier(channel)
        return self.root if channel == "main" else self.root / "previews" / channel

    def run(self, action, channel="main", release=""):
        identifier(channel)
        if release:
            identifier(release)
        operation = uuid.uuid4().hex
        source = Path(__file__).with_suffix(".sh").read_text(encoding="utf-8")
        injected = None
        if action in {"activate", "rollback"}:
            for phase in ("old-moved", "new-moved"):
                try:
                    self.failpoint(phase)
                except (RuntimeError, SystemExit) as error:
                    injected = error
                    command = "kill -9 $$" if isinstance(error, SystemExit) else "exit 97"
                    source = source.replace("# FAILPOINT " + phase, command)
                    break
        source += '\nroot=$2; state=$3; run_action "$1" "$4" "$5" "$6"\n'
        shell = shell_executable()
        env = os.environ.copy()
        if os.name == "nt":
            utilities = Path(shell).parent.parent / "usr/bin"
            env["PATH"] = str(utilities) + os.pathsep + env.get("PATH", "")
        response = subprocess.run([shell, "-s", "--", action, shell_path(self.root), shell_path(self.state), channel, release, operation], input=source, encoding="utf-8", capture_output=True, env=env)
        if response.returncode:
            if injected:
                raise injected
            raise ValueError(response.stderr.strip())
        try:
            from .deploy_helios import parse_remote_output
        except ImportError:
            from deploy_helios import parse_remote_output
        result = parse_remote_output(response.stdout)
        for key, path in (("stage", self.state / "staging" / release), ("root", self.root)):
            if key in result:
                if result[key] != shell_path(path):
                    raise ValueError("Unexpected local shell result")
                result[key] = str(path)
        return result

    def prepare(self, channel, release):
        return self.run("prepare", channel, release)

    def activate(self, channel, release):
        return self.run("activate", channel, release)

    def rollback(self, channel, expected_release=None):
        return self.run("rollback", channel, expected_release or "")

    def recover(self, channel="main"):
        return self.run("recover", channel)
