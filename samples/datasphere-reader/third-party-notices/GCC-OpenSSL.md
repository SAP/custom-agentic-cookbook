# Third-party notices — GCC runtimes and bundled OpenSSL

This sidecar is proposed for the restricted Datasphere HTTP/OAuth/OData validation image. The Cookbook application code keeps its own license. Third-party source and runtime-library licenses apply to the corresponding components described here. This is not an approval to distribute the image or a statement that the complete recipe notice inventory is finished.

## GNU GCC runtime libraries

The image includes these upstream-wheel runtime objects:

| Wheel component | Image path | GCC version/source family | SHA-256 of shipped object |
| --- | --- | --- | --- |
| pydantic-core 2.50.1 | /usr/local/lib/python3.12/site-packages/pydantic_core.libs/libgcc_s-f685abf1.so.1 | GCC 12.4.0; rust-musl-cross/musl-cross-make toolchain | 91a43de5877248a317d14faa35490ef474a1b33a83e235b52fb1eabf7108108e |
| rpds-py 2026.9.1 | /usr/local/lib/python3.12/site-packages/rpds_py.libs/libgcc_s-f685abf1.so.1 | GCC 12.4.0; rust-musl-cross/musl-cross-make toolchain | 91a43de5877248a317d14faa35490ef474a1b33a83e235b52fb1eabf7108108e |
| cryptography 50.0.2 | /usr/local/lib/python3.12/site-packages/cryptography.libs/libgcc_s-0cd532bd.so.1 | Alpine libgcc 14.2.0-r6, source commit fbf60319be3bbaf6dd32ef55cc6fb7189e05c266 | 42b5f2c8ca13e5e173d837f5117a04b6c042437548112bde7879251ae8dcff8f |

GNU libgcc runtime source files such as the unwind implementation are licensed under GPL version3 or later with the GCC Runtime Library Exception version3.1. The exact GPL text and exception are reproduced verbatim in `licenses/GPL-3.0-or-later.txt` and `licenses/GCC-exception-3.1.txt`. The source packages retain all individual file copyright and license notices; source files with their own terms retain those terms. The broader Alpine package metadata is not substituted for the actual libgcc file license.

Upstream wheel repair copies the runtime objects into wheel-specific `.libs` directories, renames their SONAME/file using a digest suffix and adjusts ELF dependency/search-path data. These packaging changes are described by the supplied maturin1.15.0 repair/patchelf source and auditwheel6.8.2 repair/patcher source. The source bundle preserves the corresponding build configurations and patches. No Cookbook application feature or GCC algorithm was changed in this candidate. The repaired objects above are preserved exactly; the image is not rebuilt by this notice proposal.

The proposed binary distribution route is an eligible compiled combination of the wheel modules and their supporting GCC runtimes under the GCC Runtime Library Exception. The exception permits eligible compiled combinations with independent modules under terms consistent with those independent modules. It applies to static and dynamic combinations; it does not automatically relicense the Cookbook as GPL. The accompanying source artifact is proposed voluntarily for this combination route. Its presence does not impose GPLv3 section6(d) source access on every image distribution or establish a complete corresponding-source claim.

If maintainers instead select independent runtime-library distribution and use the GPLv3 section6(d) method, they must first qualify exact corresponding-source completeness, including the historical GCC12 source correspondence described in the source README, and provide equivalent machine-readable source access and clear directions with the object, without an additional charge and with the availability required by that method. Final route selection, actual access placement and publication approval remain separate. No external source endpoint or distribution is created by this proposal.

The exact source/header notices include:

### GCC 12.4.0 upstream unwind notice

```text
/* DWARF2 exception handling and frame unwind runtime interface routines.
   Copyright (C) 1997-2022 Free Software Foundation, Inc.

   This file is part of GCC.

   GCC is free software; you can redistribute it and/or modify it
   under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 3, or (at your option)
   any later version.

   GCC is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
   License for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */
```

### GCC 14.2.0 upstream unwind notice

```text
/* DWARF2 exception handling and frame unwind runtime interface routines.
   Copyright (C) 1997-2024 Free Software Foundation, Inc.

   This file is part of GCC.

   GCC is free software; you can redistribute it and/or modify it
   under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 3, or (at your option)
   any later version.

   GCC is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
   License for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */
```

## OpenSSL 4.0.3 statically included by cryptography

The exact cryptography wheel embeds OpenSSL4.0.3. Its source archive is:

`https://github.com/openssl/openssl/releases/download/openssl-4.0.3/openssl-4.0.3.tar.gz`

SHA-256: `325b5c806167c13b40b1ffeadfe0248197c00eccc4cf123ec1e28d2d2fd216d9`.

The wheel's SBOM records `no-zlib no-shared no-module no-comp no-apps no-docs no-sm2-precomp no-atexit enable-ec_nistp_64_gcc_128`. This is the bundled cryptography backend; the separate system libssl/libcrypto packages retain their own inventory and source.

OpenSSL's Apache License2.0 is reproduced verbatim in `licenses/OpenSSL-4.0.3-LICENSE.txt`. The exact upstream authors list is preserved in `licenses/OpenSSL-4.0.3-AUTHORS.md`. The official source archive has no root NOTICE/NOTICE.txt file; this proposal does not invent one. Individual upstream source-file notices remain in the accompanying source archive. The crypto wheel's own Apache/BSD licenses remain at their original dist-info paths and are not replaced by this sidecar.


## Repair and toolchain source in the accompanying artifact

The accompanying source artifact also contains copied repair and build source. Its SOURCE-LICENSE-MAP.json binds each original upstream license path to the captured source tree, immutable Git blob and supplied file. The original license texts and copyright notices are included verbatim beside the corresponding flattened source paths under upstream-build-recipes/:

| Copied source | Original license and attribution included |
| --- | --- |
| auditwheel 6.8.2 | auditwheel6.8.2--LICENSE; includes its MIT and applicable BSD source terms |
| auditwheel vendored wheel | auditwheel6.8.2--src--auditwheel--_vendor--wheel--LICENSE.txt |
| auditwheel vendored whichprovides | auditwheel6.8.2--src--auditwheel--_vendor--whichprovides--LICENSE.txt |
| maturin 1.15.0 repair source | maturin1.15--license-apache and maturin1.15--license-mit |
| pinned maturin-action source | maturin-action--LICENSE |
| date-qualified rust-musl-cross source | rust-musl-cross--LICENSE, rust-musl-cross--LICENSE-MIT.txt and rust-musl-cross--LICENSE-APACHE.txt |

Both upstream alternative license texts are retained where present. This notice makes no implicit license choice. The full copied texts preserve the original attribution; the OpenSSL license is not used as a substitute for these projects’ notices. Existing source-file copyright and license headers remain unchanged. These source-artifact additions do not alter any shipped image object.

## Source and notice coverage

The linked Cargo/Rust component inventory, other installed wheels, Alpine packages and Python notices must be combined with this scoped sidecar before a complete binary-distribution claim. Source/header license evidence and eligible compilation are distinct from byte-for-byte compiler invocation reproduction. This sidecar makes no waiver, security-clearance, general-Python-stdlib, tenant, live-deployment or public-readiness claim.
