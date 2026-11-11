"""Verify that the serving build refuses changed public model artifacts."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


def downloader(tmp_path, monkeypatch, payload=b"model"):
    source = Path(__file__).resolve().parents[2] / "custom-model-serving/download_model.py"
    spec = importlib.util.spec_from_file_location("model_download", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    manifest = json.dumps({"config": {"digest": digest, "size": len(payload)}, "layers": []})
    (tmp_path / "qwen2.5-1.5b-manifest.json").write_text(manifest)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "download_model.py"))
    monkeypatch.setattr(module, "MANIFEST_DIGEST", hashlib.sha256(manifest.encode()).hexdigest())
    response = io.BytesIO(payload)
    response.status = 206
    response.headers = {"Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"}
    client = Mock()
    client.open.return_value = response
    monkeypatch.setattr(module.urllib.request, "build_opener", Mock(return_value=client))
    return module, client, digest


def test_verified_model_blobs_and_manifest_are_installed(tmp_path, monkeypatch):
    module, client, digest = downloader(tmp_path, monkeypatch)
    root = tmp_path / "models"
    module.install(root)
    assert (root / "blobs" / digest.replace(":", "-")).read_bytes() == b"model"
    assert (root / "manifests/registry.ollama.ai/library/qwen2.5/1.5b").is_file()
    assert client.open.call_count == 1


@pytest.mark.parametrize("corrupt", [b"other", b"model-extra", b"mo"])
def test_changed_blob_is_refused_and_removed(tmp_path, monkeypatch, corrupt):
    module, client, digest = downloader(tmp_path, monkeypatch)
    response = io.BytesIO(corrupt)
    response.status = 206
    response.headers = {"Content-Range": "bytes 0-4/5"}
    client.open.return_value = response
    root = tmp_path / "models"
    with pytest.raises(RuntimeError, match="exceeds|differs|ended"):
        module.install(root)
    assert not (root / "blobs" / digest.replace(":", "-")).exists()
    assert not (root / "manifests").exists()


def test_verified_cache_is_rechecked_without_network_access(tmp_path, monkeypatch):
    module, client, digest = downloader(tmp_path, monkeypatch)
    root = tmp_path / "models"
    (root / "blobs").mkdir(parents=True)
    (root / "blobs" / digest.replace(":", "-")).write_bytes(b"model")
    module.install(root)
    client.open.assert_not_called()


def test_partial_download_resumes_with_a_fresh_bounded_range(tmp_path, monkeypatch):
    module, client, digest = downloader(tmp_path, monkeypatch)
    root = tmp_path / "models"
    (root / "blobs").mkdir(parents=True)
    target = root / "blobs" / digest.replace(":", "-")
    target.with_suffix(".part").write_bytes(b"mo")
    response = io.BytesIO(b"del")
    response.status = 206
    response.headers = {"Content-Range": "bytes 2-4/5"}
    client.open.return_value = response
    module.install(root)
    assert client.open.call_args.args[0].get_header("Range") == "bytes=2-4"
    assert target.read_bytes() == b"model"


def test_unexpected_byte_range_is_refused(tmp_path, monkeypatch):
    module, client, _ = downloader(tmp_path, monkeypatch)
    client.open.return_value.headers = {"Content-Range": "bytes 1-5/5"}
    with pytest.raises(RuntimeError, match="unexpected byte range"):
        module.install(tmp_path / "models")


def test_download_budget_stops_before_another_network_request(tmp_path, monkeypatch):
    module, client, _ = downloader(tmp_path, monkeypatch)
    monkeypatch.setattr(module.time, "monotonic", Mock(side_effect=[0, 1801]))
    with pytest.raises(TimeoutError, match="30-minute budget"):
        module.install(tmp_path / "models")
    client.open.assert_not_called()


def test_changed_manifest_is_refused_before_network_access(tmp_path, monkeypatch):
    module, client, _ = downloader(tmp_path, monkeypatch)
    (tmp_path / "qwen2.5-1.5b-manifest.json").write_text("{}")
    with pytest.raises(RuntimeError, match="manifest differs"):
        module.install(tmp_path / "models")
    client.open.assert_not_called()
