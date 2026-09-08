# Native-First Asset Manufacturing

Game Asset Forge should internalize reproducible asset operations where practical instead of making Blender, Houdini, Unreal, Unity, a learned model, hosted service, or another external application part of the machine's identity.

External systems remain useful research references, bridges, accelerators, comparators, and escape hatches. They are not canonical source state and they are not allowed to become required runtime backends for capabilities the Forge calls native or standalone.

## Standalone invariant

The Forge must remain independently operable as an AXM machine.

For any capability claimed as native/standalone:

1. The implementation and state contract live in this repository.
2. Another AXM repository is not required at runtime.
3. A third-party model, DCC, cloud service, hosted API, proprietary application, or external repository is not required at runtime.
4. Removing an optional bridge may reduce convenience, speed, comparison coverage or experimental quality, but it must not make the native capability disappear.
5. Research references may influence architecture and mechanism design without being shipped, embedded, called, wrapped or required.
6. Restricted code, weights, assets or data are never silently absorbed. Only material whose license permits the intended use may be imported, and provenance must be retained.

The current Python host requirement is a declared execution/runtime requirement of the native core, not a specialist capability dependency. The long-term direction may internalize even more of that runtime, but specialist capability ownership is the immediate boundary.

## Research versus dependency

A system can be extremely valuable to AXM without becoming part of AXM.

Examples such as Hunyuan, TRELLIS, Meshy, MetaHuman, Character Creator, Blender, Houdini, KineFX, Simplygon and similar systems may be studied for:

- pipeline decomposition
- intermediate representations
- geometry/material/rigging strategies
- quality gates
- failure modes
- repair loops
- interface design
- performance patterns
- provenance and packaging ideas

The result of that study should be **AXM-owned mechanisms and state contracts** wherever the Forge claims standalone capability.

A research reference becoming unavailable, commercially restricted, jurisdiction-limited, network-only, or otherwise unusable must not invalidate the Forge. At most it removes that reference/bridge from the research or comparison lane.

## Precedent inside AXM

Universal Creation already follows this pattern for a useful visual subset: deterministic local code emits textures, gradients, PBR-style channel maps, SVG/OBJ fixtures, decals, palettes, kits, manifests, and hashes without hidden services. Game Asset Forge extends the same pattern into a much deeper game-asset manufacturing stack.

Do not copy Universal Creation's implementation blindly. Rebuild specialist versions here so this machine remains standalone and can evolve under stricter close-inspection requirements.

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

## Native-first rule

For every pipeline capability, prefer this order:

1. **AXM-native deterministic/process implementation** when we can make it reliable and inspectable.
2. **AXM-native learned/generative implementation** when learned inference genuinely adds capability and the model/runtime is owned or distributable within the standalone boundary.
3. **AXM-owned implementation inspired by open/public research** when a mature external mechanism teaches us how to build the capability ourselves.
4. **Optional open-library adapter** only as a replaceable acceleration/import/export path, never as the sole implementation behind a native capability claim.
5. **External DCC/engine/model/service bridge** only for comparison, validation, migration, experimentation or temporarily unavailable capability, and always labeled optional/non-native.

Native does not mean ignoring existing knowledge. It means the knowledge is converted into AXM-owned capability rather than leaving the machine dependent on somebody else's runtime.

## Dependency test

For any stage, ask:

> If this external thing vanished tomorrow, would Game Asset Forge still possess the capability it claims?

- **Yes**: the external thing is a valid optional bridge/reference.
- **No**: that stage is not yet standalone. Mark it external/blocked/experimental, or internalize the mechanism before claiming it as native.

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

The target is not "never study or connect Blender." The target is that unplugging Blender, Hunyuan, or any other external specialist must not remove the Forge's brain or invalidate a standalone capability claim.
