"""Записывает идентификатор сборки для healthcheck конкретной версии."""
import argparse
import json
from pathlib import Path

try:
    from .helios_release import identifier
except ImportError:
    from helios_release import identifier


def stamp(directory, release, branch="main"):
    identifier(release)
    marker = "PYWEB_LAB1_RELEASE:" + release
    with (directory / "index.html").open("a", encoding="utf-8") as stream:
        stream.write("\n<!-- " + marker + " -->\n")
    info = {"release": release, "branch": branch, "marker": marker}
    (directory / "deployment.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    (directory / ".release-id").write_text(release + "\n", encoding="ascii")
    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("site"))
    parser.add_argument("--release", required=True)
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()
    print(json.dumps(stamp(args.directory, args.release, args.branch)))
