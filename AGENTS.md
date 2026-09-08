# AGENTS.md

## Lane rule

**One chat = one PR lane.** Do not spread work from this chat across unrelated branches or AXM repositories.

## Mission

Build AXM Game Asset Forge into a standalone specialist machine that can repeatedly produce game-ready assets which survive close visual, deformation, animation, optimization, and engine inspection.

## Standalone boundary

**Standalone means the Forge owns the capability it claims.** A claimed core capability must not require another AXM repository, external model/service, proprietary DCC, hosted API, or third-party application to exist at runtime.

The only baseline runtime dependency may be the explicitly declared host/runtime needed to execute the Forge itself (for example Python where the current native core requires it). Everything else is either:

- **research/influence**: study public systems, papers, workflows, interfaces, outputs and quality patterns, then implement an AXM-owned equivalent;
- **optional bridge/comparator**: useful for acceleration, validation, import/export or experimentation, but removable without invalidating the Forge's native capability claims;
- **optional source/data import**: allowed only when the source/data license permits it, with provenance retained, and never required for the Forge to function.

A reference system may influence architecture without becoming a dependency. Do not turn research targets such as Hunyuan, Blender, Houdini, MetaHuman, Character Creator, Meshy, TRELLIS or similar systems into required backends merely because they were studied.

If unplugging an external system removes a capability we call native/standalone, the architecture has drifted and must be repaired.

## Non-negotiable roots

1. Truth before story.
2. Never claim a capability that was not actually exercised.
3. Never label output "AAA" from a beauty render alone.
4. Never hide proprietary, paid, cloud, network, model, library, data, or license dependencies.
5. Never silently rewrite canonical source state.
6. Preserve inputs, outputs, tool/model identity, versions, parameters, seeds, hashes, provenance and receipts where available.
7. Prefer AXM-owned native stages for claimed capability. External specialists may sit behind optional adapter boundaries but cannot be required to make a native claim true.
8. If a stage is unavailable, record `blocked` or `unavailable`, never `pass`.
9. Quality must eventually include real engine screenshots/video and performance evidence.
10. User agency and wisdom over speed.

## Build discipline

- The Game Asset Genome is semantic/canonical state, not merely an FBX/GLB manifest.
- Source state and delivery assets are separate layers.
- GLB/FBX are compiled deliveries, not the whole source of truth.
- Repair loops append attempts and receipts; they do not erase failed attempts.
- Engine-specific transforms happen downstream of canonical state.
- A proxy may exercise plumbing but must be labeled as a proxy.
- Universal Creation integration comes later through a clean request/result contract.
- Research may copy **ideas, mechanisms, measurements, workflow lessons and public interface patterns** into new AXM-owned implementations; it must not silently copy restricted code, weights, assets or licensed runtime requirements.
- Optional bridges must fail cleanly. Their absence may reduce convenience or comparison coverage, but must not erase the standalone machine's core truth.

## First proving asset

Use Sentinel-01: an exposed-face biomechanical human soldier with skin/eyes, short hair, cloth, hard-surface armor, mechanical detail and a two-handed rifle. It deliberately forces anatomy, materials, rigging, facial motion, weapon contacts, secondary motion, LOD and cross-engine validation into one proof.
