# 2026-09-20 capability convergence

This pass asks one question: **which useful mechanisms learned today in MorphTile and Universal Creation actually improve Game Asset Forge without weakening its specialist architecture?**

The answer is not "copy UC." Game Asset Forge is already stronger in several asset-specific areas. Its Game Asset Genome / canonical source / compiled-delivery split remains authoritative, and its native skeleton, skin, morph, animation, contact and engine-evidence machinery remains the deeper character path.

## What Game Asset Forge already had stronger

Before this pass the Forge already had:

- Game Asset Genome as semantic/canonical identity rather than a finished-file manifest;
- canonical source state separate from GLB/FBX/USD deliveries;
- content hashes, provenance and failed-attempt evidence;
- real skeleton, skin-weight, morph, animation and contact contracts;
- skinned character glTF output;
- native construction primitives and semantic assemblies;
- deterministic PBR map families, skin/eye/hair/fabric specialization;
- source-first edit surfaces for player/AI-safe asset changes;
- proposal-only Universal Creation ingress that refuses inherited acceptance authority.

Those are preserved. A UC `.glb.source.json` sidecar does **not** replace the Genome.

## What was worth absorbing

### 1. Reusable shape grammar instead of only finished builders

MorphTile and today's UC work reinforced that the strongest reusable unit is often a **construction pattern**, not a finished mesh.

`native_form_recipe.py` adds a bounded data-driven recipe language over existing Forge-native geometry:

- profile extrusion;
- lofted sections;
- lathes;
- authored pipe paths;
- beams;
- rings;
- rounded boxes;
- reusable named definitions;
- named numeric definition parameters and per-use overrides;
- bounded repeat loops with loop variables;
- repeated definitions;
- nested translation / rotation / scale composition;
- semantic part ids, material families and roles.

The output remains ordinary Forge `Mesh` / `ConstructionAssembly` state. The recipe is source authority and the mesh is a realization.

This does not claim arbitrary sculpting, arbitrary boolean CSG or production retopology.

### 2. Material response above texture values

Forge already had strong deterministic texture/map generation. What it lacked was today's explicit distinction between **channel values** and **surface behaviour**.

`native_material_response.py` absorbs the pinned AXM-owned response contract as standalone local data. It exposes 13 families composed from eight behaviour organs:

- subsurface;
- sheen;
- anisotropy;
- clear coat;
- micro breakup;
- transmission;
- iridescence;
- wear layering.

The resolver can preserve intent such as `wood-oiled`, `skin-living` or `leaf-thin` without lying that a renderer implements it. Active organs stay `HOLD_RENDERER_BINDING_NOT_TESTED` until a concrete renderer earns evidence.

### 3. Character identity belongs before rig/runtime delivery

Forge already knows how to rig and animate characters. Today's useful addition is the semantic layer around that state.

`native_character_source_profile.py` preserves:

- race id;
- body family;
- semantic body parts;
- equipment / attachment sockets;
- body-family clothing regions;
- per-character or per-part material-response intent.

This is deliberately separate from `native_character_state.py`, which still owns skeleton / skin / morph / animation / contact runtime state.

A clothing region says where compatibility is intended. It is **not** geometric fit proof.

### 4. New UC source-first results should arrive with their causes

The existing UC bridge handled the older forge-directory contract with Blender source, LODs and render proofs. Today's UC can also publish source-first:

`asset.glb + asset.glb.source.json`

`universal_creation_asset_bridge.py --source-asset ...` now verifies that pair, checks byte and source-body digests, preserves the recipe/specification/character semantics that exist, and emits a Game Asset Forge **proposal only**.

UC does not receive Genome mutation, selection, visual approval, runtime adoption, release, merge or CANON authority.

### 5. Intent should route to the specialist machine, not require callers to memorize modules

`asset_intent_router.py` adds a bounded family-grounded planner.

It can select one asset family when:
- the caller gives an explicit family; or
- ordinary language produces one unique bounded family match.

Ambiguous language stays HOLD. A character holding a weapon does not silently decide whether the request is a character asset or a weapon asset.

The plan points at current Forge manufacturing blocks and never equates planning with execution. It is callable through `python forge.py route-intent request.json`, so humans and AI can use the same bounded planning contract without memorizing internal module names.

## What was intentionally not absorbed

- UC creator-source sidecars do not become Forge canonical state.
- UC's static-character limit does not replace Forge's native rig/skin/animation path.
- MorphTile Vault semantics do not create automatic asset-library admission.
- A successful build does not auto-promote reusable parts.
- Material-response contracts do not imply renderer support.
- Intent routing does not auto-execute ambiguous or multi-product requests.
- Visual proof remains separate from structural/runtime evidence.

## Persistence and library rule

A finished Forge asset can be permanent in its own Genome/source state without being promoted into a global reusable library.

Reusable part discovery and any future Vault/library remain explicit admission steps. This preserves the distinction learned today:

**asset persistence != reusable-library storage != blueprint/composition references.**

## Current truth boundary

This convergence strengthens construction vocabulary, material intent, source semantics, UC interoperability and routing. It does not claim:

- unrestricted 3D creation;
- automatic aesthetic judgment;
- production retopology;
- universal clothing fit;
- renderer parity for every material organ;
- universal engine acceptance;
- automatic Genome mutation;
- automatic Vault admission;
- automatic CANON.
