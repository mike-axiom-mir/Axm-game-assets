# Native-First Asset Manufacturing

Game Asset Forge should internalize reproducible asset operations where that increases agency, inspectability, continuity or quality. It should **not** turn "standalone" into an ideological ban on useful, legally compatible libraries or data.

External systems can be research references, embedded compatible components, optional bridges, accelerators, comparators and escape hatches. They must not silently become canonical AXM state or be misrepresented as AXM-native work.

## Standalone invariant

The Forge remains a standalone AXM specialist when:

1. its canonical asset/genome/source-state contracts live here;
2. another AXM repository is not required to understand or reconstruct that state;
3. every external component has an explicit source/license/role boundary;
4. restricted or unclear artifacts are not bundled merely because they were useful research references;
5. optional DCC/model/service bridges can disappear without corrupting canonical state;
6. a capability that depends on a compatible library says so truthfully rather than falsely claiming to be dependency-free.

A mature open library is not automatically a loss of agency. If its license permits redistribution, its role is explicit, and AXM owns the surrounding contract/state/evidence, using it may be wiser than reimplementing the same low-level algorithm for no practical gain.

## Five external-material classes

### A — AXM-native
Original AXM implementation and AXM-owned state contract. External language/runtime/platform requirements are declared separately.

### B — compatible embedded component/data
Open-source or otherwise explicitly redistributable code/data/assets may be used when the **exact artifact** license permits the intended use and jurisdiction.

Requirements:
- source and version pinned;
- exact license verified;
- required LICENSE/NOTICE/attribution retained;
- provenance retained;
- replacement/interface boundary named where practical.

CC0/public-domain-style seed data belongs here, not in "research only".

### C — optional adapter/bridge
Blender, Houdini, engines, learned models, local executables, hosted services and similar specialists may accelerate, validate, compare, import/export or fill an explicitly non-native stage.

Their absence may reduce convenience, speed, quality or coverage, but it must not silently corrupt AXM canonical state.

### D — research/influence only
A system can teach AXM without being part of AXM.

Study:
- papers and public documentation;
- pipeline decomposition;
- intermediate representations;
- geometry/material/rigging strategies;
- quality gates and failure modes;
- repair loops;
- public interfaces and performance patterns.

Then implement the useful mechanism in AXM where appropriate. Research access does **not** authorize copying restricted code, model weights, assets or outputs.

### E — quarantined / unclear
If the source, license, redistribution permission or jurisdiction is unresolved, preserve the reference and mark it HOLD/research-only. Do not delete knowledge and do not ship the artifact.

## Hunyuan versus MakeHuman example

These are deliberately different cases.

- **Hunyuan3D 2.1** is useful as a research/mechanism reference for our EU lane, but its restricted license means it must not become the required backend, bundled model or absorbed artifact unless separate permission makes that lawful.
- **Verified MakeHuman/MPFB CC0 mesh/target data** may be reused as seed material because the asset/data license is the relevant permission. That does not grant permission to import adjacent GPL/AGPL application logic. Preserve exact provenance and never claim AXM invented the original seed.

## Precedent inside AXM

Universal Creation already follows the useful part of this pattern: deterministic local code emits many visual/software primitives while still allowing deliberate donor/import paths when they are understood and admitted into its own structure.

Do not copy Universal Creation's implementation blindly. Rebuild specialist versions here where that produces better game-asset capability; reuse compatible mature mechanisms where reimplementation would add little value.

## Native geometry kernel v0.1

`native_geometry.py` currently provides executable dependency-free operations for:

- mesh representation
- box and UV-sphere primitive generation
- translation, scale, centering, and bounds
- mesh combination
- polygon triangulation
- area-weighted vertex normals
- basic topology inspection
  - invalid indices
  - degenerate faces
  - boundary edges
  - non-manifold edges
  - closed two-manifold candidate check
- AABB collision bounds
- deterministic vertex-cluster LOD fallback
- OBJ read/write with generated normals

The retained test exercises these paths and currently demonstrates a UV sphere LOD chain of 960 -> 108 -> 48 -> 12 triangles plus OBJ round-trip.

## Truth boundary

The native kernel is real, but it is not yet a Blender replacement.

The current LOD fallback does **not** preserve:

- UV seams
- tangent frames
- hard/split normals
- skin weights
- skeleton bindings
- blendshapes / morph targets
- material boundaries
- semantic body regions
- cloth constraints

Therefore it must not be selected for final skinned-character LODs until those preservation gates exist. It is already useful for rigid props, collision proxies, early blockout, diagnostics, fallback generation, and testing the Forge without a DCC installation.

## Native-first preference order

For every pipeline capability, prefer:

1. **AXM-native deterministic/process implementation** when reliable and inspectable.
2. **AXM-native learned/generative implementation** when inference genuinely adds capability and the model/runtime rights fit the target distribution.
3. **Compatible open/local library or data component** when rebuilding a mature mechanism adds little agency or value.
4. **Optional external DCC/engine/model bridge** for acceleration, comparison, validation, migration or capability not yet internalized.
5. **Proprietary/restricted service** only as an explicit optional bridge where its terms permit the intended use; never hidden canonical state.
6. **Research-only reference** when direct artifact use is not permitted or not desirable.

Native does not mean ignoring existing knowledge. Standalone does not mean zero dependencies. The aim is that AXM understands and owns its state/capability boundary instead of becoming an opaque wrapper around somebody else's product.

## Dependency truth test

For any external thing, ask two questions:

> If this vanished tomorrow, what exactly would AXM lose?

> Is that loss stated truthfully and is canonical AXM state still reconstructable?

A compatible library may legitimately provide a low-level mechanism. A proprietary cloud generator secretly holding the only editable source state may not legitimately be described as AXM-native.

## Provenance files

- `THIRD_PARTY.json` — actual imported/used code, assets, data, runtimes and external components.
- `RESEARCH_REFERENCES.json` — systems studied for influence/reference without artifact absorption.

Promotion from research to use requires a new exact source/license review; public availability or GitHub hosting is never the permission grant by itself.

## Next internalization targets

Highest-value deterministic/native work next:

1. mesh welding and duplicate cleanup
2. robust normal/tangent generation with hard-edge policy
3. native UV chart state and fallback unwrap
4. material-slot and seam preservation through mesh transforms
5. stronger simplification that preserves attributes
6. convex/compound collision generation
7. texture baking and dilation pipeline
8. skeletal + skin-weight aware mesh representation
9. morph/blendshape preservation
10. engine-independent scene/asset package compiler

The target is not "never use Blender" or "never depend on a library." The target is **no hidden ownership transfer**: AXM keeps portable canonical state, truthful capability claims, source/license provenance and an explicit replacement boundary.
