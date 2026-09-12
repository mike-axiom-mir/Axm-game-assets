# AXM code-multiplier transplants — Game Asset Forge

This lane reuses working mechanisms from other AXM repositories by **porting the
mechanism into Game Asset Forge's native Python body**. It does not add hidden
runtime dependencies on those repositories and it does not transfer canonical
asset authority away from Game Asset Forge.

The first two transplants are deliberately small and evidence-oriented:

1. Material / Surface Fabric's payload + pixel-signal diagnostics.
2. FrameState's stable, caller-pinned evidence verification pattern.

They strengthen the Forge immediately while the broader Universal Creation 3D
path continues to grow.

## 1. Native material payload + signal audit

Source mechanisms studied and ported:

- `mike-axiom-mir/axm-material-surface-fabric/payload-audit-core.js`
- `mike-axiom-mir/axm-material-surface-fabric/signal-audit-core.js`
- `mike-axiom-mir/axm-material-surface-fabric/tools/png-pixels.js`

Game Asset implementation:

- `native_material_signal_audit.py`
- `native_material_signal_audit_test.py`

The port remains Python-standard-library-only. It does not shell out to Node and
does not import Material / Surface Fabric.

### Request

The tool audits one **explicitly declared material family**. It never guesses
material semantics from filenames.

```json
{
  "schema": "axm.game-assets.material-audit-request/v0.1",
  "family_id": "painted-workshop-panel",
  "entries": [
    {
      "id": "panel-base",
      "channel": "base-color",
      "path": "materials/panel-base.png"
    },
    {
      "id": "panel-normal",
      "channel": "normal",
      "path": "materials/panel-normal.png"
    },
    {
      "id": "panel-roughness",
      "channel": "roughness",
      "path": "materials/panel-roughness.png"
    }
  ]
}
```

Run:

```bash
python native_material_signal_audit.py material-audit-request.json \
  --output build/panel-material-audit.json
```

Relative payload paths are resolved against the request file's directory.
Payload paths may not escape that directory or cross symlinks.

### What it checks

For PNG/JPEG/WebP it performs bounded container checks. PNG additionally has a
native 8-bit, non-interlaced pixel decoder for grayscale, RGB, indexed,
grayscale-alpha and RGBA images.

For PNGs it can record:

- RGBA mean and standard deviation;
- grayscale share;
- visible/partial alpha share;
- coarse colour-bin diversity;
- horizontal edge-energy signal;
- tangent-normal mean vector length;
- tangent-normal broad valid-length share;
- mean tangent-normal Z.

Warnings currently include:

- `near-flat-signal`
- `scalar-channel-color-leak`
- `normal-map-near-grayscale`
- `normal-positive-z-weak`
- `normal-vector-length-irregular`
- `low-signal-diversity`
- `fully-transparent-signal`
- `duplicate-payload-across-channels:*`

A warning is a diagnostic, **not a quality verdict**. A roughness map may be
technically suspicious without proving an asset is aesthetically poor, and a
clean audit never means the material is beautiful, physically calibrated, PBR
certified or AAA.

Unsupported-but-structurally-valid image encodings stay visible as
`STRUCTURE_ONLY`; broken or unsafe evidence becomes `HOLD`.

## 2. Native caller-pinned evidence bundle verifier

Source mechanism studied and generalized:

- `mike-axiom-mir/axm-framestate/src/axm_framestate/render_verify.py`

Game Asset implementation:

- `native_evidence_verify.py`
- `native_evidence_verify_test.py`

The useful FrameState idea is stronger than simply hashing a directory. Evidence
is accepted only when the caller supplies the exact manifest digest expected,
the manifest's own digest still matches its content, and every declared file
still has the exact hash/length claimed.

The verifier also retains FrameState's stable-file pattern:

1. `lstat` before opening;
2. `fstat` on the opened file;
3. stream/hash the bytes;
4. `fstat` again before close;
5. `lstat` after;
6. reject if device/inode/size/mtime/ctime changed at any point.

This closes an important evidence race without turning the verifier into an
asset-quality authority.

### Manifest

```json
{
  "schema": "axm.game-assets.evidence-bundle/v0.1",
  "bundle_id": "workshop-turntable-v1",
  "files": [
    {
      "path": "renders/front.png",
      "sha256": "sha256:<64 lowercase hex>",
      "bytes": 12345,
      "role": "front-view"
    }
  ],
  "manifest_digest": "sha256:<digest of manifest without this field>"
}
```

Verify:

```bash
python native_evidence_verify.py build/workshop-evidence \
  evidence-manifest.json \
  --expected-manifest-digest sha256:<caller-pin> \
  --output build/workshop-evidence-verification.json
```

The verifier is read-only. Its optional receipt output is create-only.

### What PASS means

PASS means the caller-pinned manifest and every declared regular, non-symlink
in-tree file had the exact bytes claimed at verification time.

PASS does **not** mean:

- the images look good;
- the GLB is game-ready;
- the evidence was produced by the tool named in metadata;
- authorship/license claims are true;
- the asset is accepted;
- the asset may release, merge or enter CANON.

## Why these were transplanted first

Game Asset Forge already has strong geometry, rig, material-generation, engine
and visual-evidence mechanisms. The missing multiplier was not another giant
generator. It was stronger reusable inspection around the growing output volume.

Material signal audit helps answer:

> Are the material bytes/signals obviously broken or suspicious?

The evidence verifier helps answer:

> Are these still exactly the bytes we reviewed and pinned?

Those questions are prerequisites for trustworthy high-detail asset iteration.

## Next donor mechanisms worth adapting

FrameState also has two useful mechanisms that should be evaluated in a later
bounded lane rather than copied blindly:

- crash-resumable/checkpointed long render work;
- rehearsal loops that accept a bounded repair only when target evidence improves
  without increasing protected regressions.

Those are not claimed by this change.

## Roots

**Truth** — technical signal, exact byte identity and aesthetic judgment remain
different evidence planes.

**Agency / non-domination** — neither tool installs, promotes, rewrites a Genome,
merges, releases or canonizes an asset.

**Continuity** — exact payload SHA-256, manifest pins, reports and receipts keep
the reviewed state traceable.

**Wisdom before speed** — suspicious or unsupported evidence stays warning/HOLD;
the machine does not convert structural success into an art-quality claim.
