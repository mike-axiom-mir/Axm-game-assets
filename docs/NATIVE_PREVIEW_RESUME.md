# Crash-resumable native preview evidence v0.1

`native_preview_resumable.py` adapts FrameState's checkpoint/resume discipline to Game Asset Forge's native diagnostic preview path.

The problem it solves is simple: once preview/evidence jobs become larger, interruption must not force the machine either to restart everything or to trust half-written output.

## Admission model

A preview view is trusted for resume only after all three of its diagnostic artifacts have been written and checkpoint-admitted:

- silhouette PNG;
- depth PNG;
- face-normal PNG.

The checkpoint binds:

- exact mesh digest;
- mesh name;
- preview size;
- ordered view list;
- exact admitted PNG SHA-256 and byte counts;
- per-view deterministic preview report state.

On resume, every admitted file is re-hashed before work continues.

If a file exists for a view after the last admitted checkpoint, it is treated as an **unadmitted crash tail**, removed, and regenerated. It is never promoted merely because bytes happen to exist.

## Example API

```python
from native_preview_resumable import render_preview_resumable

# Do at most one new view this run.
result = render_preview_resumable(
    mesh,
    "build/resumable-preview",
    size=128,
    max_new_views=1,
)

# Later, continue from the admitted checkpoint.
result = render_preview_resumable(
    mesh,
    "build/resumable-preview",
    size=128,
)
```

A completed call assembles the ordinary native `preview-report.json` and `review.html`, then builds and verifies the same caller-pinned evidence manifest used by `native_preview_evidence.py`.

Calling the completed job again re-verifies its evidence; it does not rerender completed views.

## Deterministic parity proof

The integration test pauses after one view, injects an unadmitted tail artifact, resumes, and then compares every one of the eleven default evidence files against a clean one-shot `write_verified_preview(...)` run.

The required result is byte identity, not merely visual similarity.

The test also proves that:

- tampering with a checkpoint-admitted PNG blocks resume;
- changing mesh identity blocks resume;
- changing preview size blocks resume;
- changing checkpoint JSON without recomputing its digest blocks resume;
- a zero-work budget creates a legitimate paused checkpoint without claiming completed work.

## Truth boundary

This checkpoint mechanism proves continuity of deterministic diagnostic work. It does not prove visual quality, engine parity, gameplay readability, release readiness, merge authority, or CANON.

It currently applies to the lightweight native diagnostic preview renderer. It is a proving ground for resumable evidence semantics, **not yet a claim that Blender, Godot, Three.js, or all long asset jobs are resumable**.

## Provenance

The admission/checkpoint idea is adapted from:

`mike-axiom-mir/axm-framestate/src/axm_framestate/resumable.py`

The implementation is Game Asset Forge native Python and does not import FrameState at runtime.
