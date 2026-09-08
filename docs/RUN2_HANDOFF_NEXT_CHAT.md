# Game Asset Forge — Run 2 handoff

This file closes the long Sentinel fidelity lane and is the starting point for a fresh builder chat.

## Repo / lane

- Repository: `mike-axiom-mir/Axm-game-assets` (legacy repository name)
- Closing PR: #3 `Run 2: Sentinel fidelity escalation`
- Run 2 branch: `forge/chat-2026-09-08-sentinel-fidelity`
- After PR #3 merges, the next chat should branch from current `main` and open one new PR lane. Do not continue writing to the merged Run 2 branch.

## Mission that remains

Game Asset Forge should be capable of manufacturing an **original** game character that survives the same class of scrutiny expected from strong modern shipped hero characters. Quality parity is the benchmark; copying recognizable proprietary character designs is not.

Do not start another broad architecture phase. The current architecture is already extensive. Prefer changes that visibly improve an in-engine asset or close a real production gate.

## Proven substrate at end of Run 2

### Human source / identity

- Preferred human head seed: `seed_data/hm08_head_v0.2/`
- Preferred complete body seed: `seed_data/hm08_full_body_v0.1/`
- Complete body is one closed continuous human surface: **13,380 vertices / 13,378 faces / 0 boundary edges**.
- The complete body contains the promoted upper-body source set **10,185 / 10,185** and promoted head source set **4,197 / 4,197**.
- The Sentinel facial target mix reproduces **zero positional drift** across the shared promoted head and upper-body source vertices.
- Canonical MakeHuman coordinates remain raw source state; engine delivery converts dm → m explicitly with `0.1` scale.

### Face / skin / eyes / hair

Current preferred direction:

- repaired hm08 v0.2 human topology
- physical-space skin authoring `physical_v0.1`
- source-grounded eye centers/radius from pinned helper-eye metadata
- brow route: continuous surface placement + dense groom + dedicated density material (`v0.3` route)
- upper lashes: repaired `v0.2` route
- short hair: scalp root-mass underlay + laid card detail

Important truth boundary:

- This is not finished cinematic skin/eye/hair quality.
- Cornea is still a prototype clear layer rather than physical refraction.
- Tearline/wetness, stronger facial secondary forms, production hairline/card breakup and expression-dependent detail remain later fidelity work.

### Complete character substrate

`native_hm08_full_body_current.py` currently assembles:

- complete closed human body
- preserved Sentinel face identity
- layered eyes
- brows
- upper lashes
- scalp underlay + laid hair cards
- graphite fitted undersuit

The graphite undersuit:

- is a separate source-derived shell, not painted skin
- offsets from the body by ~**2.2 mm**
- preserves source UV relationship
- leaves head/hands/feet exposed
- covers ~**73.8% of physical body surface area**
- is a garment substrate, not finished tailoring

The current Godot package has **10 semantic material primitives** including the undersuit.

### Engine evidence

Godot is the current real evidence laboratory.

Pinned Godot version: **4.7.2 stable**
archive SHA256: `cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4`

At the pre-handoff Run 2 head (`ea59e31c7b50cf6ca257b22ffd25799fed217ffb`) all of these were green on the same commit:

- `forge-tests`
- `godot-face-current-smoke`
- `godot-upper-body-current-smoke`
- `godot-full-body-current-smoke`

The full-body evidence detector was repaired so dark graphite clothing is measured against the known dark background without weakening the existing silhouette-size or near-white exposure gates.

## Rejected / non-promoted experiments

Preserve these as evidence. Do not silently resurrect them as defaults.

- hm08 head v0.1: structurally valid but visually rejected because aggressive cropping damaged scalp/side boundaries.
- early generic UV-space skin: rejected as preferred route because atlas-scale noise created giant blotchy skin detail.
- semantic skin v0.1: experimental and not promoted; an early mouth landmark assumption was wrong.
- triangle-subdivision + smoothing face: rejected because triangulation created directional rippling.
- Catmull-Clark face candidate: technically valid but visual improvement too small for the 4× triangle cost.
- first brow passes: dotted/stippled; superseded by dedicated brow density material.
- lash v0.1: too high/vertical; superseded by v0.2.
- scalp-hair v0.1: sparse scratches, temple/ear leakage, random tails.
- laid scalp cards alone: placement improved but insufficient continuous hair mass; underlay + cards is preferred direction.

## Licensing / provenance boundary

Use precise wording so research references are not confused with dependencies.

- **Hunyuan3D**: REFERENCE / INFLUENCE ONLY. Do not ingest code, weights, outputs, or make it a runtime dependency for this EU workflow.
- **MakeHuman application code**: not imported into Forge.
- **MakeHuman hm08 base mesh and targets used here**: CC0 source data with pinned provenance.
- **MPFB application code**: not imported into Forge.
- **MPFB hm08 mesh metadata used here**: treat only the verified reusable mesh-data boundary with provenance.
- Compatible open libraries may be used deliberately when appropriate, but canonical Forge state and capability must not be secretly trapped inside an external application/service/model.
- Unclear or incompatible material stays HOLD / research-only until verified.

## Shared asset/edit architecture already present

Do not rebuild it unless a real production need exposes a gap.

The repository now has the beginnings of a shared Asset Genome / Edit Surface model:

`canonical genome → bounded edit packet → derived variant → compile → evidence`

The same idea is intended for characters, weapons, armor/clothing, props, buildings, environment kits, vegetation, materials and VFX.

A player-facing RPG character creator can therefore become a controlled frontend over the same deterministic character state rather than a separate shallow slider system.

## Next build lane — priority order

### 1. Rigid Sentinel armor

This is the immediate next task.

Build an **original** armor silhouette over the proven graphite undersuit. Use top shipped game-character quality expectations only as a quality benchmark.

Start with separate semantic components, not one fused decorative blob:

- chest / sternum core
- back/spine core
- left/right shoulder plates
- forearm protection
- thigh / shin protection
- biomechanical interface details

Requirements:

- real clearance over the undersuit/body
- strong readable primary silhouette before microdetail
- manufactured edge/bevel language
- coherent panel thickness / fit
- material separation
- no clipping in neutral pose
- preserve components as editable source state
- Godot front / 3-quarter / profile evidence before promotion

Reuse existing native hard-surface mechanisms where useful, but do not simply scale the old rectangular armor proof onto the body and call it finished.

### 2. Integrate the existing rifle with the complete character

After armor silhouette is useful:

- attach rifle as a real character layer
- establish right-hand primary grip + left support contact
- preserve sockets / attachment state
- judge weapon scale against the full body
- repair weapon construction where whole-character evidence exposes toy-like detail

### 3. Rig / deformation

Turn structural rig capability into a production character proof:

- shoulders
- elbows
- wrists
- fingers
- hips
- knees
- jaw
- eyelids / eyes
- corrective deformation where simple weighting fails
- foot planting and hand/rifle contact evidence

### 4. Motion / face

Prove actual animation quality, not merely that clips/channels exist:

- idle
- walk/run or locomotion proving clip
- aim / weapon hold
- blink / eye aim
- jaw / facial motion
- contact / foot-slide / clipping checks

### 5. LOD0–LOD3

The current attribute-aware LOD work is still experimental. Build real Sentinel LODs preserving:

- silhouette
- UV/material boundaries
- rig weights
- morph state where required
- armor/weapon readability
- acceptable transition behavior

### 6. Finish engine triangle

Godot has real evidence. Three.js and Unreal still need equivalent real import/render/runtime receipts before the machine can claim multi-engine production delivery.

## Quality rule for the next chat

Do not reward:

- more triangles by itself
- different pixels by itself
- a green structural test by itself
- beauty lighting that hides defects

Reward:

- stronger in-engine silhouette
- believable material response
- coherent manufactured construction
- good fit between skin / cloth / armor / weapon
- deformation and contact that survive motion
- reproducible canonical source state

The target is **capability parity with high-quality shipped game-character pipelines while producing original designs**.

## Run 2 stop condition

Run 2 is complete when this handoff is committed, the exact handoff head is green, and PR #3 is merged to `main`.

The next chat should start fresh from `main` and open one new PR lane for the armor → weapon/contact → rig/deformation sequence.