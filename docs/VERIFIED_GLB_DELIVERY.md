# Verified rigid GLB delivery v0.1

## Why this exists

The native rigid route already produces a verified glTF 2.0 delivery as `.gltf` + `.bin` + PNG textures. That is useful provider evidence, but it is not the single-file `glb` delivery requested by the existing AXM Many-Race RTS Forge bridge.

This capability closes only that delivery boundary. It does **not** claim that a rigid proxy is a finished RTS character, and it does not install an asset into a game.

## Flow

```text
caller-owned native package manifest SHA-256
  -> native_pipeline.verify_rigid_package
  -> exact declared .gltf/.bin/PNG source bytes
  -> deterministic GLB embedding
  -> structural GLB verification
  -> optional exact RTS rigid-proxy request binding
  -> GLB + evidence receipt
```

Run it explicitly:

```bash
python native_glb_delivery.py \
  --package /path/to/native-rigid-package \
  --expected-manifest-sha256 'sha256:...' \
  --output /path/to/asset.glb \
  --receipt /path/to/asset-glb-receipt.json
```

To bind the delivery to an RTS request produced by the existing `axm.rts.forge-unit-request/v0.1` bridge, add:

```bash
  --consumer-request /path/to/forge-request.json
```

The optional RTS binding is intentionally narrow. The request must:

- use exactly `axm.rts.forge-unit-request/v0.1`;
- identify the same asset ID as the verified native package;
- explicitly declare `asset.type: rigid-proxy`;
- explicitly target exactly `threejs` and `glb`.

A normal RTS `character` request is rejected because this native route has no skeleton, skinning, morph targets, or animation. That rejection is part of the contract rather than a missing marketing claim.

## Deterministic derivation

For one exact verified package and caller-owned manifest pin, repeated derivation produces byte-identical GLB output. Geometry remains the provider-verified binary payload. Every glTF-referenced PNG is taken only from the verified package inventory, SHA-256 rechecked after package admission, aligned into the embedded GLB buffer, and rewritten from URI form to `bufferView + image/png` form.

The source package is never mutated. The GLB is a downstream delivery realization, not canonical Game Asset Genome state.

The receipt records:

- exact source package manifest SHA-256;
- source `.gltf`, `.bin`, and image path/byte/hash identities;
- optional canonical RTS request SHA-256 and bounded request identity;
- GLB byte count and SHA-256;
- structural validation evidence;
- explicit false authority for Genome/source mutation, automatic install/adoption, visual approval, merge, and CANON.

## Truth boundary

A PASS means the GLB was deterministically derived from one caller-pinned package that passed the native rigid verifier, and that the resulting container has a valid GLB v2 header/chunk structure with one embedded buffer and embedded PNG material images.

A PASS does **not** prove:

- character rigging or animation;
- visual quality or semantic fitness for a requested unit;
- actual Three.js rendering;
- collision/gameplay correctness;
- producer authorship or signature authenticity;
- license suitability beyond the source package's separately preserved evidence;
- runtime adoption, publication, merge, or CANON.

The existing RTS request is used as an explicit compatibility consumer in CI only. Game Asset Forge keeps standalone operation and gains no RTS runtime dependency.
