# Native found-object detail donor

Game Asset Forge now has a small semantic-detail vocabulary selectively adapted from the finished Universal Creation workshop/RTS foundry.

Pinned donor:

`mike-axiom-mir/axm-universal-creation@a5cc708457b7e8f33e794fdac648ae65d15a0fb4`

Relevant donor mechanisms:

- `tools/blender/axm_salvage_personality.py`
- `src/axm_uc/rts_detail.py`

## Why this donor matters

The workshop that exposed the gap between Universal Creation and the specialized Game Asset Forge was not detailed merely because it had more polygons. It contained small understandable objects and repair history: a kettle, mug, winch, stool, lantern, tied cargo, mismatched fixes and other lived-in construction cues.

Those details are semantic. They help a player read what a place is and how it is used.

`native_found_object_detail.py` ports a bounded set of those reusable mechanisms into Forge-owned native geometry instead of copying the workshop composition itself.

## Current recipes

- kettle
- mug
- winch with spokes and drop cable
- mismatched-leg stool with hubcap-like seat
- lantern with cage/handle plus optional practical-light metadata
- tied cargo crate with explicit rope geometry

Every recipe returns named semantic parts with material-family intent and an exact deterministic receipt.

## Practical lights

A lantern can carry a `PracticalLight` record containing position, color, energy and radius hints.

That record is metadata. It explicitly says the target engine must recreate and tune the light. It is not a baked-light or engine-light claim.

## Composition principle

The useful donor pattern is:

`large form -> construction system -> functional substructure -> small semantic objects -> repair/history detail -> materials -> evidence`

The Forge should preserve those layers separately so lower-detail realizations can decide which details to keep, bake, simplify or omit without silently changing asset meaning.

## Truth boundary

These recipes prove deterministic authored geometry for their bounded objects and explicit practical-light metadata.

They do not prove:

- good art direction;
- correct automatic placement;
- realism;
- engine lighting parity;
- gameplay interaction;
- collision behavior;
- target-engine performance;
- automatic Genome adoption;
- CANON.

A machine may use these capabilities as building blocks, but selecting and composing them remains a separate design/review problem.
