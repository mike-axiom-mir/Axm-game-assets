# Native collision/navigation contract donor

Game Asset Forge now has an explicit coarse collision contract selectively adapted from the finished Universal Creation RTS foundry.

Pinned donor:

`mike-axiom-mir/axm-universal-creation@a5cc708457b7e8f33e794fdac648ae65d15a0fb4`

Donor mechanism:

`src/axm_uc/rts_foundry.py::collision_contract`

## Why this is separate from visual geometry

A detailed mesh is not automatically a good gameplay collider. Universal Creation's RTS foundry correctly kept collision as separate authored state: named coarse boxes, semantic roles, optional state conditions and XZ navigation footprints.

`native_collision_contract.py` ports that distinction into Game Asset Forge.

## Contract

Each `CollisionBox` has:

- `proxy_id`
- center
- size
- semantic role
- optional explicit condition

A `CollisionContract` owns one or more boxes plus the explicit `equipment_blocks_navigation` decision.

The contract derives rectangular XZ footprints from the declared proxy boxes. Those footprints are geometric evidence only; they are not a pathfinding result.

Examples of useful roles include:

- `solid`
- `vehicle-proxy`
- `unit-proxy`
- `coarse-placement-proxy`
- `gate-closed-only`
- project-specific semantic roles

The module does not hard-code role behavior. Consumers remain responsible for interpreting the contract.

## Conditional collision

A stateful proxy can carry an explicit condition such as:

`active only while gate state is closed`

That condition is preserved as data. Animation alone does not silently enable or disable collision.

## Coarse bounds helper

`coarse_contract_from_mesh` can derive one box from source mesh bounds, but the caller must explicitly supply the scale factors and the result is labelled a coarse placement proxy. This is deliberately not called production collider fitting.

## Delivery evidence

`write_collision_contract` writes create-only:

- `collision-contract.json`
- `collision-proxy.obj`
- `collision-receipt.json`

The receipt binds the exact written contract/proxy bytes and keeps physics/navigation acceptance false.

## Truth boundary

A passing contract proves:

- declared box geometry;
- role and condition state;
- derived XZ box footprints;
- exact written contract/proxy identity.

It does not prove:

- physics response;
- pathfinding behavior;
- collision fidelity against the render mesh;
- target-engine import;
- gameplay suitability;
- performance;
- automatic Genome adoption;
- CANON.

This should remain a separate evidence plane from both visual geometry and rigid node animation.
