#!/usr/bin/env python3
"""Data-driven reusable form recipes for AXM Game Asset Forge.

This is the Game Asset Forge adaptation of two lessons that converged in AXM:
- MorphTile-style reusable definitions/composition are more powerful than a
  catalog of finished shapes.
- Universal Creation's generic form-pattern path showed that profiles, lofts,
  revolves and authored paths can be retained as source structure instead of
  baking every result into a one-off mesh builder.

The compiler is stdlib-only and operates on the Forge native Mesh contract.
It does not depend on MorphTile or Universal Creation at runtime.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any, Iterable, Sequence

from native_construction_kit import (
    ConstructionAssembly,
    SemanticPart,
    beam_segment,
    lathe_profile,
    pipe_path,
    rounded_box,
    torus_ring,
)
from native_geometry import Mesh, topology_report

SCHEMA = "axm.game-assets.form-recipe/v0.1"
MAX_PARTS = 256
MAX_DEFINITIONS = 64
MAX_REPEAT = 128
MAX_POINTS = 128
MAX_COMPOSITION_DEPTH = 6

DONOR_LINEAGE = [
    {
        "repository": "mike-axiom-mir/axm-morphtile",
        "mechanism": "reusable definitions and composition over retained source structure",
        "dependency": False,
    },
    {
        "repository": "mike-axiom-mir/axm-universal-creation",
        "commit": "5a6356270d0c7822576239b99c2b3ca3371cfdd7",
        "mechanism": "generic profile/loft/revolve/tube source-first form patterns",
        "dependency": False,
    },
]


class FormRecipeError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FormRecipeError("recipe must be finite JSON data") from exc


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormRecipeError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise FormRecipeError(f"{label} must be from {low} through {high}")
    return result


def _vec(value: Any, label: str, width: int = 3, low: float = -100000.0, high: float = 100000.0) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != width:
        raise FormRecipeError(f"{label} must contain exactly {width} values")
    return tuple(_number(item, f"{label}[{index}]", low, high) for index, item in enumerate(value))


def _text(value: Any, label: str, maximum: int = 120) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise FormRecipeError(f"{label} must be non-empty text up to {maximum} characters")
    return value.strip()


_PARAM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _params(raw: Any, label: str) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FormRecipeError(f"{label} must be an object")
    out: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _PARAM_RE.fullmatch(key):
            raise FormRecipeError(f"{label} contains invalid parameter name {key!r}")
        out[key] = _number(value, f"{label}.{key}", -100000.0, 100000.0)
    return out


def _resolve(value: Any, env: dict[str, float], label: str) -> Any:
    """Resolve bounded named numeric parameters without evaluating arbitrary code."""
    if isinstance(value, dict) and set(value) == {"$var"}:
        name = value["$var"]
        if not isinstance(name, str) or not _PARAM_RE.fullmatch(name):
            raise FormRecipeError(f"{label} has an invalid $var name")
        if name not in env:
            raise FormRecipeError(f"{label} references unknown parameter {name!r}")
        return env[name]
    if isinstance(value, list):
        return [_resolve(item, env, f"{label}[]") for item in value]
    if isinstance(value, tuple):
        return tuple(_resolve(item, env, f"{label}[]") for item in value)
    if isinstance(value, dict):
        return {key: _resolve(item, env, f"{label}.{key}") for key, item in value.items()}
    return deepcopy(value)


def _scale(value: Any, label: str) -> tuple[float, float, float]:
    if value is None:
        return (1.0, 1.0, 1.0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount = _number(value, label, 0.001, 10000.0)
        return amount, amount, amount
    return _vec(value, label, 3, 0.001, 10000.0)  # type: ignore[return-value]


def _rotate_point(point: tuple[float, float, float], rotation: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    rx, ry, rz = rotation
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return x, y, z


def transform_mesh(
    mesh: Mesh,
    *,
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str | None = None,
) -> Mesh:
    vertices = []
    for x, y, z in mesh.vertices:
        point = (x * scale[0], y * scale[1], z * scale[2])
        point = _rotate_point(point, rotation)
        vertices.append(
            (
                point[0] + translation[0],
                point[1] + translation[1],
                point[2] + translation[2],
            )
        )
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def profile_extrude(
    outline: Sequence[Sequence[float]],
    *,
    depth: float,
    name: str = "profile-extrude",
) -> Mesh:
    if not 3 <= len(outline) <= MAX_POINTS:
        raise FormRecipeError(f"profile outline requires 3..{MAX_POINTS} points")
    points = [_vec(row, f"outline[{index}]", 2, -10000.0, 10000.0) for index, row in enumerate(outline)]
    depth = _number(depth, "depth", 0.001, 10000.0)
    vertices = [(x, -depth * 0.5, z) for x, z in points] + [
        (x, depth * 0.5, z) for x, z in points
    ]
    count = len(points)
    faces: list[tuple[int, ...]] = [
        tuple(reversed(range(count))),
        tuple(range(count, count * 2)),
    ]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, nxt + count, index + count))
    mesh = Mesh(name, vertices, faces)
    report = topology_report(mesh)
    if not report["closed_two_manifold_candidate"]:
        raise FormRecipeError(f"profile extrusion is not a closed valid shell: {report}")
    return mesh


def loft_sections(
    sections: Sequence[dict[str, Any]],
    *,
    segments: int = 20,
    name: str = "loft",
) -> Mesh:
    if not 2 <= len(sections) <= MAX_POINTS:
        raise FormRecipeError(f"loft requires 2..{MAX_POINTS} sections")
    if type(segments) is not int or not 3 <= segments <= 128:
        raise FormRecipeError("loft segments must be an integer from 3 through 128")
    vertices: list[tuple[float, float, float]] = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise FormRecipeError(f"sections[{index}] must be an object")
        if set(section) - {"at", "radius", "offset", "twist"} or not {"at", "radius"} <= set(section):
            raise FormRecipeError(f"sections[{index}] fields are invalid")
        at = _number(section["at"], f"sections[{index}].at", -10000.0, 10000.0)
        radius = _vec(section["radius"], f"sections[{index}].radius", 2, 0.001, 10000.0)
        offset = _vec(section.get("offset", [0.0, 0.0]), f"sections[{index}].offset", 2)
        twist = _number(section.get("twist", 0.0), f"sections[{index}].twist", -100000.0, 100000.0)
        for side in range(segments):
            angle = math.tau * side / segments + twist
            vertices.append(
                (
                    offset[0] + radius[0] * math.cos(angle),
                    at,
                    offset[1] + radius[1] * math.sin(angle),
                )
            )
    faces: list[tuple[int, ...]] = []
    for level in range(len(sections) - 1):
        a, b = level * segments, (level + 1) * segments
        for side in range(segments):
            nxt = (side + 1) % segments
            faces.append((a + side, a + nxt, b + nxt, b + side))
    faces.append(tuple(reversed(range(segments))))
    last = (len(sections) - 1) * segments
    faces.append(tuple(last + side for side in range(segments)))
    mesh = Mesh(name, vertices, faces)
    report = topology_report(mesh)
    if not report["closed_two_manifold_candidate"]:
        raise FormRecipeError(f"loft is not a closed valid shell: {report}")
    return mesh


def _primitive_mesh(node: dict[str, Any], part_id: str) -> Mesh:
    pattern = str(node.get("pattern", "")).strip().casefold()
    if pattern == "profile-extrude":
        return profile_extrude(node.get("outline", []), depth=node.get("depth"), name=part_id)
    if pattern == "loft":
        return loft_sections(node.get("sections", []), segments=int(node.get("segments", 20)), name=part_id)
    if pattern == "lathe":
        return lathe_profile(
            node.get("profile", []),
            axis=str(node.get("axis", "y")),
            segments=int(node.get("segments", 18)),
            name=part_id,
        )
    if pattern == "pipe":
        return pipe_path(
            node.get("path", []),
            radius=_number(node.get("radius"), f"{part_id}.radius", 0.001, 10000.0),
            sides=int(node.get("segments", 8)),
            name=part_id,
        )
    if pattern == "beam":
        return beam_segment(
            node.get("start", [0, 0, 0]),
            node.get("end", [0, 1, 0]),
            width=_number(node.get("width"), f"{part_id}.width", 0.001, 10000.0),
            depth=None if node.get("depth") is None else _number(node.get("depth"), f"{part_id}.depth", 0.001, 10000.0),
            name=part_id,
        )
    if pattern == "ring":
        return torus_ring(
            node.get("center", [0, 0, 0]),
            radius=_number(node.get("radius"), f"{part_id}.radius", 0.001, 10000.0),
            tube=_number(node.get("tube"), f"{part_id}.tube", 0.001, 10000.0),
            axis=str(node.get("axis", "y")),
            ratio=_number(node.get("ratio", 1.0), f"{part_id}.ratio", 0.001, 10000.0),
            major_segments=int(node.get("major_segments", 20)),
            minor_segments=int(node.get("minor_segments", 6)),
            name=part_id,
        )
    if pattern == "rounded-box":
        return rounded_box(
            node.get("center", [0, 0, 0]),
            node.get("size", [1, 1, 1]),
            chamfer=_number(node.get("chamfer", 0.05), f"{part_id}.chamfer", 0.0, 10000.0),
            name=part_id,
        )
    raise FormRecipeError(
        f"unsupported form pattern {pattern!r}; expected profile-extrude, loft, lathe, pipe, beam, ring, or rounded-box"
    )


def _semantic_part(node: dict[str, Any], part_id: str, inherited: dict[str, Any] | None = None) -> SemanticPart:
    inherited = inherited or {}
    mesh = _primitive_mesh(node, part_id)
    scale = _scale(node.get("scale", inherited.get("scale")), f"{part_id}.scale")
    rotation = _vec(node.get("rotation", inherited.get("rotation", [0, 0, 0])), f"{part_id}.rotation")  # type: ignore[assignment]
    translation = _vec(node.get("translation", inherited.get("translation", [0, 0, 0])), f"{part_id}.translation")  # type: ignore[assignment]
    mesh = transform_mesh(
        mesh,
        scale=scale,
        rotation=rotation,  # type: ignore[arg-type]
        translation=translation,  # type: ignore[arg-type]
        name=part_id,
    )
    report = topology_report(mesh)
    if not report["closed_two_manifold_candidate"]:
        raise FormRecipeError(f"part {part_id!r} is not a closed valid shell: {report}")
    material = _text(node.get("material_family", inherited.get("material_family", "unassigned")), f"{part_id}.material_family", 120)
    role = _text(node.get("semantic_role", inherited.get("semantic_role", part_id)), f"{part_id}.semantic_role", 160)
    return SemanticPart(part_id, mesh, material, role)


def _compose_settings(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Compose nested definition/use transforms instead of silently replacing them."""
    out = deepcopy(base)
    if "translation" in overlay:
        left = _vec(out.get("translation", [0, 0, 0]), "composed.translation.base")
        right = _vec(overlay["translation"], "composed.translation.overlay")
        out["translation"] = [left[i] + right[i] for i in range(3)]
    if "rotation" in overlay:
        left = _vec(out.get("rotation", [0, 0, 0]), "composed.rotation.base")
        right = _vec(overlay["rotation"], "composed.rotation.overlay")
        out["rotation"] = [left[i] + right[i] for i in range(3)]
    if "scale" in overlay:
        left = _scale(out.get("scale"), "composed.scale.base")
        right = _scale(overlay["scale"], "composed.scale.overlay")
        out["scale"] = [left[i] * right[i] for i in range(3)]
    for key, value in overlay.items():
        if key not in {"translation", "rotation", "scale"}:
            out[key] = deepcopy(value)
    return out


def compile_form_recipe(raw: Any) -> ConstructionAssembly:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise FormRecipeError(f"recipe must use schema {SCHEMA}")
    if set(raw) - {"schema", "name", "vars", "definitions", "parts", "metadata"}:
        raise FormRecipeError("recipe contains unsupported top-level fields")
    name = _text(raw.get("name"), "recipe.name")
    root_vars = _params(raw.get("vars"), "recipe.vars")
    definitions = raw.get("definitions", {})
    if not isinstance(definitions, dict) or len(definitions) > MAX_DEFINITIONS:
        raise FormRecipeError(f"definitions must be an object with at most {MAX_DEFINITIONS} entries")
    for definition_name, body in definitions.items():
        _text(definition_name, "definition name", 80)
        if not isinstance(body, dict) or set(body) - {"parts", "defaults", "params"} or "parts" not in body:
            raise FormRecipeError(
                f"definition {definition_name!r} requires parts and optional defaults/params"
            )
        if not isinstance(body["parts"], list) or not body["parts"]:
            raise FormRecipeError(f"definition {definition_name!r}.parts must be non-empty")
        if "defaults" in body and not isinstance(body["defaults"], dict):
            raise FormRecipeError(f"definition {definition_name!r}.defaults must be an object")
        _params(body.get("params"), f"definition {definition_name}.params")

    root_parts = raw.get("parts")
    if not isinstance(root_parts, list) or not root_parts:
        raise FormRecipeError("recipe.parts must be a non-empty list")

    parts: list[SemanticPart] = []
    source_index: list[dict[str, Any]] = []
    generated_id = 0

    def emit(
        nodes: Iterable[Any],
        *,
        prefix: str,
        inherited: dict[str, Any],
        env: dict[str, float],
        stack: tuple[str, ...],
        depth: int,
    ) -> None:
        nonlocal generated_id
        if depth > MAX_COMPOSITION_DEPTH:
            raise FormRecipeError(f"composition exceeds depth {MAX_COMPOSITION_DEPTH}")
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                raise FormRecipeError("every recipe node must be an object")
            if "repeat" in raw_node:
                if set(raw_node) - {"repeat", "step", "body", "as"} or "body" not in raw_node:
                    raise FormRecipeError("repeat node accepts repeat, step, body and optional as")
                raw_count = _resolve(raw_node["repeat"], env, "repeat")
                if (
                    isinstance(raw_count, bool)
                    or not isinstance(raw_count, (int, float))
                    or not float(raw_count).is_integer()
                    or not 0 <= int(raw_count) <= MAX_REPEAT
                ):
                    raise FormRecipeError(
                        f"repeat must resolve to an integer from 0 through {MAX_REPEAT}"
                    )
                count = int(raw_count)
                step = _vec(
                    _resolve(raw_node.get("step", [0, 0, 0]), env, "repeat.step"),
                    "repeat.step",
                )
                body = raw_node["body"]
                if not isinstance(body, list):
                    raise FormRecipeError("repeat.body must be a list")
                loop_name = raw_node.get("as", "i")
                if not isinstance(loop_name, str) or not _PARAM_RE.fullmatch(loop_name):
                    raise FormRecipeError("repeat.as must be a portable parameter name")
                for index in range(count):
                    shifted = _compose_settings(
                        inherited,
                        {"translation": [step[0] * index, step[1] * index, step[2] * index]},
                    )
                    inner_env = dict(env)
                    inner_env[loop_name] = float(index)
                    inner_env[f"{loop_name}_of"] = float(count)
                    inner_env[f"{loop_name}_at"] = (
                        index / (count - 1) if count > 1 else 0.0
                    )
                    emit(
                        body,
                        prefix=f"{prefix}r{index}-",
                        inherited=shifted,
                        env=inner_env,
                        stack=stack,
                        depth=depth + 1,
                    )
                continue
            if "use" in raw_node:
                allowed = {
                    "use", "id_prefix", "with", "translation", "rotation", "scale",
                    "material_family", "semantic_role"
                }
                if set(raw_node) - allowed:
                    raise FormRecipeError("use node contains unsupported fields")
                definition_name = _text(raw_node["use"], "use", 80)
                if definition_name not in definitions:
                    raise FormRecipeError(f"unknown definition {definition_name!r}")
                if definition_name in stack:
                    raise FormRecipeError(
                        f"definition cycle: {' -> '.join(stack + (definition_name,))}"
                    )
                definition = definitions[definition_name]
                child_env = _params(
                    definition.get("params"), f"definition {definition_name}.params"
                )
                overrides = raw_node.get("with", {})
                if not isinstance(overrides, dict):
                    raise FormRecipeError("use.with must be an object")
                unknown = sorted(set(overrides) - set(child_env))
                if unknown:
                    raise FormRecipeError(
                        f"use of {definition_name!r} overrides undeclared parameters {unknown}"
                    )
                for key, value in overrides.items():
                    resolved = _resolve(value, env, f"use.with.{key}")
                    child_env[key] = _number(
                        resolved, f"use.with.{key}", -100000.0, 100000.0
                    )

                combined_env = {**env, **child_env}
                defaults = _resolve(
                    definition.get("defaults", {}),
                    combined_env,
                    f"definition {definition_name}.defaults",
                )
                if not isinstance(defaults, dict):
                    raise FormRecipeError(
                        f"definition {definition_name!r}.defaults must resolve to an object"
                    )
                child = _compose_settings(inherited, defaults)
                use_settings: dict[str, Any] = {}
                for key in (
                    "translation", "rotation", "scale", "material_family", "semantic_role"
                ):
                    if key in raw_node:
                        use_settings[key] = _resolve(
                            raw_node[key], combined_env, f"use.{key}"
                        )
                child = _compose_settings(child, use_settings)
                id_prefix = str(raw_node.get("id_prefix", definition_name + "-"))
                emit(
                    definition["parts"],
                    prefix=prefix + id_prefix,
                    inherited=child,
                    env=combined_env,
                    stack=stack + (definition_name,),
                    depth=depth + 1,
                )
                continue

            generated_id += 1
            if generated_id > MAX_PARTS:
                raise FormRecipeError(f"recipe exceeds {MAX_PARTS} generated parts")
            resolved_node = _resolve(raw_node, env, "part")
            if not isinstance(resolved_node, dict):
                raise FormRecipeError("resolved part must remain an object")
            requested_id = resolved_node.get("id")
            part_id = (
                _text(requested_id, "part.id", 80)
                if requested_id is not None
                else f"part-{generated_id:03d}"
            )
            part_id = prefix + part_id
            if any(existing.part_id == part_id for existing in parts):
                raise FormRecipeError(f"duplicate generated part id {part_id!r}")
            part = _semantic_part(resolved_node, part_id, inherited)
            parts.append(part)
            source_index.append(
                {
                    "part_id": part_id,
                    "pattern": resolved_node.get("pattern"),
                    "material_family": part.material_family,
                    "semantic_role": part.semantic_role,
                    "source_fragment_sha256": "sha256:"
                    + hashlib.sha256(_canonical(raw_node)).hexdigest(),
                    "resolved_fragment_sha256": "sha256:"
                    + hashlib.sha256(_canonical(resolved_node)).hexdigest(),
                    "topology": topology_report(part.mesh),
                }
            )

    emit(
        root_parts,
        prefix="",
        inherited={},
        env=root_vars,
        stack=(),
        depth=0,
    )
    if not parts:
        raise FormRecipeError("recipe generated no parts")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "name": name,
        "recipe_sha256": "sha256:" + hashlib.sha256(_canonical(raw)).hexdigest(),
        "source_authority": True,
        "realization_is_secondary": True,
        "parts": source_index,
        "part_count": len(parts),
        "definitions_declared": len(definitions),
        "parameterized_definitions": sum(bool(body.get("params")) for body in definitions.values()),
        "root_vars": deepcopy(root_vars),
        "metadata": deepcopy(raw.get("metadata", {})),
        "provenance": {
            "implementation": "AXM Game Asset Forge native form recipe compiler",
            "donor_lineage": deepcopy(DONOR_LINEAGE),
        },
        "truth_boundary": {
            "source_recipe_retained": True,
            "closed_mesh_topology_checked": True,
            "arbitrary_sculpting_proven": False,
            "arbitrary_boolean_csg_proven": False,
            "retopology_proven": False,
            "uv_or_material_binding_proven": False,
            "rigging_or_animation_proven": False,
            "aesthetic_quality_proven": False,
            "automatic_genome_mutation": False,
            "automatic_vault_admission": False,
            "automatic_canon": False,
        },
    }
    receipt["receipt_digest"] = "sha256:" + hashlib.sha256(_canonical(receipt)).hexdigest()
    return ConstructionAssembly(name, tuple(parts), receipt)


def form_recipe_summary() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "patterns": [
            "profile-extrude",
            "loft",
            "lathe",
            "pipe",
            "beam",
            "ring",
            "rounded-box",
        ],
        "reusable_definitions": True,
        "named_numeric_parameters": True,
        "per_use_parameter_overrides": True,
        "bounded_repeat": True,
        "loop_variables": True,
        "per_use_transform": True,
        "nested_transform_composition": True,
        "source_authority": True,
        "runtime_dependencies": [],
        "truth": (
            "The recipe can compose new inspectable forms from profiles, paths, "
            "definitions and repetitions. It is not an unrestricted sculptor, "
            "retopology system, or aesthetic judge."
        ),
    }
