# Universal Creation v0.24 donor intake

This lane studies the finished high-detail / RTS foundry state in:

- repository: `mike-axiom-mir/axm-universal-creation`
- pinned commit: `a5cc708457b7e8f33e794fdac648ae65d15a0fb4`
- release state: Universal Creation `v0.24.0`

The goal is **not** to copy the whole Universal Creation machine into Game Asset
Forge. Both repositories have distinct canonical responsibilities. Instead, this
lane extracts small mechanisms that multiply Game Asset Forge without creating a
hidden Universal Creation runtime dependency or silently replacing the Game Asset
Genome.

At the pinned state Universal Creation's new foundry contains a broad deterministic
3D asset catalog and extensive proving tests across structures, vehicles, props and
machines. That makes it a useful donor because the mechanisms were exercised in a
real multi-asset pipeline rather than invented here from scratch.

## Selected donor 1 — multi-family authored surfaces

Universal Creation's salvage/workshop surface work separated two kinds of detail:

- semantic/functional detail that should stay geometry;
- micro/broad surface history that is better expressed through material signals.

The donor surface implementation covered materially distinct steel/metal, wood,
cloth, stone, soil and rubber treatments rather than painting every object with one
noise function.

Game Asset Forge now adapts that idea in:

- `native_surface_families.py`
- `native_surface_families_test.py`

The Forge implementation is stdlib-only and builds on the already-owned
`native_pbr.py` noise and PNG encoder. It does **not** copy Universal Creation's
NumPy/Pillow/Blender runtime dependency.

Current explicit families are:

- `salvage_metal`
- `steel`
- `wood`
- `cloth`
- `stone`
- `soil`
- `rubber`

Each family materializes:

- base colour;
- roughness;
- metallic;
- height;
- tangent normal derived from height;
- ambient occlusion;
- packed ORM as an explicit delivery view.

Every payload is hashed and the authoring state is receipted. The existing
`native_material_signal_audit.py` is exercised against every family so the donor
is immediately connected to the technical signal inspection organ added earlier.

These are procedural authored surfaces, **not measured scans**, and successful
signal inspection is not a claim of beauty, physical BRDF accuracy, engine parity
or AAA quality.

## Selected donor 2 — lossless shared-image GLB packing

Universal Creation's finished RTS pipeline includes a useful production mechanism:
many standalone GLBs can be repacked into portable glTF assets that reference one
content-addressed shared texture store. Duplicate embedded images therefore stop
being copied once per asset.

Game Asset Forge adapts and hardens that mechanism in:

- `native_shared_glb_pack.py`
- `native_shared_glb_pack_test.py`

The Forge implementation:

1. reads one GLB 2.0 container;
2. extracts embedded PNG/JPEG images;
3. names shared payloads by exact SHA-256;
4. keeps geometry/accessor buffer-view payload bytes lossless;
5. repacks retained buffer views with deterministic alignment;
6. recursively remaps `bufferView` references;
7. preserves nodes, meshes, materials, textures, samplers, animations, skins and
   scene structure;
8. verifies every relocated binary view and image after writing;
9. refuses unsupported opaque/compressed buffer extensions instead of pretending
   they were safely rewritten;
10. refuses to overwrite conflicting content-addressed payloads.

The integration proof does not use a synthetic foreign GLB. It starts with a real
Game Asset Forge route:

`native mesh -> native rigid package -> verified self-contained GLB -> shared pack`

Two identical deliveries are then packed into one collection and must resolve to
the same shared image identities.

This is **lossless packaging**, not mesh optimization or texture compression. It
can reduce duplicated storage in asset kits without weakening the original asset
truth.

## Selected donor 3 — readable geometric stencil detail

Universal Creation's foundry also used actual secondary geometry for readable
labels/signage instead of baking every word into a screenshot or opaque texture.
The useful generic mechanism is its compact 3×5 A–Z/0–9 stencil vocabulary.

Game Asset Forge adapts this in:

- `native_stencil_detail.py`
- `native_stencil_detail_test.py`

The output is ordinary native Forge `Mesh` state made from real quads. Unsupported
characters are rejected rather than guessed. A receipt binds the exact text,
requested bounds, resulting topology and donor provenance.

The stencil organ deliberately does **not** choose:

- what an asset should say;
- where signage belongs;
- the material or colour;
- art direction;
- canonical Genome meaning.

Those decisions remain caller/professional/canonical-state responsibilities.

## Why these donors matter for the dense workshop reference

The earlier workshop reference was valuable because its quality came from a stack
of semantically different details: structural shell, tarp/cloth, steel hardware,
wooden work surfaces, rubber pieces, ground/stone, grime and wear, plus readable
signage and many small functional props.

A single universal material or one giant `make detailed` operation cannot express
that structure cleanly. These donors increase the number of small, reusable
capabilities available to a later environment/building pipeline:

`geometry identity + material family + surface history + readable geometric detail + compact shared delivery`

That is directly aligned with the repository's detail-density principle: multiply
small truthful controls, then compose them.

## What was deliberately not copied

The entire Universal Creation RTS foundry, recipe catalog and Blender build stack
were **not** imported wholesale.

Reasons:

- Game Asset Forge already owns a canonical Genome, native geometry, glTF/GLB,
  LOD, material, rig and evidence stack;
- duplicating the whole foundry would create overlapping authorities;
- specific RTS recipes are useful creation proposals, not automatically canonical
  Game Asset families;
- several Universal Creation production tools intentionally use Blender and other
  packages, while the selected Forge donors can remain native/stdlib-only;
- other useful mechanisms such as stairs/ladders/corrugation/cables, industrial
  articulation and richer surface geometry can be ported later when a concrete
  Game Asset need justifies them.

## Relationship to the existing Universal Creation bridge

`universal_creation_asset_bridge.py` remains a proposal-only ingress for the older
Universal Creation 3D forge request/receipt shape it was written against.

The new v0.24 RTS/foundry body is broader and has its own contracts. This donor lane
does **not** claim that every new foundry output automatically satisfies the older
bridge schema. A later adapter should consume the new exact static/foundry output
contract explicitly rather than weakening validation to make mismatched schemas
look compatible.

## Truth and authority boundary

The selected donor mechanisms may produce or transform derived Game Asset data,
but none of them gains authority to:

- mutate a Game Asset Genome automatically;
- install or select itself automatically;
- declare aesthetic acceptance;
- declare physical/PBR certification;
- declare engine/gameplay fitness;
- release, merge or enter CANON.

Donor repository, exact commit and source mechanism are retained in the resulting
implementations. Unsupported state is rejected or held instead of silently
translated.

The four AXM roots remain the merge gate: Truth, Agency / non-domination,
Continuity, and Wisdom before speed.
