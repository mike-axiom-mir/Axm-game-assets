# AXM Game Asset Forge

A standalone AXM specialist machine for manufacturing high-fidelity, game-ready assets with reconstructable state, replaceable specialist stages, provenance, repair loops and in-engine acceptance evidence.

The goal is not:

> AI can make a 3D object.

The goal is:

> AXM can repeatedly manufacture game assets that survive close inspection.

## Current status

The genesis lane now contains both the **truth/evidence spine** and a growing executable native manufacturing stack. It is still not a fake high-end character demo.

Working now:

- Game Asset Genome creation with content hashes
- deterministic intake and stage receipts
- non-sacred DAG recipes with parallel execution waves
- hardware / offline / jurisdiction capability gates
- AXM-native constructive hard-surface modeling
- native mesh transforms, triangulation, normals, topology inspection and collision bounds
- semantic Sentinel armor detail-source progression
- native multires organic surface subdivision, smoothing, localized deformation and deterministic micro-displacement
- sparse fixed-topology target parsing, validation, deterministic blending, composition and lineage
- native semantic target authoring for reusable region/normal deformations
- reconstructable parametric variants with seed/target/topology/geometry digest locks
- receipt-bearing seed bundle importer with basemesh compatibility checks
- optional MakeHuman `hm08` CC0 seed-data route without depending on MakeHuman application code
- native UV state, projection, validation and UV-aware OBJ interchange
- deterministic hard-surface PBR/ORM authoring
- deterministic organic skin maps with subsurface/thickness state
- layered eye geometry: sclera, iris, pupil and cornea
- deterministic iris/sclera material generation and corneal transmission state
- native tangent-frame generation
- dependency-free rigid glTF 2.0 compilation
- native skeleton hierarchy, inverse bind matrices, four-slot skin-weight validation and CPU deformation proof
- native named morph/blendshape delta state
- native skeletal animation state, pose sampling and contact-drift evidence
- machine-readable character-state packet for future learned proposal adapters
- dependency-free character glTF delivery with `JOINTS_0`, `WEIGHTS_0`, skin hierarchy, inverse bind matrices, morph targets and skeletal animation channels
- experimental attribute-aware character LOD carrying UV/skin/morph state with explicit posed deformation-error budgets
- native silhouette/depth/normal diagnostic previews
- end-to-end rigid detail and organic mechanism proofs
- Sentinel-01 difficult proving request
- CI gates across the native stack plus Genome/DAG validation

Still not claimed:

- a production-quality automatically generated Sentinel character
- production-grade human anatomy generation or face fitting
- production deformation-aware retopology
- production rig **inference** or automatic facial rig solving
- final Sentinel LOD0-LOD3 approval in real poses and engine transitions
- high-end hair/cloth/secondary-motion synthesis
- semantic face UV/material zoning, pose wrinkles and corrective shapes at production quality
- real Godot/Three.js/Unreal screenshot, motion and performance acceptance receipts

Those remain research, experimental, blocked for canonization, or incomplete until actually exercised against the real proving asset.

## Native-first rule

Game Asset Forge should absorb reproducible DCC-style operations into the machine where that increases agency, inspectability and repeatability.

Blender, Houdini and other DCCs remain useful accelerators, comparators and escape hatches. They are **not** canonical Forge state and should not be required for operations AXM can perform reliably itself.

The preference order is:

1. AXM-native deterministic/process implementation where reliable.
2. AXM-native learned/generative implementation where inference genuinely adds capability.
3. Replaceable local open-library adapter where reimplementing a mature mechanism adds little value.
4. External DCC/engine bridge for capability not yet internalized or for comparison/validation.
5. Proprietary service only as an explicit optional bridge, never hidden canonical state.

See `docs/NATIVE_FIRST.md`.

## Why a Game Asset Genome

An asset is not just an FBX or GLB. The Forge separates:

1. **Genome**: identity, art direction, dimensions, variants, budgets, targets, lineage and evidence requirements.
2. **Canonical source state**: geometry, parametric targets, high-detail layers, UVs, materials, rig, weights, animation, simulation, VFX and procedural state.
3. **Compiled deliveries**: GLB/FBX/USD, LODs, collisions, compressed textures, engine imports, screenshots, video and performance receipts.

This is what should make transformations such as "same character + winter equipment + older + injured arm + RTS LOD" reconstructable rather than blind regeneration.

## Parametric organic route

The current organic architecture is:

```text
fixed canonical topology
  -> sparse identity/body/face targets
  -> exact parametric state receipt
  -> subdivision / surface detail
  -> skin / eye / hair / cloth layers
  -> rig / weights / morphs / animation
  -> deformation-gated LOD
  -> engine delivery and evidence
```

Target edits happen **before** topology-changing subdivision. Target files remain separate source layers with digests and weights, so a variant can be rebuilt instead of silently baking its history away.

### Optional MakeHuman CC0 seed data

The MakeHuman repository explicitly marks the inspected `hm08` base mesh and target assets as CC0 while the MakeHuman application code is AGPL-3.0. Game Asset Forge therefore treats those verified assets as an optional seed-data source only. It does not import or depend on MakeHuman application logic.

See `research/MAKEHUMAN_CC0_SEED.md`.

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
- LOD0-LOD3 retention
- Godot, Three.js and Unreal delivery/validation

A simpler prop would hide too much of the actual fidelity problem.

### Native hard-surface detail proof

The current rigid Sentinel armor component separates **detail-source progression** from runtime LOD. Its four semantic detail levels grow from:

- 28 triangles / 1 component
- 112 triangles / 4 components
- 428 triangles / 13 components
- 732 triangles / 21 components

Added structure includes a raised core, edge rails, fasteners, vents, service ribs, biomechanical ports, micro-fasteners and a spine channel. Each level passes native UV, visual-diagnostic and structural glTF checks.

### Native organic mechanism proof

A fixed head fixture now proves:

- semantic nose/brow/cheek/jaw targets
- reconstructable target-weight identity state
- topology-preserving variant edits
- two levels of native subdivision
- smoothing and deterministic microdetail
- diagnostic front/side signal changes

The fixture grows from 224 to 3,584 triangles after multires detail. This proves the **mechanism**, not anatomical realism. The next stronger proof is the same pipeline on a suitable human seed topology.

### Experimental character LOD proof

The experimental attribute-aware reducer carries UVs, four-slot skin influences and morph deltas while simplifying. A synthetic skinned fixture currently proves monotonic reduction with structural glTF delivery and a declared deformation-error budget across test poses.

That does **not** approve Sentinel LODs yet. Sentinel must pass the same gates plus visual retention and real engine transition evidence.

## Run the forge spine

Requires only Python 3.11+ for the native core.

```bash
python forge.py self-test
python forge.py init examples/sentinel-request.json build/sentinel
python forge.py plan recipes/sentinel-character.json
python forge.py audit build/sentinel/genome.json
python forge.py doctor
```

CI exercises the native geometry, modeling, hard-surface, multires, target, target-authoring, parametric, seed-bundle, organic proof, skin material, eye, PBR, UV, preview, glTF, packaging, skinning, morph, animation, character-state and character-LOD paths.

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
- Meshy as a capability/pipeline reference, not a required backend
- SkinTokens, UniRig and RigAnything for rig proposal/skinning proposal
- MakeHuman CC0 seed topology/targets as an optional parametric source-data route
- Blender procedural geometry, hair, rigging, bake and repair paths as an optional bridge/reference
- xatlas UV parameterization
- meshoptimizer simplification/runtime optimization
- OpenUSD / UsdSkel layered source composition
- MaterialX and OpenPBR material interchange/shading semantics
- MetaHuman and Character Creator as high-end character pipeline references
- KineFX as a procedural/non-destructive rig architecture reference
- Simplygon reduction + mapping + material-casting patterns

Learned generators and riggers are expected to emit AXM-owned state contracts and pass native evidence gates rather than own canonical state.

See:

- `research/STATE_OF_THE_ART.md`
- `research/capability-registry.json`
- `research/native-organic-registry.json`
- `research/MAKEHUMAN_CC0_SEED.md`

## Architectural rule

The default lifecycle is a **recipe graph**, not sacred law.

For Sentinel-01, UV and rigging can proceed in parallel after retopology; material authoring and animation can likewise advance on separate branches before final engine convergence. Better future models or algorithms should replace individual stages without forcing a rewrite of the whole Forge.

Native validators are gates, not automatic aesthetic judges. A changed screenshot/hash is evidence that a signal changed, not proof that the asset became better.

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
