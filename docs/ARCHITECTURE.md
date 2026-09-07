# Game Asset Forge Architecture v0.1

## The key split

A game asset is not one file. The Forge treats it as three coupled layers:

1. **Genome** — semantic identity, dimensions, variants, target engines, budgets, quality gates, lineage and provenance.
2. **Canonical source state** — editable geometry, high-detail layers, UV state, material graphs/textures, skeleton, weights, animation, simulation, VFX and procedural graphs.
3. **Compiled deliveries** — GLB/FBX/USD, engine imports, LODs, collisions, compressed textures, screenshots, video and performance receipts.

Shipping files never become the only truth.

## Genome as a reconstructable state graph

The Genome should eventually reference artifact nodes carrying:

- stable id and semantic role
- content hash
- tool/model and version
- parameters and random seed where applicable
- input artifact ids
- output artifact ids
- license/source record
- coordinate/unit convention
- attempt id
- derived-from/supersedes edges
- acceptance evidence

A repair creates a new attempt. It does not erase the failed state that motivated it.

## Recipe graph, not sacred conveyor belt

The lifecycle from the project brief remains a strong default, but the executable plan is a DAG. Asset classes may replace, skip or reorder stages through explicit recipe revisions.

For Sentinel-01, rig construction can start when deformation topology exists while UV/bake/material work continues separately. Animation, facial work, secondary motion, VFX, LOD and collision later converge for engine packaging.

This is why `recipes/sentinel-character.json` is data rather than hard-coded order.

## Stage contract

Every future stage adapter should declare:

- capability required
- input artifact roles
- output artifact roles
- deterministic / generative / hybrid class
- hardware requirements
- network requirements
- jurisdiction/license constraints
- acceptance gates
- evidence required to pass

Unavailable capability returns `blocked` or `unavailable`. It cannot silently pass.

## Fidelity stack

The Forge treats detail as a stack:

- silhouette
- proportion/anatomy
- primary forms
- secondary forms
- tertiary forms
- deformation topology
- UV density/seams
- baked geometric information
- PBR material response
- micro-surface frequency
- wear/history logic
- skin/eyes/hair/cloth/hard-surface specialization
- rig/correctives
- animation contacts and transitions
- facial performance
- secondary motion
- VFX attachment
- LOD image-space retention
- real engine behavior

Improvement should identify the weakest layer and repair that layer without blindly destroying working layers.

## Canonical and delivery formats

Planned canonical interchange where practical:

- **OpenUSD / UsdSkel** for layered composition, variants, skeleton, animation and blendshape interchange.
- **MaterialX/OpenPBR direction** for material graph interchange.
- Native DCC files remain valid source artifacts when they preserve information not carried elsewhere.

Compiled deliveries:

- **glTF/GLB** for portable runtime delivery and web/Godot paths.
- **FBX** only as a DCC/engine adapter when necessary.
- **USD** may also be a delivery format where supported.

## Evidence classes

### Structural

Hashes, file validity, units, transforms, topology statistics, UV overlap, texel density, texture channels, skeleton hierarchy, influence counts.

### Behavioral

Stress-pose deformation, foot slide, hand/weapon contact error, animation transition discontinuity, clipping and simulation stability.

### In-game

Import logs, gameplay-camera captures, lighting variation, LOD sweeps, frame time, draw calls, memory and triangle/texture budgets.

A beauty render by itself cannot canonize an asset.

## Local-first degradation

The orchestration and evidence spine runs without a GPU. Heavy stages are replaceable adapters.

Example tiers:

- CPU / low-memory: Genome, provenance, recipes, audits, deterministic checks and existing-asset processing.
- 8–12 GB VRAM: selected learned rigging/generation adapters and lower-resolution work.
- 24–32+ GB VRAM: heavier image-to-3D/PBR and character stages.
- external compute: optional accelerator, never a hidden requirement.

The same Genome and receipts must survive movement between tiers.

## Universal Creation boundary

Later, Universal Creation should issue a clean request contract and receive:

- canonical asset id + Genome revision
- source-state manifest
- deliveries per engine/profile
- receipts and failed/blocked gates
- available variants
- explicit capability gaps

Game Asset Forge remains a standalone specialist behind that boundary.
