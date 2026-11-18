# Optional synthetic validation image

This proposed image runs the existing HTTP/OAuth/OData reader and its optional
A2A consumer with an in-memory task store. The included fixture uses synthetic
OAuth/OData records. It does not prove a Datasphere tenant, a deployed service,
or authenticated public access. Its default command starts the fixture on
loopback without authentication. The normal `uv` reader and optional A2A
commands retain their existing HTTPS/OAuth/OData configuration and behavior.
This image's source, runtime and redistribution review remain separate gates.

The image starts from the pinned official Python 3.12 Alpine base in
`build-inputs.json`. It retains the frozen application dependencies and uses
only the supported Alpine main repository. SQLite and NIS are unused by this
sample. Their Python modules and native providers are removed. The replacement
virtual package records the remaining runtime requirements. A scratch final
stage copies that filesystem, so the shipped layers omit those components.
This is a sample runtime; it does not provide the complete Python standard
library. The protobuf wheel uses its Python backend.

Commit the reviewed source and assets before staging. From this sample
directory, the following local build creates a unique context and owned builder.
The helper verifies the committed source, repository LICENSE, project/lock
hashes and all 28 context inputs before creating the destination. Explicit
guards also run under `python -O`. It emits actual staged hashes and the fresh
source commit; that commit is passed to both build and final image labels.
Source, support, license and build inputs must be regular files whose exact bytes
exist as regular-file blobs in that commit. Symlinks are refused before staging.
An optional local bootstrap wheel must also be a regular file and match the
SHA-256 in the committed build manifest; its public download remains separately
bound to that same hash.

```sh
python - <<'PYTHON'
import json, pathlib, subprocess, tempfile, uuid
sample = pathlib.Path.cwd()
owned = pathlib.Path(tempfile.mkdtemp(prefix="cookbook-datasphere-build-"))
builder = "cookbook-datasphere-" + uuid.uuid4().hex
tag = "cookbook-datasphere-validation:" + uuid.uuid4().hex
prepared = subprocess.run([
    "python", "validation-image/prepare-context.py", "--source-dir", ".",
    "--root-license", "../../LICENSE", "--directory", str(owned / "context")
], check=True, capture_output=True, text=True, timeout=60)
receipt = json.loads(prepared.stdout)
(owned / "context-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print("Owned build directory:", owned, flush=True)
try:
    subprocess.run([
        "docker", "buildx", "create", "--name", builder,
        "--driver", "docker-container", "--driver-opt",
        "image=docker.io/moby/buildkit@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea",
        "--driver-opt", "memory=1536m", "--driver-opt", "memory-swap=1536m",
        "--driver-opt", "cpu-quota=200000", "--driver-opt", "cpu-period=100000",
        "--driver-opt", "cpuset-cpus=0-1"
    ], check=True, timeout=20)
    with (owned / "build.log").open("w") as log:
        subprocess.run([
            "docker", "buildx", "build", "--builder", builder,
            "--platform", receipt["platform"], "--progress", "plain", "--load",
            "--build-arg", "PYTHON_IMAGE=" + receipt["python_base"],
            "--build-arg", "APPLICATION_REVISION=" + receipt["source_revision"],
            "--tag", tag, str(owned / "context")
        ], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    (owned / "built-image.txt").write_text(tag + "\n")
    print("Local image:", tag, flush=True)
finally:
    # Removing this uniquely named builder also stops its owned build container.
    subprocess.run(["docker", "buildx", "rm", builder], check=True, timeout=30)
    print("Retained context and complete build log:", owned, flush=True)
PYTHON
```

The builder has two CPU slots (0 and 1), 1536 MiB memory and memory-plus-swap,
with a ten-minute build timeout. It does not change the default builder.
On timeout or failure, inspect the retained log and confirm this exact builder
is gone before retrying; a failed removal is a cleanup failure. No image is
pushed. Remove only the recorded unique local image tag after validation.
The source helper downloads only the exact hashed public bootstrap wheel when
`--pip-wheel` is omitted. Supply that same wheel with `--pip-wheel` for offline
staging. Build package downloads still require access to the pinned public
Python/BuildKit images, Alpine main and PyPI.

This proposal must receive source, runtime, third-party notice and security
review. The retained scan is one layer of evidence. It does not replace source
advisory review or establish the provenance of wheel-vendored GCC runtimes.
Changes to source or locked build inputs require a fresh build and validation.
Refresh dependencies through the normal project lock workflow, regenerate the
complete hashed validation requirements from the reviewed lock, and refresh
the support/context hashes together. Do not bypass a failing guard by copying
changed input bytes or retaining old hashes. Moving supported Alpine packages
and generated timestamps mean exact staging is not a bit-reproducible image
claim. Deployment, registry publication and live resource cleanup require their
own concrete reviews and approvals.


The committed `source_notice_files` mapping adds exact third-party notice and
license copies from `../third-party-notices/` to bounded, flat context names.
Each mapped source must pass the same regular-file and committed-blob guards;
its SHA-256 is checked before any context file is written. Docker copies those
bytes under `/usr/share/doc/cookbook-pr79/third-party-notices/`, preserving the
source directory layout. This placement does not select a distribution route
or authorize publication. The separate accompanying source archives remain
outside this source tree and require their own reviewed delivery decision.
