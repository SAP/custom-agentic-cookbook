"""Download the pinned public Ollama manifest and verify every model blob."""

import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

MANIFEST_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"
REGISTRY = "https://registry.ollama.ai/v2/library/qwen2.5"


def install(root=Path("/models")):
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    manifest = Path(__file__).with_name("qwen2.5-1.5b-manifest.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != MANIFEST_DIGEST:
        raise RuntimeError(
            "The selected model manifest differs from the reviewed digest"
        )
    content = json.loads(manifest)
    blobs = root / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    for item in [content["config"], *content["layers"]]:
        digest = item["digest"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise RuntimeError("The model manifest contains an invalid blob digest")
        expected_size = item["size"]
        if not isinstance(expected_size, int) or expected_size < 0:
            raise RuntimeError("The model manifest contains an invalid blob size")
        target = blobs / digest.replace(":", "-")
        if target.exists():
            if target.stat().st_size == expected_size:
                with target.open("rb") as existing:
                    verified = hashlib.file_digest(existing, "sha256").hexdigest()
                if verified == digest[7:]:
                    continue
            target.unlink()
        partial = target.with_suffix(".part")
        size = partial.stat().st_size if partial.exists() else 0
        if size >= expected_size:
            partial.unlink(missing_ok=True)
            size = 0
        deadline = time.monotonic() + 1800
        # Fresh signed redirects for small ranges avoid expiry during a large model transfer.
        try:
            with partial.open("ab") as output:
                while size < expected_size:
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "The model blob download exceeded its 30-minute budget"
                        )
                    end = min(size + 8 * 1024 * 1024, expected_size) - 1
                    request = urllib.request.Request(
                        REGISTRY + "/blobs/" + digest,
                        headers={
                            "Range": f"bytes={size}-{end}",
                            "Accept-Encoding": "identity",
                        },
                    )
                    with client.open(request, timeout=120) as response:
                        expected_range = f"bytes {size}-{end}/{expected_size}"
                        if (
                            response.status != 206
                            or response.headers.get("Content-Range") != expected_range
                        ):
                            raise RuntimeError(
                                "The model registry returned an unexpected byte range"
                            )
                        remaining = end - size + 1
                        while remaining:
                            if time.monotonic() > deadline:
                                raise TimeoutError(
                                    "The model blob download exceeded its 30-minute budget"
                                )
                            block = response.read(min(1024 * 1024, remaining))
                            if not block:
                                raise RuntimeError(
                                    f"Model blob {digest} ended before its expected size"
                                )
                            output.write(block)
                            size += len(block)
                            remaining -= len(block)
                        if response.read(1):
                            raise RuntimeError(
                                f"Model blob {digest} exceeds its expected size"
                            )
            with partial.open("rb") as downloaded:
                checksum = hashlib.file_digest(downloaded, "sha256").hexdigest()
            if checksum != digest[7:]:
                raise RuntimeError(
                    f"Model blob {digest} differs from its reviewed digest"
                )
            partial.replace(target)
        except RuntimeError:
            partial.unlink(missing_ok=True)
            raise
    target = root / "manifests/registry.ollama.ai/library/qwen2.5/1.5b"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(manifest)
    print("The pinned Qwen2.5 1.5B manifest and all blobs pass digest verification")


if __name__ == "__main__":
    install()
