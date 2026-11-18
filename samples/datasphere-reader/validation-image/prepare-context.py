"""Prepare a committed, hash-bound synthetic context; never build or publish."""

import argparse
import hashlib
import json
import re
import stat
import subprocess
import urllib.request
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(source, *args):
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(source), *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    require(result.returncode == 0, "Source must be committed and unchanged")
    return result.stdout.strip()


def regular_bytes(path):
    require(
        stat.S_ISREG(path.lstat().st_mode),
        "Input must be a regular file; symlinks are not accepted",
    )
    require(path.stat().st_size <= 4 * 1024 * 1024, "Input exceeds limit")
    return path.read_bytes()


def read_committed(path):
    raw = regular_bytes(path)  # Check the supplied object before resolving it.
    resolved = path.resolve()
    require(resolved.is_relative_to(root), "Committed input must stay in source repository")
    relative = str(resolved.relative_to(root))
    row = git(root, "ls-tree", revision, "--", relative).partition("\t")[0].split()
    require(
        len(row) == 3 and row[0] in ("100644", "100755") and row[1] == "blob",
        "Input must be a regular file in committed HEAD",
    )
    require(re.fullmatch(r"[0-9a-f]{40}", row[2]), "Invalid committed blob")
    size = int(git(root, "cat-file", "-s", row[2]))
    require(0 <= size <= 4 * 1024 * 1024, "Committed input exceeds limit")
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), "cat-file", "blob", row[2]],
        capture_output=True,
        timeout=10,
        check=False,
    )
    require(
        result.returncode == 0 and len(result.stdout) == size and raw == result.stdout,
        "Input bytes differ from committed HEAD",
    )
    return raw


def source_notices(manifest):
    notices = manifest["source_notice_files"]
    require(isinstance(notices, dict) and 1 <= len(notices) <= 128, "Invalid notice mapping")
    require(set(notices).issubset(manifest["files"]), "Notice missing from context hashes")
    require(len(set(notices.values())) == len(notices), "Duplicate notice source")
    for flat, relative in notices.items():
        require(isinstance(relative, str) and len(relative) <= 240, "Invalid notice source path")
        parts = relative.split("/")
        require(
            2 <= len(parts) <= 8 and parts[0] == "third-party-notices",
            "Notice must stay in third-party-notices",
        )
        require(
            all(
                re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in (".", "..") for part in parts
            ),
            "Invalid notice source path",
        )
        require(
            flat == "notice-" + relative.replace("/", "--") and len(flat) <= 128,
            "Invalid flat notice filename",
        )
    return notices


parser = argparse.ArgumentParser()
parser.add_argument("--source-dir", required=True, type=Path)
parser.add_argument("--root-license", required=True, type=Path)
parser.add_argument("--directory", required=True, type=Path)
parser.add_argument("--pip-wheel", type=Path)
args = parser.parse_args()
script = Path(__file__).absolute()
regular_bytes(script)
assets = script.parent.resolve()
source = args.source_dir.resolve()
regular_bytes(args.root_license)
license_path = args.root_license.resolve()
require(not args.directory.exists(), "Use a new destination path")
root = Path(git(source, "rev-parse", "--show-toplevel")).resolve()
revision = git(source, "rev-parse", "--verify", "HEAD")
require(re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid source revision")
require(
    assets.is_relative_to(root) and license_path.is_relative_to(root),
    "Assets and license must be in the source repository",
)
manifest = json.loads(read_committed(assets / "build-inputs.json"))
notice_files = source_notices(manifest)
tracked = [
    str(path.relative_to(root)) for path in assets.iterdir() if path.is_file() or path.is_symlink()
]
tracked += [str((source / name).relative_to(root)) for name in manifest["source_files"]]
tracked += [
    str((source / name).relative_to(root)) for name in manifest["source_support_files_sha256"]
]
tracked += [str((source / name).relative_to(root)) for name in notice_files.values()]
tracked.append(str(license_path.relative_to(root)))
git(root, "ls-files", "--error-unmatch", "--", *tracked)
git(
    root,
    "diff",
    "--quiet",
    "--no-ext-diff",
    "HEAD",
    "--",
    str(source.relative_to(root)),
    str(license_path.relative_to(root)),
)
for path in assets.iterdir():
    if path.is_file() or path.is_symlink():
        read_committed(path)
for name, expected in manifest["source_support_files_sha256"].items():
    require(Path(name).name == name, "Invalid support filename")
    raw = read_committed(source / name)
    require(hashlib.sha256(raw).hexdigest() == expected, "Lock or project file changed: " + name)

inputs = {}
actual_hashes = {}
for name, expected in manifest["files"].items():
    require(
        re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in (".", ".."),
        "Invalid context filename",
    )
    require(re.fullmatch(r"[0-9a-f]{64}", expected), "Invalid context hash")
    if name == "pip-26.2-py3-none-any.whl":
        if args.pip_wheel:
            raw = regular_bytes(args.pip_wheel)
        else:
            require(
                manifest["bootstrap_wheel_url"].startswith("https://files.pythonhosted.org/"),
                "Unexpected bootstrap host",
            )
            with urllib.request.urlopen(manifest["bootstrap_wheel_url"], timeout=30) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, "Bootstrap wheel exceeds limit")
    elif name == "LICENSE":
        raw = read_committed(license_path)
    elif name in notice_files:
        raw = read_committed(source / notice_files[name])
    elif name in manifest["source_files"]:
        raw = read_committed(source / name)
    else:
        raw = read_committed(assets / name)
    actual = hashlib.sha256(raw).hexdigest()
    require(actual == expected, "Source or build input changed: " + name)
    inputs[name] = raw
    actual_hashes[name] = actual

# Qualify every input before creating or writing the destination.
args.directory.mkdir(parents=True)
for name, raw in inputs.items():
    (args.directory / name).write_bytes(raw)
staged_hashes = {
    name: hashlib.sha256((args.directory / name).read_bytes()).hexdigest() for name in inputs
}
require(staged_hashes == actual_hashes, "Staged input changed")
print(
    json.dumps(
        {
            "context": str(args.directory),
            "files_sha256": staged_hashes,
            "source_revision": revision,
            "platform": manifest["platform"],
            "python_base": manifest["python_base"],
            "build_args": {
                "PYTHON_IMAGE": manifest["python_base"],
                "APPLICATION_REVISION": revision,
            },
            "build_or_publish": False,
            "bit_reproducible_image_claim": False,
        }
    ),
    flush=True,
)
