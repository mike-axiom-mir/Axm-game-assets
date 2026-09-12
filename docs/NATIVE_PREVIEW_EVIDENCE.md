# Native preview evidence v0.1

`native_preview_evidence.py` wires two existing Game Asset Forge capabilities together:

`native_preview.py` diagnostic software rasterization
→ `native_evidence_verify.py` caller-pinned exact-byte verification

The result is a review bundle whose diagnostic frames, report, and local review surface are bound to one exact mesh digest and one caller-pinned evidence manifest.

## What is captured

For each requested preview view the wrapper records:

- silhouette PNG;
- depth PNG;
- face-normal PNG.

It also records:

- `preview-report.json`;
- `review.html`.

The default front/side/top set therefore contains eleven caller-pinned files.

## Identity

The mesh digest is computed from the explicit mesh name, vertex positions, and face indices. The evidence manifest also records preview size, ordered views, signal kinds, and the fact that this is the native orthographic diagnostic rasterizer.

After writing the manifest, the wrapper immediately calls the generic evidence verifier. That verifier independently re-hashes every declared file and validates the caller-pinned manifest digest.

## Use

Python API:

```python
from native_preview_evidence import write_verified_preview

result = write_verified_preview(mesh, "build/preview-evidence", size=128)
```

The destination is create-only so a new run cannot silently overwrite the reviewed evidence body.

## Truth boundary

`PASS` proves exact diagnostic bytes and the declared mesh/context binding at verification time.

It does not prove:

- aesthetic quality;
- engine rendering parity;
- gameplay readability;
- AAA quality;
- canonical acceptance.

These previews remain software diagnostics. Real engine screenshots/video and performance evidence are still separate later gates.

## Provenance

The stable caller-pinned verifier was adapted from FrameState and transplanted into Game Asset Forge in PR #24. This wrapper is the first direct use of that verifier on Forge-native visual output rather than only on synthetic evidence fixtures.
