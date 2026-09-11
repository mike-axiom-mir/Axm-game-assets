# Forge initialization HOLD inspection

`forge.py init` is create-only. If the requested output path already exists it returns:

```text
HOLD AXM_FORGE_INIT_OUTPUT_EXISTS
```

That HOLD protects existing bytes, but it does not by itself tell a human what is already there. Use the read-only inspector before deciding whether to reuse, archive, recover, or choose another path:

```bash
python forge_init_inspector.py build/sentinel
```

For a machine-readable receipt:

```bash
python forge_init_inspector.py build/sentinel --json
```

## States

- `AVAILABLE` — no filesystem entry currently occupies the path. `forge.py init` remains the final create-only admission check because another process can still claim it first.
- `ESTABLISHED_INITIALIZATION` — `genome.json` and the intake receipt are individually self-consistent, share request identity, and the current Genome is the exact output recorded by intake.
- `ESTABLISHED_FORGE_STATE` — Genome and intake are individually self-consistent and share request identity, but the current Genome has evolved beyond the intake-stage output. The inspector does not reconstruct later lineage; review the later state/receipts before acting.
- `HELD_PARTIAL_INITIALIZATION` — only one of the two initialization evidence files is present. This is compatible with an interrupted initialization but does not prove the cause.
- `HELD_AMBIGUOUS_INITIALIZATION` — Forge-looking evidence is unreadable, unsafe to inspect, or fails its read-only identity checks.
- `HELD_OCCUPIED` — a directory exists without the two expected initialization evidence files. The inspector does not assume it is disposable.
- `HELD_NOT_DIRECTORY` — a non-directory entry occupies the path.
- `HELD_SYMLINKED_OUTPUT` — the requested output itself is a symbolic link; its target is not treated as Forge authority.

## Authority boundary

The inspector is deliberately observational. It does **not** initialize, repair, delete, archive, migrate, reseal, promote, or canonize anything. It reads only the exact initialization evidence paths, rejects symlinked evidence, uses strict UTF-8 JSON with duplicate-key rejection, bounds each inspected file to 64 MiB, checks embedded Genome and receipt digests, and checks that the Genome request identity is bound into the intake receipt.

A green inspection is not authorship proof, visual approval, engine acceptance, release approval, merge approval, or CANON. If a state is held or ambiguous, preserve the bytes and choose a new output path unless a human explicitly decides how to recover or archive the old one.
