# MakeHuman CC0 seed-data route

Captured: 2026-09-07

## Why this matters

Game Asset Forge needs an organic route that preserves identity and editability instead of generating a new unrelated mesh every time. MakeHuman demonstrates a strong mechanism for this:

**fixed canonical topology + sparse vertex-delta targets + parameter weights**

That mechanism maps cleanly onto the Game Asset Genome. The Forge can ingest seed geometry and target data as source state, then own the mixing, validation, multires detail, rig, animation, LOD, delivery and evidence stages itself.

## License boundary observed

The MakeHuman repository separates application code from asset data.

- `LICENSE.CODE.md` is GNU AGPL v3.
- `LICENSE.ASSETS.md` contains Creative Commons CC0 1.0 Universal.
- `makehuman/data/3dobjs/base.obj` begins with an explicit notice that the mesh asset was released as CC0 in September 2020 and identifies basemesh `hm08`.
- Target files inspected under `makehuman/data/targets/...` likewise carry explicit CC0 notices. For example, `nose/nose-width1-incr.target` states that it was explicitly released as CC0 in September 2020 and declares `# basemesh hm08`.

Useful source references:

- https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.ASSETS.md
- https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.CODE.md
- https://github.com/makehumancommunity/makehuman/blob/master/makehuman/data/3dobjs/base.obj
- https://github.com/makehumancommunity/makehuman/blob/master/makehuman/data/targets/nose/nose-width1-incr.target

Observed blob SHAs at capture time:

- `LICENSE.ASSETS.md`: `f3ede1fc3318f8d794e2cb51924186c62f02f71a`
- `LICENSE.CODE.md`: `4ef32f0833975b98cb4080343c8fd60ab6d0f88c`
- `base.obj`: `d26635e9326e3cca30778fd7b9c00062b03cce09`
- `nose-width1-incr.target`: `db108799ff4614f32bb33f5e7ae4781a2a82349c`

## AXM policy

Do **not** make the MakeHuman application an AXM dependency.

Prefer:

1. optional ingestion of explicitly verified CC0 seed assets/data,
2. AXM-native target parsing and deterministic mixing,
3. AXM-native source-state manifests and reconstruction receipts,
4. AXM-native multires/detail and later learned proposal organs,
5. explicit source/license evidence on every imported seed.

The current native importer does not perform legal verification. It preserves declared license/source evidence and hashes exact files. Human/project policy still decides whether a source is acceptable.

## Target format confirmed

A MakeHuman-compatible target is sparse text with rows:

```text
vertex_index dx dy dz
```

Example shape from the inspected nose-width target:

```text
# basemesh hm08
97 -.001 0 0
104 -.003 0 0
6881 .001 0 0
6888 .003 0 0
```

This is exactly the kind of state the Forge can preserve without baking edits destructively into a new mesh.

## Current AXM implementation

- `native_targets.py`
  - sparse target parsing
  - duplicate/range/finite checks
  - deterministic blending
  - target digests
  - composed-target lineage
  - conversion into AXM morph state
- `native_parametric.py`
  - fixed-topology parametric variants
  - topology + geometry digests
  - target-weight state
  - exact reconstruction with target-digest locks
- `native_seed_bundle.py`
  - hashes the base OBJ and target files
  - checks declared `basemesh` compatibility
  - emits seed/variant OBJ + parametric state + bundle manifest
  - proves reconstruction before acceptance
- `native_surface.py`
  - topology-changing detail comes **after** target application
  - subdivision, smoothing, localized deformation and deterministic micro-displacement

## Truth boundary

This route gives AXM a credible **parametric organic source-state mechanism**. It does not mean the current Forge already produces MetaHuman-level faces.

Missing high-end work still includes:

- selecting/curating suitable seed topology for the Sentinel target
- anatomically meaningful target libraries and semantic regions
- high-quality skin/eye/teeth/hair material systems
- wrinkle/corrective systems tied to pose and expression
- high-frequency pore/crease detail with scale-correct response
- automatic topology-aware rig proposal proven against the real seed
- facial solver and correctives
- real engine close-up validation

MakeHuman is therefore a useful **CC0 seed-data source and mechanism reference**, not the finish line.
