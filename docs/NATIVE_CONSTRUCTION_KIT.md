# Native construction kit donor

Game Asset Forge now owns a dependency-free Y-up construction toolkit selectively adapted from the finished Universal Creation RTS foundry.

Pinned donor:

`mike-axiom-mir/axm-universal-creation@a5cc708457b7e8f33e794fdac648ae65d15a0fb4`

Relevant donor mechanisms:

- `src/axm_uc/surface_geometry.py`
- `src/axm_uc/rts_mesh.py`
- `src/axm_uc/rts_recipes.py`

The point of the transplant is not to copy the RTS catalog. It is to bring the reusable construction language into the asset-specific machine.

## Native primitives

`native_construction_kit.py` currently provides:

- arbitrary oriented closed rectangular beams;
- closed authored pipe/cable paths;
- torus/ring geometry with X/Y/Z axes;
- radius/height lathe solids;
- chamfered/rounded boxes;
- semantic assemblies for ladders, barrels, crates, railings and cranes.

Every semantic assembly keeps explicit part identity, material-family intent and semantic role. That lets later Game Asset stages preserve distinctions such as wood ladder rails versus steel rungs, a salvage-metal barrel body versus steel hoops, or crane structure versus hydraulic/cable parts.

## Why it matters

The newer Universal Creation assets are visually stronger partly because they are composed from many understandable construction elements instead of one low-detail shell. Dense environment assets need geometry-level details that survive camera motion and silhouette changes:

`primary structure -> secondary construction -> pipes / rails / braces -> material families -> wear/detail -> evidence`

This donor closes part of that structural-detail gap without making Universal Creation a runtime dependency.

## Composition with existing Forge organs

A typical native route can now be:

1. author primary form with `native_geometry.py` / `native_modeling.py`;
2. add real corrugated sheet or tarp shells with `native_salvage_construction.py`;
3. add beams, pipes, railings, ladders, barrels, crates or cranes with `native_construction_kit.py`;
4. add geometric lettering with `native_stencil_detail.py`;
5. assign material families from `native_surface_families.py`;
6. UV/project explicitly with `native_uv.py`;
7. compile multi-material delivery with `native_multi_gltf.py`;
8. inspect through native preview/evidence and engine gates.

The toolkit does not automatically perform those later steps or mutate the Game Asset Genome.

## Evidence

The dedicated donor tests require generic primitives and semantic assembly parts to have:

- no invalid indices;
- no degenerate faces;
- no boundary or non-manifold edges;
- valid world-space UV projection through the existing Forge UV organ;
- deterministic repeated construction;
- observable output through the existing native preview renderer;
- explicit donor provenance and false automatic authority flags.

## Truth boundary

This capability proves deterministic authored geometry for the supported bounded recipes.

It does **not** prove:

- structural-engineering correctness;
- physics behaviour;
- collision suitability;
- target-engine performance;
- visual quality or art-direction fit;
- gameplay correctness;
- release readiness;
- CANON.

The Universal Creation catalog remains separate. Only generic reusable mechanisms are transplanted here.
