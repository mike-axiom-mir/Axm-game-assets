# AXM Game Asset Forge

A standalone AXM specialist machine for manufacturing high-fidelity, game-ready assets with reconstructable state, replaceable specialist stages, provenance, repair loops and in-engine acceptance evidence.

The goal is not:

> AI can make a 3D object.

The goal is:

> AXM can repeatedly manufacture game assets that survive close inspection.

## Current status

The genesis lane now contains both the **truth/evidence spine** and the first executable native manufacturing organs. It is still not a fake high-end character demo.

Working now:

- Game Asset Genome creation with content hashes
- deterministic intake and stage receipts
- non-sacred DAG recipes with parallel execution waves
- hardware / offline / jurisdiction capability gates
- AXM-native constructive modeling primitives: profile extrusion, chamfered profiles, cylinders and placement
- native mesh transforms, triangulation, normals, topology inspection, collision bounds and coarse fallback LOD
- native UV state, box/spherical projection, validation and UV-aware OBJ interchange
- deterministic PBR-style micro-surface generation with base color, roughness, metallic, height, normal, AO and engine-ready ORM packing
- native tangent-frame generation
- dependency-free rigid glTF 2.0 compilation
- native skeleton hierarchy, inverse bind matrices, four-slot skin-weight validation and CPU deformation proof
- native named morph/blendshape delta state and validation
- native skeletal animation state, pose sampling and contact-drift evidence
- native machine-readable character-state packet for future learned rig/animation proposal adapters
- dependency-free character glTF delivery with `JOINTS_0`, `WEIGHTS_0`, skin hierarchy, inverse bind matrices, morph targets and skeletal animation channels
- receipt-bearing rigid package route
- Sentinel armor semantic-detail progression and end-to-end native detail proof
- Sentinel-01 difficult proving request
- CI gates across the native stack plus Genome/DAG validation

Still not claimed:

- a production-quality automatically generated Sentinel character
- production organic sculpt/anatomy generation
- production deformation-aware retopology
- production rig **inference** or automatic facial rig solving
- attribute-preserving skinned/morphed runtime LOD generation
- high-end hair/cloth/secondary-motion synthesis
- real Godot/Three.js/Unreal screenshot, motion and performance acceptance receipts

Those capabilities remain research, blocked, or incomplete until they are actually integrated and exercised.

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
- LOD0-LOD3 retention
- Godot, Three.js and Unreal delivery/validation

A simpler prop would hide too much of the actual fidelity problem.

### First native detail proof

The current rigid Sentinel armor component intentionally separates **detail-source progression** from runtime LOD. Its four semantic detail levels grow from:

- 28 triangles / 1 component
- 112 triangles / 4 components
- 428 triangles / 13 components
- 732 triangles / 21 components

Added structure includes a raised core, edge rails, fasteners, vents, service ribs, biomechanical ports, micro-fasteners and a spine channel. Each level passes native UV and structural glTF delivery checks. This proves the machine can add coherent geometry layers; it does **not** prove the full character is high-end yet.

## Run the forge spine

Requires only Python 3.11+ for the native core.

```bash
python forge.py self-test
python forge.py init examples/sentinel-request.json build/sentinel
python forge.py plan recipes/sentinel-character.json
python forge.py audit build/sentinel/genome.json
python forge.py doctor

python native_geometry_test.py
python native_modeling_test.py
python native_hardsurface_test.py
python native_pbr_test.py
python native_uv_test.py
python native_gltf_test.py
python native_pipeline_test.py
python native_detail_proof_test.py
python native_skin_test.py
python native_morph_test.py
python native_animation_test.py
python native_character_state_test.py
python native_character_gltf_test.py
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
- SkinTokens, UniRig and RigAnything for rig proposal/skinning proposal
- Blender procedural geometry, hair, rigging, bake and repair paths as an optional bridge/reference
- xatlas UV parameterization
- meshoptimizer simplification/runtime optimization
- OpenUSD / UsdSkel layered source composition
- MaterialX material interchange
- MetaHuman and Character Creator as high-end character pipeline references
- KineFX as a procedural/non-destructive rig architecture reference
- Simplygon's reduction + mapping + material-casting pattern as an optimization reference

Learned riggers are expected to emit the AXM native character-state contract and pass native validation/deformation gates rather than own canonical state.

See `research/STATE_OF_THE_ART.md` and `research/capability-registry.json`.

## Architectural rule

The default lifecycle is a **recipe graph**, not sacred law.

For Sentinel-01, UV and rigging can proceed in parallel after retopology; material authoring and animation can likewise advance on separate branches before final engine convergence. Better future models or algorithms should replace individual stages without forcing a rewrite of the whole Forge.

The Sentinel recipe now annotates native gates on UV, rig, skinning, animation, facial state and engine packaging. Runtime LOD is explicitly blocked from using the coarse native simplifier for the final skinned/morphed character until attribute preservation exists.

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
