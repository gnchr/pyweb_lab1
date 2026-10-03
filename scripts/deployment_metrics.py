"""Замер от начала доставки до завершения публичного healthcheck."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("action", choices=("start", "finish"))
parser.add_argument("--file", type=Path, required=True)
parser.add_argument("--outcome", default="")
parser.add_argument("--url", default="")
parser.add_argument("--started-at", type=float, help="Carry the build job's start timestamp into the deploy job")
args = parser.parse_args()
args.file.parent.mkdir(parents=True, exist_ok=True)
if args.action == "start":
    started = args.started_at if args.started_at is not None else time.time()
    result = {"started_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(), "started_unix": started}
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"delivery_started={started}\n")
else:
    result = json.loads(args.file.read_text()) if args.file.exists() else {}
    result.update({"finished_utc": datetime.now(timezone.utc).isoformat(), "outcome": args.outcome, "url": args.url})
    if "started_unix" in result:
        result["delivery_seconds"] = round(time.time() - result["started_unix"], 6)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("\nDeployment measurements:\n\n```json\n" + json.dumps(result, indent=2) + "\n```\n")
args.file.write_text(json.dumps(result, indent=2), encoding="utf-8")
