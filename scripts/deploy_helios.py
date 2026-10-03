"""Проверка параметров Helios и синхронизация только каталога этой работы."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import urlsplit


PROJECT = "pyweb_lab1"

# Выполняется на сервере через POSIX sh; Python на Helios не требуется.
REMOTE_PREPARE = r"""set -eu
fail() { echo "$1" >&2; exit 1; }
requested=$1
account=$2
test "$(id -un)" = "$account" || fail 'Unexpected remote account'
home_dir=$(cd "$HOME" && pwd -P)
case "$home_dir" in
    "/home/studs/$account"|"/export/home/studs/$account") ;;
    *) fail 'Unexpected physical home directory' ;;
esac
requested_home=${requested%/public_html/pyweb_lab1}
test "$(cd "$requested_home" && pwd -P)" = "$home_dir" || fail 'Requested home does not match account home'
public_dir="$home_dir/public_html"
target="$public_dir/pyweb_lab1"
test ! -L "$public_dir" || fail 'public_html must not be a symbolic link'
test ! -L "$target" || fail 'Project directory must not be a symbolic link'
mkdir -p "$target"
test "$(cd "$public_dir" && pwd -P)" = "$public_dir" || fail 'Unexpected physical public_html path'
test "$(cd "$target" && pwd -P)" = "$target" || fail 'Unexpected physical project path'
chmod 755 "$public_dir" "$target"
command -v rsync >/dev/null 2>&1 || fail 'rsync is not installed on Helios'
printf '%s\n' "$target"
"""


def allowed_paths(user: str) -> set[str]:
    return {
        f"/home/studs/{user}/public_html/{PROJECT}",
        f"/export/home/studs/{user}/public_html/{PROJECT}",
    }


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    user: str
    path: str
    site_url: str

    @classmethod
    def from_environment(cls) -> "Config":
        fields = ("HELIOS_HOST", "HELIOS_DEPLOY_PATH", "HELIOS_SITE_URL", "HELIOS_USER", "HELIOS_SSH_KEY", "HELIOS_KNOWN_HOSTS")
        for name in fields:
            if not os.environ.get(name):
                raise ValueError(f"{name} is not set")
        host = os.environ["HELIOS_HOST"]
        user = os.environ["HELIOS_USER"]
        path = os.environ["HELIOS_DEPLOY_PATH"].rstrip("/")
        site_url = os.environ["HELIOS_SITE_URL"]
        port = int(os.environ.get("HELIOS_PORT") or "2222")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
            raise ValueError("Invalid HELIOS_HOST")
        if not re.fullmatch(r"s[0-9]+", user):
            raise ValueError("HELIOS_USER must be an ITMO student account, e.g. s123456")
        if not 1 <= port <= 65535:
            raise ValueError("HELIOS_PORT must be between 1 and 65535")
        if path not in allowed_paths(user):
            raise ValueError("HELIOS_DEPLOY_PATH must point exactly to this account's public_html/pyweb_lab1 directory")
        url = urlsplit(site_url)
        if (url.scheme not in {"http", "https"} or not url.netloc or url.username
                or url.query or url.fragment or not url.path.endswith(f"/{PROJECT}/")):
            raise ValueError("HELIOS_SITE_URL must be an HTTP(S) URL ending with /pyweb_lab1/")
        return cls(host, port, user, path, site_url)


def deploy(config: Config, site: Path) -> None:
    site = site.resolve()
    if not (site / "index.html").is_file():
        raise ValueError("The site directory must contain index.html")
    ssh_options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-p", str(config.port)]
    remote = f"{config.user}@{config.host}"
    result = subprocess.run(
        ["ssh", *ssh_options, remote, f"sh -s -- {shlex.quote(config.path)} {shlex.quote(config.user)}"],
        input=REMOTE_PREPARE, text=True, capture_output=True, check=True,
    )
    canonical_path = result.stdout.strip()
    if canonical_path not in allowed_paths(config.user):
        raise ValueError("The remote server returned an unexpected deployment path; rsync was not started")
    parent = canonical_path.rsplit("/", 1)[0]
    # Повторная проверка прямо в команде принимающего rsync.
    receiver = (
        f"test ! -L {shlex.quote(parent)} && test ! -L {shlex.quote(canonical_path)} "
        f"&& cd -P {shlex.quote(canonical_path)} "
        f"&& test \"$(pwd -P)\" = {shlex.quote(canonical_path)} && exec rsync"
    )
    subprocess.run(
        ["rsync", "--archive", "--compress", "--delete", "--one-file-system", "--chmod=D755,F644",
         "--rsync-path", receiver, "-e", shlex.join(["ssh", *ssh_options]),
         site.as_posix().rstrip("/") + "/", f"{remote}:{canonical_path}/"],
        check=True,
    )
    print("Helios deployment completed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    args = parser.parse_args()
    try:
        config = Config.from_environment()
        if args.validate_only:
            print("Helios configuration validated")
        else:
            deploy(config, args.site_dir)
    except subprocess.CalledProcessError as error:
        # Не печатаем переменные окружения и SSH-ключи.
        print(f"HELIOS DEPLOY FAILED: command exited with {error.returncode}", file=sys.stderr)
        if error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"HELIOS DEPLOY FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
