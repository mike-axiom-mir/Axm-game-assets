# Native salvage construction donor

This capability is a second selective intake from the finished Universal Creation
v0.24.0 foundry, pinned to commit:

`a5cc708457b7e8f33e794fdac648ae65d15a0fb4`

The donor mechanism is:

`tools/blender/axm_salvage_construction.py`

Game Asset Forge does not import that Blender module. It adapts two useful
construction ideas into native Y-up `Mesh` + `UVMap` state in
`native_salvage_construction.py`.

## Corrugated sheet

`corrugated_sheet(...)` creates a real profiled shell rather than a flat panel
whose corrugation exists only in a texture.

The recipe exposes:

- width / height;
- explicit thickness;
- deterministic seed;
- corrugation frequency;
- ridge amplitude;
- bounded dent amplitude;
- X/Y subdivisions;
- UV tile scale.

The source donor used Blender Solidify. The Forge version builds both shell layers
and all perimeter bands directly, so topology and thickness remain inspectable
without Blender.

This is useful for:

- workshop walls/roofs;
- salvage cladding;
- improvised barriers;
- sheds and environment kits;
- visibly bent metal panels.

## Pinned cloth / tarp

`cloth_patch(...)` accepts four explicit pinned corners and creates deterministic
cloth/tarp geometry with:

- center sag;
- edge sag;
- bounded flutter;
- asymmetric corner-fold signal;
- explicit subdivisions;
- explicit thickness;
- grid UVs suitable for repeating authored cloth material.

Universal Creation's source was Blender Z-up. Game Asset Forge is Y-up, so the
vertical deformation was adapted explicitly rather than copied with the wrong
axis semantics.

This is an authored geometric deformation recipe, **not a cloth physics solver**.
Thickness is a rest-plane shell approximation, which stays explicit in the
receipt.

## Why this donor belongs in Game Asset Forge

The dense workshop reference that motivated this work contains exactly the kind
of detail these mechanisms protect: a sagging tarp and visibly constructed,
imperfect sheet material. Those forms affect silhouette and spatial readability,
so hiding them entirely in texture detail would lose useful asset truth.

They complement the material-family donor merged earlier:

`real corrugated/tarp form -> explicit UV state -> material family -> signal audit -> preview/evidence`

The geometry and material layers therefore remain composable instead of being
collapsed into one opaque generator.

## Evidence

The dedicated test requires:

- no invalid/degenerate generated faces;
- closed shell topology for the current bounded recipes;
- valid native UV state;
- deterministic repeated generation;
- seed-sensitive corrugated dents;
- pinned cloth intent retained in the receipt;
- measurable cloth center sag;
- successful observation by the existing native front/side/top preview organ;
- create-only OBJ + receipt output;
- degenerate inputs rejected rather than guessed.

## Truth boundary

These functions prove deterministic authored geometry under explicit parameters.
They do not prove:

- physical cloth or sheet simulation;
- structural engineering correctness;
- aesthetic quality;
- engine performance;
- gameplay/collision suitability;
- canonical Genome adoption.

Neither function may automatically install, rewrite a Genome, release, merge or
enter CANON. The four AXM roots remain the merge gate.
