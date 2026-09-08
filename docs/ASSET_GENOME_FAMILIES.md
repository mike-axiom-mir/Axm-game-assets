# AXM Asset Genome Families

Game Asset Forge should manufacture more than dead runtime files. It should preserve enough structured state that AXM systems can create, transform, compile, validate, and re-create assets without handing canonical truth to an editor, DCC, service, or game-specific UI.

## Core model

Every supported family follows the same high-level contract:

`canonical genome -> bounded edit/transform packet -> derived variant state -> runtime compile -> evidence`

The internal mechanism can differ radically between a character, rifle, tree, building, material, or VFX system. The shared truth is that AXM owns canonical state and that edits are explicit, replayable, and attributable.

Registered families live in `asset_genomes/families.json`.

## Why this matters for player-facing RPG creation

A deep RPG character creator should not be a second shallow character system made from disconnected sliders. It should be a bounded front-end over the same Character Genome that the Forge uses to manufacture the character.

A game may expose parameters such as:

- body proportions
- facial structure
- age/history bias
- scars/injuries
- hair style and color family
- equipment layers
- material/wear choices

while keeping internal topology, source artifacts, rig truth, provenance, repair state, and compile logic inside the Forge.

The player's selection becomes a small deterministic edit packet. The base character is not destructively rewritten. The saved character can therefore be represented mainly by:

- base genome digest
- edit-surface digest
- bounded parameter values
- variant digest

This also lets an AXM AI use the exact same surface when it creates an NPC, proposes a character, or assists the player.

## Why this matters for game edit engines

The same mechanism applies to other asset families.

A weapon editor can expose barrel class, stock type, sight type, wear amount, or winter wrapping. A building editor can expose floor count, facade family, damage state, or roof type. A vegetation editor can expose age, season, health, wind response, and LOD class.

The editor never needs permission to arbitrarily mutate the canonical asset JSON or mesh. It receives an **edit surface** that defines the safe semantic controls for that game/context.

## Edit surfaces

`schemas/asset-edit-surface.schema.json` defines a surface.

A surface declares:

- `surface_id`
- asset family
- semantic parameter IDs
- the Forge-owned variant-state path each parameter maps onto
- type and bounds/enum values
- which actor classes may edit the parameter: `player`, `ai`, `tool`
- optional UI hints

The packet never contains arbitrary state paths. It can only reference parameter IDs declared by the surface.

This separation is intentional. Different games can expose different surfaces over the same canonical asset.

Examples:

- `examples/sentinel-player-edit-surface.json`
- `examples/sentinel-weapon-edit-surface.json`

## Edit packets

`schemas/asset-edit-packet.schema.json` defines the first packet format.

v0.1 supports only deterministic `set` operations. This is deliberately narrow. Higher-level operations such as `age_character`, `winterize_weapon`, `damage_left_arm`, or `ruin_building` can later compile into validated bounded parameter updates instead of becoming arbitrary mutation hooks.

A packet includes:

- target surface
- base Genome digest
- actor kind/id
- operations
- optional metadata

`native_asset_edit.py` validates and applies the packet to a **copy** of supplied variant state. It returns a new deterministic variant digest and explicitly records `canonical_state_mutated: false`.

## Canonical state vs derived variant state

Canonical state may include information that a player-facing editor should never expose directly:

- topology identity
- source-index maps
- skeleton/skin bindings
- morph storage
- source licenses and provenance
- failed attempts/repair lineage
- engine compile metadata
- hidden implementation details

Derived variant state contains only the result of accepted transformations.

A game can save the derived edit packet plus base digest instead of becoming the owner of the asset source.

## Quality tiers

The shared vocabulary currently includes:

- `prototype`
- `gameplay`
- `hero`
- `hero_closeup`
- `cinematic`
- `mass_rts`
- `mobile`

The same semantic edit may compile differently for different quality tiers. A hero character may use dense face/hair state while the same Genome compiles an RTS representation with much cheaper delivery.

Quality tier does not mean a single score. Acceptance remains split into structural, visual, motion/behavior, runtime/engine, and provenance/truth evidence.

## Character quality target

The long-term character target is **capability parity with the production expectations of top shipped game characters**, not copying a recognizable proprietary design.

A Forge that deserves an `AAA-character-capable` claim must be able to manufacture an original character that survives the same class of scrutiny:

- primary and secondary facial form
- eyes/eyelids/brows/lashes/hair integration
- believable skin response
- body/neck/head continuity
- material separation
- cloth/armor fit
- rig deformation and correctives
- hand/weapon contact
- facial motion and animation
- LOD retention
- real in-engine close inspection and motion evidence

Sentinel-01 is the proving character, not the definition of the capability.

## Family direction

### Character

Genome domains include body, face, skin, eyes, hair, clothing/armor, rig, morphs, animation, contact state, and LODs.

### Weapon

Genome domains include semantic components, frame/receiver, barrel, stock, grip, magazine, attachments, sockets, materials/wear, VFX, interaction state, and LODs.

### Armor/clothing

Genome domains include fit, layered soft/rigid regions, materials, damage, cloth constraints, attachment rules, and LODs.

### Prop

Genome domains include components, materials, interaction points, damage/wear, collision, and LODs.

### Building

Genome domains include footprint, floors, facade, roof, openings, interior linkage, damage, materials, collision/navigation, and LODs.

### Environment kit

Genome domains include biome, modules, scatter, transitions, materials, weathering, and LOD/impostor state.

### Vegetation

Genome domains include species, growth/age, trunk/branch state, leaves, season, health, wind, and LOD/impostor state.

### Material

Genome domains include base response, roughness, metallic state, microdetail, wear/dirt, physical scale, and runtime packing.

### VFX

Genome domains include emitter shape, timing, direction, particles, color, gameplay role, and performance budget.

## Truth boundary

This architecture does **not** claim that all assets should be pure deterministic geometry or that learned/generative systems are unnecessary.

Generative systems may propose geometry, textures, rigs, animations, or variants. Their output should land in AXM-owned state and pass family-specific gates.

Likewise, compatible reusable open components/data may be used deliberately with provenance. Restricted or unclear systems remain reference-only or HOLD. Canonical capability must not be accidentally trapped inside an external service/model/application.

## First executable proof

The current implementation is intentionally small:

- `native_asset_edit.py`
- `native_asset_edit_test.py`
- `native_asset_edit_examples_test.py`
- Character and Weapon edit surfaces/packets under `examples/`

The next evolution should connect edit results to real family transforms/compile recipes rather than expanding the packet language into a general-purpose mutation system.
