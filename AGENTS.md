# AGENTS.md

## Lane rule

**One chat = one PR lane.** Do not spread work from this chat across unrelated branches or AXM repositories.

## Mission

Build AXM Game Asset Forge into a standalone specialist machine that can repeatedly produce game-ready assets which survive close visual, deformation, animation, optimization, and engine inspection.

## Standalone boundary

**Standalone means AXM owns the capability contract, canonical state, evidence and replacement boundary.** It does **not** mean "never use a library" or "reinvent every mature algorithm."

External things must be classified explicitly:

- **AXM-native** — AXM implementation/state owns the claimed capability.
- **compatible embedded component** — redistributable/open component or data may be used deliberately when its exact license permits the intended use; preserve source, version, license, notices and provenance.
- **optional adapter/bridge** — DCC, engine, model, executable or service may accelerate, compare, validate, import or export without owning canonical AXM state.
- **research/influence only** — study public systems, papers, workflows, interfaces, outputs and quality patterns, then implement the useful mechanism in AXM; restricted artifacts are not imported merely because they were studied.
- **quarantined/unclear** — preserve the research reference but do not ship/canonize the artifact until source and license are resolved.

A compatible library may be required by an implementation **if that dependency is declared and legally redistributable**; in that case the capability must be described truthfully as using that component rather than falsely called dependency-free. The stronger native test is about ownership and replaceability, not ideological zero-dependency purity.

A reference system may influence architecture without becoming a dependency. Do not turn research targets such as Hunyuan, Blender, Houdini, MetaHuman, Character Creator, Meshy, TRELLIS or similar systems into required backends merely because they were studied.

If removing an external specialist also removes canonical state, evidence, or the only path by which a claimed AXM capability can exist, the dependency boundary must be made explicit or the mechanism internalized before calling it AXM-native.

## Non-negotiable roots

1. Truth before story.
2. Never claim a capability that was not actually exercised.
3. Never label output "AAA" from a beauty render alone.
4. Never hide proprietary, paid, cloud, network, model, library, data, or license dependencies.
5. Never silently rewrite canonical source state.
6. Preserve inputs, outputs, tool/model identity, versions, parameters, seeds, hashes, provenance and receipts where available.
7. Prefer AXM-owned native stages where that increases agency, inspectability or continuity; use compatible open components when rebuilding them would add little value.
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
- Research may copy **ideas, mechanisms, measurements, workflow lessons and public interface patterns** into new AXM-owned implementations; it must not silently copy restricted code, weights, assets or runtime rights.
- Open/permissive/CC0 or otherwise explicitly redistributable material may be reused when the exact artifact license permits it; provenance is mandatory and the original source must never be presented as AXM-authored.
- Optional bridges must fail cleanly and never become hidden canonical state.
- `THIRD_PARTY.json` records imported/used external material; research-only references belong in `RESEARCH_REFERENCES.json`.

## First proving asset

Use Sentinel-01: an exposed-face biomechanical human soldier with skin/eyes, short hair, cloth, hard-surface armor, mechanical detail and a two-handed rifle. It deliberately forces anatomy, materials, rigging, facial motion, weapon contacts, secondary motion, LOD and cross-engine validation into one proof.
