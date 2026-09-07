# Native-First Asset Manufacturing

Game Asset Forge should internalize reproducible asset operations where practical instead of making Blender, Houdini, Unreal, Unity, or another DCC application part of the machine's identity.

External tools remain useful bridges, accelerators, comparators, and escape hatches. They are not the canonical source of truth.

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
2. **AXM-native learned/generative implementation** when learned inference genuinely adds capability.
3. **Open replaceable library adapter** when rebuilding the mechanism would waste effort without increasing agency.
4. **External DCC/engine bridge** when it provides capability we have not yet reproduced or when it serves as a reference comparator.
5. **Proprietary service** only as an optional, explicit bridge and never as hidden canonical state.

Native does not mean "rewrite every mature algorithm from scratch." A local open library can still be part of the machine if its license, source, inputs, outputs, and replacement boundary are explicit.

## Next internalization targets

Highest-value deterministic/native work next:

1. mesh welding and duplicate cleanup
2. robust normal/tangent generation with hard-edge policy
3. UV chart state and atlas adapter, then an AXM fallback unwrap
4. material-slot and seam preservation through mesh transforms
5. stronger simplification that preserves attributes
6. convex/compound collision generation
7. texture baking and dilation pipeline
8. skeletal + skin-weight aware mesh representation
9. morph/blendshape preservation
10. engine-independent scene/asset package compiler

The target is not "never use Blender." The target is that unplugging Blender should reduce optional capability rather than remove the Forge's brain.
