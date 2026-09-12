# Native PBR rehearsal v0.1

`native_pbr_rehearsal.py` adapts one useful FrameState mechanism into Game Asset Forge:

`produce -> measure -> propose one bounded repair -> produce again -> accept only when the named evidence improves without protected regressions`

This is a technical rehearsal loop, not an aesthetic optimizer.

## Current scope

The first bounded adapter works only with `native_pbr.py` painted-metal manifests (`axm.game-assets.native-pbr.v0.2`). It reads the exact authored spec and existing material signal review, then may create candidate material directories without modifying the source material directory.

Current automatic repairs are intentionally narrow:

- if the generated height payload has measured variation but the tangent-normal payload is near-flat, increase the explicitly authored `normal_strength` within policy bounds;
- if the tangent-normal signal has weak positive Z, reduce `normal_strength` within policy bounds.

It deliberately does **not** auto-repair base-colour diversity, roughness variation, aesthetic quality, art-direction fit, or physical PBR correctness.

## Acceptance rule

A candidate is accepted only when all of these are true:

1. the targeted normal warning count decreases;
2. total technical warnings do not increase;
3. the candidate review does not become `HOLD`;
4. every non-normal material payload keeps the exact same SHA-256;
5. the normal payload actually changes.

That means a repair to tangent-normal expression cannot silently rewrite base colour, height, AO, roughness, metallic, or packed ORM bytes.

Rejected attempts remain on disk and are recorded in the rehearsal receipt.

## Example

```bash
python native_pbr_rehearsal.py \
  build/material/material.json \
  build/material-rehearsal \
  --max-passes 4
```

The output directory is create-only. It contains candidate attempt directories plus `rehearsal-receipt.json`.

## Evidence boundary

A successful rehearsal can prove only that one named bounded technical signal improved under the acceptance rule. It does not prove:

- that the material looks better to a person;
- that the material matches an art direction;
- that it is physically correct PBR;
- that it is engine-parity validated;
- that it is approved, released, merged, or CANON.

The source manifest is hashed before rehearsal and checked again at the end. The source material directory is not mutated.

## Provenance

The evidence-improvement discipline is adapted from `mike-axiom-mir/axm-framestate` rehearsal logic. The implementation is native Game Asset Forge Python and does not require FrameState at runtime.

## Why this matters

The Forge now has three separate layers around material iteration:

1. deterministic native material generation;
2. payload/signal observation;
3. evidence-bounded repair rehearsal.

That is a stronger growth pattern than an opaque `make material better` step because every accepted change names the parameter changed, the warning targeted, the before/after evidence, the unchanged protected payloads, and the exact candidate retained.
