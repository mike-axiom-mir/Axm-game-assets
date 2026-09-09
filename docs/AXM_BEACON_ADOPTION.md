# Game Asset Forge Organ Beacon

Game Asset Forge adopts `axm-beacon/0.1` as a local, optional discovery and
proposal transport. The implementation is adapted from AXM Discovery Buddy
`main@0ef4e93f30e6aeba7ab1bdc524d82bde6460177b`, inspected on 2026-09-09.
Each repository carries its own executable copy; Game Asset Forge does not
import Discovery Buddy or any peer at runtime.

## Local commands

```bash
python .axm/beacon/beacon.py publish --base HEAD^ --head HEAD --output-dir /tmp/asset-forge-feed
python .axm/beacon/beacon.py scan --feed-dir tests/fixtures/axm_beacon_reference_index.json
python .axm/beacon/beacon.py fetch --repo owner/repo --capsule-id <sha256>
python .axm/beacon/beacon.py verify .axm/beacon/inbox/<sha256>/capsule.json
```

The publish command creates deterministic capsule and patch identities from an
exact Git range. The scan command ranks evidence against asset-domain interests.
Fetch writes only to `.axm/beacon/inbox/<capsule-id>/` and records that nothing
was applied.

## Export boundary

The publisher uses an allowlist for Forge code, tests, contracts, recipes,
profiles, registries, and documentation. Seed assets, build outputs, private or
quarantined paths, environment files, credentials, keys, and local Beacon
transport state are excluded. These exclusions do not decide copyright or
license status; existing `THIRD_PARTY.json`, `RESEARCH_REFERENCES.json`, and the
repository's provenance rules remain authoritative.

The checked-in reference fixture preserves the exact Discovery Buddy capsule
identity requested by issue #5. It is a deterministic scan input, not copied
runtime code, correctness evidence, or CANON.

## Authority boundary

Attention and relevance are triage signals only. A received capsule may contain
an idea, mechanism, test, or patch worth inspecting, but it cannot update the
Game Asset Genome, source state, delivery assets, or any other canonical file.
Adoption still requires explicit human/AI review and this repository's own
tests, visual gates, provenance checks, and merge authority.
