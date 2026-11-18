# Validation-only package; root must provide an independently verified public digest.
ARG PYTHON_IMAGE
ARG APPLICATION_REVISION
FROM ${PYTHON_IMAGE} AS build
ARG APPLICATION_REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
LABEL org.opencontainers.image.revision="${APPLICATION_REVISION}" \
      io.sap.cookbook.validation="synthetic-only"
WORKDIR /app
# Supported Alpine main only; keep APK metadata and every required runtime feature.
RUN printf '%s\n' 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' > /tmp/cookbook-supported-repositories \
    && apk --repositories-file /tmp/cookbook-supported-repositories upgrade --no-cache \
    && rm /tmp/cookbook-supported-repositories
# Private validation variant: SQLite/NIS are outside this HTTP/OData recipe contract.
# Rebuild generated runtime dependency metadata before removing unused native providers.
RUN python - <<'PYTHON'
from pathlib import Path
import json,shutil,subprocess,importlib.util
root=Path('/usr/local/lib/python3.12');db=Path('/lib/apk/db/installed')
entries=[{line.split(':',1)[0]:line.split(':',1)[1] for line in s.splitlines() if ':' in line} for s in db.read_text().split('\n\n')]
original={e['P']:e['V'] for e in entries if 'P' in e}
old=next(e for e in entries if e.get('P')=='.python-rundeps')
deps=old['D'].split();assert 'so:libsqlite3.so.0' in deps and 'so:libnsl.so.3' in deps
retained=[d for d in deps if d not in ('so:libsqlite3.so.0','so:libnsl.so.3')]
# libintl is a former libnsl dependency; preserve it to keep this removal exact.
retained.append('libintl='+original['libintl'])
removed=[]
for pattern in ('_sqlite3.*.so','nis.*.so'):
 matches=list((root/'lib-dynload').glob(pattern));assert len(matches)==1
 for path in matches:removed.append(str(path));path.unlink()
assert (root/'sqlite3').is_dir();shutil.rmtree(root/'sqlite3');removed.append(str(root/'sqlite3'))
subprocess.run(['apk','add','--no-network','--virtual','.cookbook-python-rundeps',*retained],check=True)
subprocess.run(['apk','del','--no-network','.python-rundeps','sqlite-libs','libnsl'],check=True)
newentries=[{line.split(':',1)[0]:line.split(':',1)[1] for line in s.splitlines() if ':' in line} for s in db.read_text().split('\n\n')]
actual={e['P']:e['V'] for e in newentries if 'P' in e}
assert set(original)-set(actual)=={'.python-rundeps','sqlite-libs','libnsl'}
assert set(actual)-set(original)=={'.cookbook-python-rundeps'}
assert all(actual[k]==v for k,v in original.items() if k in actual)
assert importlib.util.find_spec('_sqlite3') is None and importlib.util.find_spec('sqlite3') is None and importlib.util.find_spec('nis') is None
Path('/etc/apk/repositories').write_text('https://dl-cdn.alpinelinux.org/alpine/v3.24/main\n')
Path('/usr/local/share/cookbook-private-runtime-variant.json').write_text(json.dumps({'private_validation_only':True,'removed_unused_stdlib_modules':removed,'removed_APK_packages':['sqlite-libs','libnsl'],'preserved_runtime_dependencies':retained,'generated_virtual_package':'.cookbook-python-rundeps','general_Python_SQLite_NIS_capability':False},indent=2)+'\n')
PYTHON
COPY pip-26.2-py3-none-any.whl bootstrap-requirements.txt /tmp/pip-bootstrap/
# Use the inspected fixed wheel itself to bootstrap; do not execute base pip.
RUN python -c 'import hashlib,pathlib,zipfile,shutil; p=pathlib.Path("/tmp/pip-bootstrap/pip-26.2-py3-none-any.whl"); assert hashlib.sha256(p.read_bytes()).hexdigest()=="931c303696af6fa3417112103b1cad26890e5a07eccb5b99783700e33f2b8aad"; zipfile.ZipFile(p).extractall("/tmp/pip-code"); shutil.rmtree("/tmp/pip-code/pip-26.2.dist-info")' \
    && PYTHONPATH=/tmp/pip-code python -m pip --isolated install \
    --upgrade --no-index --find-links /tmp/pip-bootstrap --only-binary=:all: \
    --require-hashes -r /tmp/pip-bootstrap/bootstrap-requirements.txt \
    && rm -rf /tmp/pip-bootstrap /tmp/pip-code \
    && python -c 'import importlib.metadata,pip; assert pip.__version__=="26.2"; assert [d.version for d in importlib.metadata.distributions() if d.metadata["Name"].lower()=="pip"]==["26.2"]'
COPY requirements.txt /app/requirements.txt
RUN python -m pip --isolated install --index-url https://pypi.org/simple \
    --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.txt
# Installer and its vendored dependency bundle are unnecessary at runtime.
RUN python -m pip --isolated uninstall --yes pip \
    && python -c 'import importlib.util,importlib.metadata; assert importlib.util.find_spec("pip") is None; assert not [d for d in importlib.metadata.distributions() if d.metadata["Name"].lower()=="pip"]'
COPY datasphere.py mcp_server.py revenue_agent.py a2a_server.py fixture.py run_mcp_fixture.py /app/
COPY LICENSE /app/LICENSE
COPY notice-third-party-notices--GCC-OpenSSL.md /usr/share/doc/cookbook-pr79/third-party-notices/GCC-OpenSSL.md
COPY notice-third-party-notices--licenses--GPL-3.0-or-later.txt /usr/share/doc/cookbook-pr79/third-party-notices/licenses/GPL-3.0-or-later.txt
COPY notice-third-party-notices--licenses--GCC-exception-3.1.txt /usr/share/doc/cookbook-pr79/third-party-notices/licenses/GCC-exception-3.1.txt
COPY notice-third-party-notices--licenses--OpenSSL-4.0.3-LICENSE.txt /usr/share/doc/cookbook-pr79/third-party-notices/licenses/OpenSSL-4.0.3-LICENSE.txt
COPY notice-third-party-notices--licenses--OpenSSL-4.0.3-AUTHORS.md /usr/share/doc/cookbook-pr79/third-party-notices/licenses/OpenSSL-4.0.3-AUTHORS.md
COPY notice-third-party-notices--README.md /usr/share/doc/cookbook-pr79/third-party-notices/README.md
COPY notice-third-party-notices--SOURCE-REFERENCES.json /usr/share/doc/cookbook-pr79/third-party-notices/SOURCE-REFERENCES.json
COPY notice-third-party-notices--THIRD-PARTY-NOTICES.txt /usr/share/doc/cookbook-pr79/third-party-notices/THIRD-PARTY-NOTICES.txt
COPY notice-third-party-notices--rust--1.98.1--COPYRIGHT /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.98.1/COPYRIGHT
COPY notice-third-party-notices--rust--1.98.1--COPYRIGHT-library.html /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.98.1/COPYRIGHT-library.html
COPY notice-third-party-notices--rust--1.98.1--LICENSE-APACHE /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.98.1/LICENSE-APACHE
COPY notice-third-party-notices--rust--1.98.1--LICENSE-MIT /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.98.1/LICENSE-MIT
COPY notice-third-party-notices--rust--1.99.0--COPYRIGHT /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.99.0/COPYRIGHT
COPY notice-third-party-notices--rust--1.99.0--COPYRIGHT-library.html /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.99.0/COPYRIGHT-library.html
COPY notice-third-party-notices--rust--1.99.0--LICENSE-APACHE /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.99.0/LICENSE-APACHE
COPY notice-third-party-notices--rust--1.99.0--LICENSE-MIT /usr/share/doc/cookbook-pr79/third-party-notices/rust/1.99.0/LICENSE-MIT
USER 10001:10001
CMD ["python", "fixture.py"]

# Only the pruned final filesystem is shipped; predecessor layers are preserved separately.
FROM scratch
ARG APPLICATION_REVISION
COPY --from=build / /
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
LABEL org.opencontainers.image.revision="${APPLICATION_REVISION}" io.sap.cookbook.validation="synthetic-only" io.sap.cookbook.runtime-variant="private-http-odata-no-sqlite-nis"
WORKDIR /app
USER 10001:10001
CMD ["python", "fixture.py"]
