# Run 3 — Sentinel armor silhouette and fit

This lane continues from merged Run 2 and deliberately avoids the active finger/contact/deformation lanes.

## Mission

Build an original rigid Sentinel armor system over the proven complete human + graphite undersuit substrate. Use strong modern shipped hero-character construction quality as the benchmark without copying recognizable proprietary character designs.

## Required semantic components

- sternum/chest core
- back/spine core
- left/right shoulder plates
- left/right forearm protection
- left/right thigh protection
- left/right shin protection
- biomechanical interface details

These remain separate editable source components. A fused decorative shell is not sufficient.

## Geometry / fit gates

- armor must sit outside the graphite undersuit/body with explicit clearance evidence
- primary plates must be closed/non-manifold-free manufactured shells
- left/right paired parts should preserve deliberate symmetry unless a variant says otherwise
- neutral-pose body/undersuit penetration is a hard failure
- exposed head, hands, major joints and intended articulation zones remain readable
- panel thickness and edge/chamfer language are explicit source parameters

## Visual gates

Promotion requires real Godot front, three-quarter and profile evidence.

A pass requires:

- a stronger readable armored silhouette than the graphite-suit control
- chest/back/shoulder hierarchy readable at whole-character distance
- plate thickness that does not read as paper or oversized blocks
- coherent material separation between cloth, coated armor and exposed mechanical detail
- no obvious floating plates or clipping
- no beauty-lighting workaround that hides fit defects

More triangles, components or changed pixels are not automatic promotion.

## Truth boundary

This lane does not claim production deformation, rifle contact, final LODs, cinematic skin/hair, Three.js parity or Unreal parity. Those remain separate gates.

## Concurrency boundary

Do not modify the active finger/contact/deformation implementations unless a later integration conflict makes it unavoidable. Prefer new armor-specific modules and workflows so the parallel Run 3 lanes can merge independently.
