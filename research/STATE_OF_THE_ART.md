# Game Asset Forge research notes

Captured: 2026-09-07

The purpose of this research is to extract mechanisms, not clone proprietary assets or turn one vendor into the architecture.

## 1. Geometry and PBR generation

### TRELLIS.2

Microsoft TRELLIS.2 is a strong current image-to-3D reference. It uses a compact sparse O-Voxel representation, a 4B model, handles complex topology and produces full PBR materials. Its surrounding stack separates representation, sparse compute, mesh post-processing/remeshing/decimation/UV work and PBR rendering.

The important lesson for AXM is not "install TRELLIS and call it done." It is that high fidelity emerges from a representation plus specialized downstream processing. This fits the Forge model of replaceable stages.

Source: https://github.com/microsoft/TRELLIS.2

### Hunyuan3D 2.1

Hunyuan3D 2.1 separates shape generation and PBR texture synthesis. That is useful evidence for keeping shape and material stages separable. The upstream repository lists roughly 10 GB VRAM for shape, 21 GB for texture, and 29 GB for the combined path.

Its published Community License also states that the agreement does not apply in the EU, UK and South Korea. Because AXM requires source and license honesty, the registry treats it as research-only and blocks it by default in those jurisdictions rather than quietly making it a dependency.

Source: https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

### Stable Fast 3D

Stable Fast 3D explicitly targets mesh reconstruction with UV unwrapping, illumination disentanglement/delighting and material prediction. This reinforces the need for cleanup and physically meaningful material stages rather than treating a generated RGB texture as finished game material truth.

Source: https://github.com/Stability-AI/stable-fast-3d

## 2. High-end character systems

### MetaHuman

MetaHuman demonstrates a layered character pipeline: identity fitting to standard topology, facial tracking/solve, correctives, facial animation and LOD-specific feature evaluation. The useful mechanism is the layered solve and correction stack.

AXM should learn from this architecture without requiring MetaHuman's backend as canonical state.

Sources:
- https://dev.epicgames.com/documentation/metahuman/mesh-to-metahuman
- https://dev.epicgames.com/documentation/metahuman/the-metahuman-component-for-unreal-engine

### Character Creator 5

Character Creator 5 combines HD morphs/subdivision, digital-human shading, expression wrinkles/displacement, hair, clothing, rigging, retargeting, physics and engine auto-setup. This is strong evidence for the core Forge premise: a convincing character is not one clever mesh. It is a coordinated fidelity stack.

Source: https://manual.reallusion.com/Character-Creator-5/

## 3. Rigging and skinning

### SkinTokens / TokenRig

SkinTokens models skeleton and skin weights as one learned compact autoregressive representation. It is the successor to UniRig and is a strong current research target for local automated rigging.

Source: https://github.com/VAST-AI-Research/SkinTokens

### UniRig

UniRig predicts a skeleton and skinning. Its own documentation notes that skinning quality can degrade substantially when the predicted skeleton is inaccurate. AXM therefore needs an explicit skeleton/deformation gate before accepting downstream skinning.

Source: https://github.com/VAST-AI-Research/UniRig

### RigAnything

RigAnything is another template-free autoregressive rigging path for diverse meshes. It belongs behind the same adapter contract so the Forge can compare outputs rather than hard-code one model.

Source: https://github.com/Isabella98Liu/RigAnything

## 4. Procedural rigging, hair and secondary motion

Houdini KineFX is built around non-destructive procedural character and rig graphs. Blender 4.5 hair Geometry Nodes expose guide interpolation, surface attachment, smoothing, curling and seed-controlled generation.

These systems point toward the same architectural rule: preserve the generative/procedural state for hair, rigs and secondary systems as long as practical. Do not flatten everything into anonymous final triangles too early.

Sources:
- https://www.sidefx.com/docs/houdini/character/kinefx/
- https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/hair/

## 5. UV, baking and optimization

### xatlas

xatlas provides open-source charting, parameterization and packing. Many UV operations can therefore be deterministic and testable instead of model-generated.

Source: https://github.com/jpcy/xatlas

### meshoptimizer

meshoptimizer provides simplification, vertex-cache/overdraw optimization and tangent generation. This is a good fit for measurable LOD generation and runtime optimization gates.

Source: https://github.com/zeux/meshoptimizer

### Simplygon as a pattern reference

Simplygon's production pattern is valuable even if AXM does not depend on the proprietary product: reduction/remeshing, mapping-image generation, material casting and separate impostor generation for far distance.

Source: https://documentation.simplygon.com/

## 6. Canonical source state versus delivery

### OpenUSD / UsdSkel

USD composition supports references/layers and lets weaker and stronger opinions compose without destroying the underlying state. UsdSkel separates skeleton, animation and blendshape data.

This maps well to the proposed Game Asset Genome: identity and lineage in the Genome, editable source layers in native/OpenUSD state, and compiled engine packages downstream.

Sources:
- https://openusd.org/release/api/class_usd_references.html
- https://openusd.org/release/api/usd_skel_page_front.html

### MaterialX

MaterialX provides an open material-description standard and physically based shading nodes. It is a better canonical interchange direction than making one engine shader graph the permanent truth.

Source: https://materialx.org/Specification.html

### glTF 2.0

glTF explicitly targets efficient runtime delivery and supports PBR metallic-roughness materials, skins, morph targets and animation. That makes GLB an excellent compiled target for web/Godot-style delivery, but not the only authoring truth.

Source: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html

## 7. Engine proof is part of asset quality

Godot's retargeting documentation demonstrates that bone rests, mapping and coordinate conventions can make an apparently valid character import incorrectly. Unreal's skeletal LOD and MetaHuman documentation likewise treats deformation features and LOD evaluation as engine behavior, not just DCC concerns.

Therefore Game Asset Forge canonization must eventually require actual engine import/capture/performance receipts.

Sources:
- https://docs.godotengine.org/en/4.5/tutorials/assets_pipeline/retargeting_3d_skeletons.html
- https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-skeletal-mesh-lods-using-fbx-in-unreal-engine

## Architecture conclusion

The strongest direction is a hybrid forge:

1. generative/reconstruction adapters propose broad shape and surface state;
2. deterministic/procedural stages handle topology, UV, baking, compression and measurable optimization where possible;
3. learned/template riggers remain behind explicit deformation gates;
4. hair, cloth and rig procedural state stays reconstructable;
5. engine compilation happens after canonical source state;
6. visual, behavioral and performance evidence is required before canonization.

The central enemy is **state collapse**: flattening too many distinct quality layers into one mesh too early. Once that happens, improving detail means blind regeneration. The Game Asset Genome should instead let the Forge identify and repair the weakest layer while preserving the rest.
