# Optional WALMI inner-asset bridge

This bridge gives Game Asset Forge a bounded consumer seam for WALMI's deterministic
`.axmasset` candidates without importing WALMI code or making WALMI a required Forge
dependency.

## Boundary

The provider contract is pinned to `mike-axiom-mir/axm-walmi` PR #7 at exact head
`abe3fd43c588ff2a282298b27e4c0530f8d88fc2`. That provider exposes:

```text
waldo-axm-mirror verify-asset <candidate.axmasset>
waldo-axm-mirror materialize-asset <candidate.axmasset> <new-directory>
```

Game Assets requires the caller to provide that executable explicitly. It does not
search PATH, clone a repository, access the network, install a package, or invoke an
AI model. The normal Forge works exactly as before when WALMI is absent.

The bridge asks WALMI to verify and materialize a candidate, then independently:

- requires a real materialized directory and only regular-file contents;
- bounds file count and total bytes;
- records SHA-256 and byte size for every materialized file;
- requires `asset.png`, `candidate.json`, and `validation.json`;
- strictly parses both JSON evidence files and rejects duplicate keys;
- validates the PNG signature, IHDR, dimensions, hash, and byte count;
- preserves the `.axmasset` file hash separately from WALMI's candidate identity;
- emits a new `PROPOSAL_ONLY` receipt instead of touching the Game Asset Genome.

A provider verification PASS proves the WALMI contract accepted the candidate.
Game Assets' receipt proves what bytes were materialized and admitted at this bridge.
Neither proves visual quality, authorship, asset-license fitness, game compatibility,
engine readiness, promotion, merge authority, or CANON.

## Local use

Build or otherwise obtain the explicitly reviewed `waldo-axm-mirror` provider and a
candidate, then choose new output paths:

```bash
python walmi_asset_bridge.py \
  --provider /path/to/waldo-axm-mirror \
  --candidate /path/to/candidate.axmasset \
  --materialized /tmp/candidate-files \
  --proposal /tmp/game-assets-proposal.json
```

The materialized directory and proposal are caller-owned evidence. Nothing is copied
into `asset_genomes/`, build outputs, seed state, or any promotion path automatically.
An existing destination is refused before the provider runs.

## Interoperability evidence

`.github/workflows/walmi-asset-bridge.yml` checks out the exact provider head, runs
its focused forge/verify/materialize regression, builds its CLI, forges the provider's
real `examples/axm-mirror/inner-asset-recipe.json` fixture, removes the provider source
checkout, and then exercises this bridge using only the built local executable and
candidate. The consumer proof checks exact provider/source pins, proposal-only
authority, materialized inventory, and primary PNG identity.

`integration/walmi-inner-asset-v0.1.json` is the machine-readable integration pin.
It deliberately records the provider's Apache-2.0 **code** license separately from
the generated asset's license, which this bridge does not infer.
