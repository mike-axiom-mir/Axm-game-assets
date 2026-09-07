# AXM Game Asset Forge

A standalone AXM specialist machine for manufacturing high-fidelity, game-ready assets with reconstructable state, replaceable specialist stages, provenance, repair loops and in-engine acceptance evidence.

The goal is not:

> AI can make a 3D object.

The goal is:

> AXM can repeatedly manufacture game assets that survive close inspection.

## Genesis status

The first PR establishes the **truth/evidence spine**, not a fake high-end demo.

Working now:

- Game Asset Genome creation with content hashes
- deterministic intake receipts
- non-sacred DAG recipes with parallel execution waves
- structural quality auditing
- hardware / offline / jurisdiction capability gates
- local environment doctor
- researched adapter registry
- Sentinel-01 difficult proving request
- CI self-test, genome audit and DAG validation

Not claimed yet:

- proven high-end geometry generation
- production retopology/material/rigging/animation adapters
- a Sentinel asset that has passed real in-game visual and performance gates

Those remain `unavailable` or `research_only` until actually integrated and exercised.

## Why a Game Asset Genome

An asset is not just an FBX or GLB. The Forge separates:

1. **Genome**: identity, art direction, dimensions, variants, budgets, targets, lineage and evidence requirements.
2. **Canonical source state**: geometry, high-detail layers, UVs, materials, rig, weights, animation, simulation, VFX and procedural state.
3. **Compiled deliveries**: GLB/FBX/USD, LODs, collisions, compressed textures, engine imports, screenshots, video and performance receipts.

This is what should later make transformations such as "same character + winter equipment + older + injured arm + RTS LOD" reconstructable rather than blind regeneration.

## First proving asset: Sentinel-01

Sentinel-01 is deliberately difficult: a biomechanical human soldier with an exposed face and eyes, short hair, cloth, hard-surface armor, mechanical detail and a two-handed rifle.

It forces the Forge to confront:

- anatomy and silhouette
- skin/eye/hair response
- cloth versus hard-surface materials
- deformation-aware topology
- fingers, eyes, jaw and facial motion
- weapon contacts
- foot planting and transitions
- secondary motion and clipping
- LOD0-L0D3 retention
- Godot, Three.js and Unreal delivery/validation

A simpler prop would hide too much of the actual fidelity problem.

## Run the genesis spine

Requires only Python 3.11+.

```bash
python forge.py self-test
python forge.py init examples/sentinel-request.json build/sentinel
python forge.py plan recipes/sentinel-character.json
python forge.py audit build/sentinel/genome.json
python forge.py doctor
```

Example capability check:

```bash
python forge.py capability geometry_generation \
  --registry research/capability-registry.json \
  --hardware profiles/hardware-gpu24.json \
  --jurisdiction EU
```

The capability check is intentionally allowed to say **blocked**. Missing hardware, offline/network conflicts or recorded license restrictions must never turn into a silent fallback or fake pass.

## Research direction

Current mechanisms being studied include:

- TRELLIS.2 / sparse structured 3D generation and PBR
- Stable Fast 3D reconstruction/material cleanup
- SkinTokens, UniRig and RigAnything for rigging/skinning
- Blender procedural geometry, hair, rigging, bake and repair paths
- xatlas UV parameterization
- meshoptimizer simplification/runtime optimization
- OpenUSD / UsdSkel layered source composition
- MaterialX material interchange
- MetaHuman and Character Creator as high-end character pipeline references
- KineFX as a procedural/non-destructive rig architecture reference
- Simplygon's reduction + mapping + material-casting pattern as an optimization reference

See `research/STATE_OF_THE_ART.md` and `research/capability-registry.json`.

## Architectural rule

The default lifecycle is a **recipe graph**, not sacred law.

For Sentinel-01, UV and rigging can proceed in parallel after retopology; material authoring and animation can likewise advance on separate branches before final engine convergence. Better future models or algorithms should replace individual stages without forcing a rewrite of the whole Forge.

## Roots

- Truth before story.
- No fake capability and no fake "AAA".
- No hidden dependencies.
- No silent rewrite.
- Preserve source/provenance.
- User agency.
- Open/local-first where practical.
- Wisdom over speed.
- Quality is judged in game, not only in pretty previews.

## Repository lane

See `AGENTS.md`.

**One chat = one PR lane.**

This repository remains standalone. `axm-universal-creation` integration comes later through a clean request/result interface.
