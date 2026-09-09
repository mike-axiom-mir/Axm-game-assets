# Run 3 — hm08 face motion

This lane starts from merged Run 2 and stays independent of the active Run 3 armor, finger-grip, and contact/deformation lanes.

## Mission

Add a first real motion layer to the proven hm08 Sentinel face without replacing or destructively editing the accepted neutral identity.

The motion source must remain deterministic, reversible, topology-preserving, and grounded in the canonical hm08 geometry plus existing AXM facial landmarks.

## Required motion channels

- left blink
- right blink
- left brow raise
- right brow raise
- smile
- frown
- jaw open

These are source motion targets, not a claim of final facial animation quality.

## Hard gates

- the neutral face with all motion weights at zero is vertex-for-vertex and face-for-face identical to the current identity substrate
- every target is a sparse reversible delta over the same 4,197-vertex repaired hm08 topology
- target generation is deterministic
- every target moves real geometry
- maximum authored displacement stays bounded to a low-millimeter facial-motion envelope
- left/right blink and brow target coverage stays intentionally near-symmetric
- meter-space morph targets validate through the existing native morph engine
- authored motion clips validate through the existing morph-weight animation engine
- no proprietary facial scan, proprietary animation data, or biometric identity data is introduced

## Truth boundary

A deterministic target or valid glTF animation channel is not automatic visual approval.

This lane does **not** claim:

- final FACS/anatomical fidelity
- final lip seal or speech shapes
- teeth/tongue deformation
- cinematic wrinkle behavior
- final eye-lid/cornea contact
- final emotion acting
- production facial rig quality

Those require real Godot close-up evidence and later human visual judgment.

## Concurrency boundary

Do not modify the active armor, finger-grip, rifle-contact, or body-deformation implementations. Prefer new hm08 face-motion files and an isolated test workflow so the parallel Run 3 lanes can merge independently.
