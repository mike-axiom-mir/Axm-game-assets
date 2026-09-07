# Proving Asset: Sentinel-01

## Why this asset

A crate can prove geometry generation. A chair can prove materials. Neither proves the machine we need.

Sentinel-01 is intentionally uncomfortable: a biomechanical human soldier with an exposed face, eyes, short hair, cloth, armor, mechanical surface language and a two-handed rifle. It forces organic and hard-surface systems to coexist and creates measurable deformation, contact and LOD problems.

## Required proof categories

### Form

- recognizable silhouette at gameplay distance
- believable 1.82 m human proportion baseline before stylization
- readable armor/cloth/mechanical hierarchy
- tertiary detail must not flatten primary form

### Surface

- skin, sclera/cornea/iris separation
- cloth weave visible close-up without destructive moire at gameplay distance
- metal/dielectric correctness
- roughness breakup tied to material/history rather than random noise
- normal/displacement frequency separation

### Topology and UV

- deformation-aware shoulders, hips, knees, elbows, mouth and eyes
- declared triangle budgets for LOD0-L0D3
- UV overlap only when explicitly intentional
- measured texel density and padding

### Rig and deformation

- root/pelvis/spine/neck/head
- fingers and weapon sockets
- eyes and jaw
- facial targets or equivalent deformation system
- stress poses with shoulder/hip/knee/elbow closeups

### Motion

- idle, walk, run
- aim/fire
- reload
- start/stop/turn transitions
- foot-slide measurement
- two-hand rifle contact error

### Secondary motion

- cloth/hair/attachment motion is stable and bounded
- no persistent body/weapon clipping

### LOD and performance

- LOD0-L0D3 monotonic budgets
- image-space silhouette/detail loss measured
- transition sweep capture
- target-engine performance receipt

### Engine proof

The accepted version needs gameplay-camera captures from Godot, Three.js and Unreal adapters, or an explicit `blocked` state for any target not yet exercised.

## Canonization rule

Sentinel-01 is not a successful proof merely because a model exists. It becomes a successful proof only when the required visual, behavioral and technical evidence passes the declared profile. Until then it remains an attempt.
