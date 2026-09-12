# Native rigid assembly donor

Game Asset Forge now has a native rigid-component assembly path selectively adapted from the finished Universal Creation RTS foundry.

Pinned donor:

`mike-axiom-mir/axm-universal-creation@a5cc708457b7e8f33e794fdac648ae65d15a0fb4`

Relevant donor mechanisms:

- `src/axm_uc/rts_foundry.py`
- `tools/blender/verify_rts_batch.py`

## Gap this closes

Before this donor, Game Asset Forge already had strong skinned-character animation and explicit hand/contact sockets, but the generic rigid route still treated most props as one non-animated rigid body. Universal Creation had already developed a lighter mechanism for vehicles, turrets, doors and machinery: named rigid components, explicit pivots, authored node animation and sockets.

`native_rigid_assembly.py` brings that mechanism into Forge-owned state without treating it as a skeleton.

## Contract

A `RigidAssembly` contains:

- named `RigidComponent` records;
- one explicit bind pivot per component;
- one or more material primitives per component;
- optional `RigidMotion` records;
- optional component-local `RigidSocket` records.

The compiler moves component geometry into pivot-local mesh coordinates and writes the pivot back as the glTF node translation. Motion is standard glTF node rotation animation generated from an explicit axis, explicit angle samples, duration and interpolation.

Sockets remain metadata. They do not silently attach another asset or claim gameplay behavior.

## Independent verification

The delivery validator independently checks:

- the assembly-state digest;
- node identity against declared components;
- exact node translation against declared pivots;
- animation target identity;
- decoded animation time samples;
- strictly increasing finite time values;
- normalized decoded quaternions;
- decoded quaternion agreement with the declared axis/angle samples;
- one delivered motion for every declared motion and no extra target;
- socket component identity, position, direction and coordinate-space declaration.

The integration test intentionally corrupts animation payload bytes and requires validation to fail.

## Relationship to skeletal animation

Rigid assembly and skeletal animation are separate capabilities.

Use rigid assembly for things such as:

- wheels;
- turrets;
- hinged mechanisms;
- doors;
- cranes;
- rotating industrial parts;
- rigid equipment subassemblies.

Use the existing character rig/skin path for deforming characters. A rigid node animation does not become skinned deformation merely because both are represented in glTF.

## Current truth boundary

A passing rigid assembly proves the declared component/pivot/socket state and decoded authored node-animation samples in the generated glTF.

It does not prove:

- physics behavior;
- collider correctness;
- IK;
- gameplay logic;
- target-engine performance;
- visual quality;
- release readiness;
- automatic Genome adoption;
- CANON.

The next useful Universal Creation donor after this is its explicit coarse collision/navigation proxy contract, because the generic Forge rigid package still has only an AABB fallback.
