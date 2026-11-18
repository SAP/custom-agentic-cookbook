"""Update one local mock-deployment values file with a tested image digest."""

from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

import yaml

DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
REPOSITORY_PATH = re.compile(
    r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*\Z"
)
REGISTRY = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
    r"(?::0*(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|"
    r"65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?\Z"
)
TAG = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}\Z")


def valid_repository(repository: str) -> bool:
    first, separator, remainder = repository.partition("/")
    if separator and ("." in first or ":" in first or first == "localhost"):
        return bool(REGISTRY.fullmatch(first) and REPOSITORY_PATH.fullmatch(remainder))
    return bool(REPOSITORY_PATH.fullmatch(repository))


class ValuesError(ValueError):
    """A values file or image input does not satisfy this deployment contract."""


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys instead of silently keeping the last one."""


def unique_mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise ValuesError("YAML merge keys are unsupported")
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValuesError("values mappings require unique string keys")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor("tag:yaml.org,2002:map", unique_mapping)


def image_coordinates(repository: str, tag: str, digest: str) -> None:
    if not all(isinstance(value, str) for value in (repository, tag, digest)):
        raise ValuesError("image coordinates must be strings")
    if (
        len(repository) > 255
        or not valid_repository(repository)
        or not TAG.fullmatch(tag)
        or tag == "latest"
    ):
        raise ValuesError("image repository and non-latest tag are required")
    if not DIGEST.fullmatch(digest):
        raise ValuesError("image digest must be a lowercase sha256 digest")


def update_image(
    path: Path, *, repository: str, tag: str, digest: str, expected_current_digest: str
) -> bool:
    """Replace image coordinates atomically; return False for an exact no-op.

    The expected digest catches an outdated local deployment-state selection.
    Use one editor at a time and review the Git branch head before publication.
    This local helper does not publish, validate registry content, or deploy.
    """
    image_coordinates(repository, tag, digest)
    if not isinstance(expected_current_digest, str) or (
        expected_current_digest and not DIGEST.fullmatch(expected_current_digest)
    ):
        raise ValuesError("expected current digest must be empty or a sha256 digest")
    if path.is_symlink() or not path.is_file():
        raise ValuesError("values path must be an existing regular file, not a symlink")
    original = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    try:
        values = yaml.load(original, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValuesError("values must contain one valid YAML document") from exc
    if not isinstance(values, dict) or not isinstance(values.get("image"), dict):
        raise ValuesError("values require one image mapping")
    image = values["image"]
    if not {"repository", "tag", "digest"} <= image.keys():
        raise ValuesError("image requires repository, tag, and digest")
    current = tuple(image[name] for name in ("repository", "tag", "digest"))
    if not all(isinstance(value, str) for value in current):
        raise ValuesError("current image coordinates must be strings")
    if current != ("", "", ""):
        image_coordinates(*current)
    if current[2] != expected_current_digest:
        raise ValuesError(
            "current image digest changed; review the latest values first"
        )
    exposure = values.get("apirule", {})
    if not isinstance(exposure, dict) or exposure.get("enabled", False) is not False:
        raise ValuesError("this GitOps sample requires apirule.enabled=false")
    replicas = values.get("replicaCount", 1)
    if type(replicas) is not int or replicas != 1:
        raise ValuesError("this in-memory sample requires one replica")
    if current == (repository, tag, digest):
        return False
    image.update(repository=repository, tag=tag, digest=digest)
    rendered = yaml.safe_dump(values, sort_keys=False).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, mode)
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise ValuesError("values changed during preparation; retry after review")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("values", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--expected-current-digest", required=True)
    args = parser.parse_args()
    try:
        changed = update_image(
            args.values,
            repository=args.repository,
            tag=args.tag,
            digest=args.digest,
            expected_current_digest=args.expected_current_digest,
        )
    except (ValuesError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    print(
        "Updated deployment values." if changed else "Deployment values already match."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
