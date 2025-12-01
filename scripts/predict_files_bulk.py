#!/usr/bin/env python3
"""Helper to upload multiple audio files to the /predict/files endpoint.

Reads input from environment variables:
- HOST: API base URL (default: http://127.0.0.1:8080)
- FILES: newline-separated or quoted, space-separated paths
- FILES_LIST: path to a file containing one path per line
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

# TODO: Analyze the problem with commas in the paths.


def _collect_paths(files_env: str, files_list_path: str) -> list[str]:
    paths: list[str] = []

    if files_list_path:
        try:
            with open(files_list_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.lstrip().startswith("#"):
                        continue
                    paths.append(line)
        except FileNotFoundError:
            sys.exit(f"Files list not found: {files_list_path}")

    if files_env:
        candidates = files_env.splitlines() if "\n" in files_env else shlex.split(files_env)
        for line in candidates:
            line = line.strip()
            if not line or line.lstrip().startswith("#"):
                continue
            paths.append(line)

    return paths


def _validate_paths(paths: list[str]) -> int:
    missing: list[str] = []
    unreadable: list[str] = []

    for path in paths:
        if not os.path.isfile(path):
            missing.append(path)
            continue
        try:
            with open(path, "rb") as handle:
                handle.read(1)
        except OSError as exc:
            unreadable.append(f"{path} ({exc})")

    if missing:
        print("Cannot find these paths:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
    if unreadable:
        print("Cannot read these paths:", file=sys.stderr)
        for path in unreadable:
            print(f"  {path}", file=sys.stderr)

    if missing or unreadable:
        return 1
    return 0


def main() -> int:
    """Main entry point for the script."""
    host = os.environ.get("HOST", "http://127.0.0.1:8080").rstrip("/")
    files_env = os.environ.get("FILES", "")
    files_list_path = os.environ.get("FILES_LIST", "")

    paths = _collect_paths(files_env, files_list_path)
    if not paths:
        print("No files provided. Use FILES or FILES_LIST.", file=sys.stderr)
        return 1

    if _validate_paths(paths):
        return 1

    print(f"Validated {len(paths)} file(s). Uploading to {host}/predict/files ...")
    cmd = ["curl"]
    for path in paths:
        cmd.extend(["-F", f"files=@{path}"])
    cmd.append(f"{host}/predict/files")

    print("Running:", " ".join(shlex.quote(part) for part in cmd))
    result = subprocess.run(cmd)
    if result.returncode != 26:
        return result.returncode

    # If curl reports it cannot read a file, probe individually to identify the culprit.
    if len(paths) > 1:
        print("curl returned 26. Probing each file individually to find the failing path...", file=sys.stderr)
        bad: list[str] = []
        for path in paths:
            probe = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "-F",
                    f"files=@{path}",
                    f"{host}/predict/files",
                ],
                capture_output=True,
                text=True,
            )
            if probe.returncode != 0:
                bad.append(f"{path} (curl exit {probe.returncode}, stderr: {probe.stderr.strip()})")
        if bad:
            print("The following path(s) failed when sent alone:", file=sys.stderr)
            for entry in bad:
                print(f"  {entry}", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
