"""SSH/rsync deploy, preview URL и откат Helios."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

PROJECT = "pyweb_lab1"


def allowed_paths(user):
    return {f"/home/studs/{user}/public_html/{PROJECT}", f"/export/home/studs/{user}/public_html/{PROJECT}"}


def branch_channel(branch, main_branch="main"):
    if not branch:
        raise ValueError("Branch name is required")
    if branch == main_branch:
        return "main"
    slug = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")[:40] or "branch"
    return slug + "-" + hashlib.sha256(branch.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    user: str
    path: str
    site_url: str

    @classmethod
    def from_environment(cls):
        for name in ("HELIOS_HOST", "HELIOS_DEPLOY_PATH", "HELIOS_SITE_URL", "HELIOS_USER", "HELIOS_SSH_KEY", "HELIOS_KNOWN_HOSTS"):
            if not os.environ.get(name):
                raise ValueError(name + " is not set")
        host, user = os.environ["HELIOS_HOST"], os.environ["HELIOS_USER"]
        path = os.environ["HELIOS_DEPLOY_PATH"].rstrip("/")
        url = os.environ["HELIOS_SITE_URL"]
        port = int(os.environ.get("HELIOS_PORT") or "2222")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
            raise ValueError("Invalid HELIOS_HOST")
        if not re.fullmatch(r"s[0-9]+", user):
            raise ValueError("Invalid HELIOS_USER")
        if not 1 <= port <= 65535:
            raise ValueError("Invalid HELIOS_PORT")
        if path not in allowed_paths(user):
            raise ValueError("HELIOS_DEPLOY_PATH must point exactly to this account's public_html/pyweb_lab1 directory")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment or not parsed.path.endswith(f"/{PROJECT}/"):
            raise ValueError("Invalid HELIOS_SITE_URL")
        return cls(host, port, user, path, url)

    @property
    def ssh_options(self):
        return ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-p", str(self.port)]

    def url(self, channel):
        return self.site_url if channel == "main" else self.site_url + "previews/" + channel + "/"


def remote_action(config, action, channel, release=""):
    source = "\n".join(Path(__file__).with_name(name).read_text(encoding="utf-8") for name in ("helios_release.sh", "helios_remote.sh"))
    command = shlex.join(["sh", "-s", "--", action, config.path, config.user, channel, release, uuid.uuid4().hex])
    response = subprocess.run(["ssh", *config.ssh_options, f"{config.user}@{config.host}", command], input=source, text=True, capture_output=True, check=True)
    return parse_remote_output(response.stdout)


def parse_remote_output(output):
    result = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in {"stage", "root", "release", "marker", "has_previous"} or key in result:
            raise ValueError("Unexpected remote response")
        if key == "has_previous" and value not in {"true", "false"}:
            raise ValueError("Invalid remote boolean")
        result[key] = value == "true" if key == "has_previous" else value
    if not result:
        raise ValueError("Empty remote response")
    return result


def deploy(config, site, channel="main", release=None):
    release = release or uuid.uuid4().hex
    site = Path(site).resolve()
    info = json.loads((site / "deployment.json").read_text(encoding="utf-8"))
    if info["release"] != release:
        raise ValueError("Build release does not match deployment release")
    started = time.perf_counter()
    prepared = remote_action(config, "prepare", channel, release)
    stage = prepared["stage"]
    expected_stages = {p.removesuffix("/public_html/" + PROJECT) + "/.pyweb_lab1-deploy/staging/" + release for p in allowed_paths(config.user)}
    if stage not in expected_stages:
        raise ValueError("Unexpected remote staging path; rsync was not started")
    receiver_script = f'test ! -L {shlex.quote(stage)} && cd -P {shlex.quote(stage)} && test "$(pwd -P)" = {shlex.quote(stage)} && exec rsync "$@"'
    receiver = shlex.join(["sh", "-c", receiver_script, "rsync"])
    subprocess.run(["rsync", "--archive", "--compress", "--one-file-system", "--chmod=D755,F644", "--rsync-path", receiver, "-e", shlex.join(["ssh", *config.ssh_options]), site.as_posix().rstrip("/") + "/", f"{config.user}@{config.host}:{stage}/"], check=True)
    uploaded = time.perf_counter()
    result = remote_action(config, "activate", channel, release)
    result["upload_seconds"] = round(uploaded - started, 6)
    result["activate_seconds"] = round(time.perf_counter() - uploaded, 6)
    return result


def outputs(values):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            for key, value in values.items():
                if isinstance(value, (str, bool, int, float)):
                    stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("configure", "deploy", "rollback", "recover"), default="deploy")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "main"))
    parser.add_argument("--main-branch", default=os.environ.get("MAIN_BRANCH", "main"))
    parser.add_argument("--release", default=os.environ.get("RELEASE_ID") or uuid.uuid4().hex)
    parser.add_argument("--expect-release", default="")
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--metrics-file", type=Path)
    args = parser.parse_args()
    try:
        try:
            from .helios_release import identifier
        except ImportError:
            from helios_release import identifier
        config = Config.from_environment()
        channel = branch_channel(args.branch, args.main_branch)
        identifier(args.release)
        result = {"channel": channel, "site_url": config.url(channel), "release": args.release}
        if args.validate_only or args.action == "configure":
            pass
        elif args.action == "deploy":
            result.update(deploy(config, args.site_dir, channel, args.release))
        elif args.action == "rollback":
            result.update(remote_action(config, "rollback", channel, args.expect_release))
        else:
            result.update(remote_action(config, "recover", channel))
        outputs(result)
        if args.metrics_file:
            args.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            args.metrics_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    except subprocess.CalledProcessError as error:
        print(f"HELIOS FAILED: command exited with {error.returncode}", file=sys.stderr)
        if error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print("HELIOS FAILED: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
