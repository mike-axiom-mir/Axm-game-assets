#!/usr/bin/env python3
"""AXM Game Asset Forge native deterministic PBR micro-surface generator v0.1."""
from __future__ import annotations

import hashlib
import json
import math
import random
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PaintedMetalSpec:
    paint_rgb: tuple[int, int, int] = (54, 67, 73)
    metal_rgb: tuple[int, int, int] = (112, 118, 121)
    paint_roughness: float = 0.48
    metal_roughness: float = 0.27
    wear: float = 0.32
    scratches: int = 18
    grain_scale: float = 28.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(value * 255.0))))


def _hash2(x: int, y: int, seed: int) -> float:
    n = (x * 0x1F123BB5) ^ (y * 0x5F356495) ^ (seed * 0x6C8E9CF5)
    n ^= n >> 15
    n = (n * 0x2C1B3C6D) & 0xFFFFFFFF
    n ^= n >> 12
    n = (n * 0x297A2D39) & 0xFFFFFFFF
    n ^= n >> 15
    return n / 0xFFFFFFFF


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def value_noise(x: float, y: float, seed: int) -> float:
    xi, yi = math.floor(x), math.floor(y)
    tx, ty = _smoothstep(x - xi), _smoothstep(y - yi)
    a = _hash2(xi, yi, seed)
    b = _hash2(xi + 1, yi, seed)
    c = _hash2(xi, yi + 1, seed)
    d = _hash2(xi + 1, yi + 1, seed)
    top = a + (b - a) * tx
    bottom = c + (d - c) * tx
    return top + (bottom - top) * ty


def fbm(x: float, y: float, seed: int, octaves: int = 5) -> float:
    total = 0.0
    amplitude = 0.5
    frequency = 1.0
    norm = 0.0
    for octave in range(octaves):
        total += value_noise(x * frequency, y * frequency, seed + octave * 1013) * amplitude
        norm += amplitude
        frequency *= 2.03
        amplitude *= 0.5
    return total / norm if norm else 0.0


def _distance_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def _scratch_segments(seed: int, count: int) -> list[tuple[float, float, float, float, float]]:
    rng = random.Random(seed ^ 0xA51E7)
    segments = []
    for _ in range(count):
        ax, ay = rng.random(), rng.random()
        angle = rng.uniform(-math.pi, math.pi)
        length = rng.uniform(0.035, 0.24)
        bx = ax + math.cos(angle) * length
        by = ay + math.sin(angle) * length
        width = rng.uniform(0.0008, 0.0045)
        segments.append((ax, ay, bx, by, width))
    return segments


def painted_metal_fields(size: int, seed: int, spec: PaintedMetalSpec = PaintedMetalSpec()) -> dict[str, object]:
    if size < 8:
        raise ValueError("size must be >= 8")
    scratches = _scratch_segments(seed, max(0, spec.scratches))
    height = [0.0] * (size * size)
    wear = [0.0] * (size * size)

    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            grain = fbm(u * spec.grain_scale, v * spec.grain_scale, seed)
            broad = fbm(u * 5.2, v * 5.2, seed + 701)
            pits = max(0.0, (fbm(u * 54.0, v * 54.0, seed + 1907) - 0.63) * 2.2)
            scratch_mask = 0.0
            for ax, ay, bx, by, width in scratches:
                d = _distance_to_segment(u, v, ax, ay, bx, by)
                if d < width * 2.5:
                    scratch_mask = max(scratch_mask, 1.0 - d / (width * 2.5))
            chip_seed = fbm(u * 15.0, v * 15.0, seed + 2903)
            chip = _clamp01((chip_seed - (0.72 - spec.wear * 0.20)) * 6.5)
            w = _clamp01(chip * 0.82 + scratch_mask * 0.92 + pits * 0.42)
            idx = y * size + x
            wear[idx] = w
            height[idx] = _clamp01(0.54 + (grain - 0.5) * 0.11 + (broad - 0.5) * 0.05 - scratch_mask * 0.18 - pits * 0.12)

    base = bytearray()
    rough = bytearray()
    metal = bytearray()
    ao = bytearray()
    height_bytes = bytearray(_u8(v) for v in height)
    normal = bytearray()
    pr, pg, pb = spec.paint_rgb
    mr, mg, mb = spec.metal_rgb

    for y in range(size):
        for x in range(size):
            idx = y * size + x
            w = wear[idx]
            grain = fbm((x + 0.5) / size * 31.0, (y + 0.5) / size * 31.0, seed + 4201)
            shade = 0.91 + (grain - 0.5) * 0.16
            r = (pr * (1.0 - w) + mr * w) * shade
            g = (pg * (1.0 - w) + mg * w) * shade
            b = (pb * (1.0 - w) + mb * w) * shade
            base.extend((max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b)))))
            roughness = spec.paint_roughness * (1.0 - w) + spec.metal_roughness * w + (grain - 0.5) * 0.10
            rough.append(_u8(_clamp01(roughness)))
            metal.append(_u8(_clamp01(w)))
            ao.append(_u8(_clamp01(0.82 + height[idx] * 0.18)))

            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            dx = (right - left) * 4.0
            dy = (up - down) * 4.0
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal.extend((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))

    return {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(rough)),
        "metallic": (1, bytes(metal)),
        "height": (1, bytes(height_bytes)),
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
    }


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def png_bytes(width: int, height: int, channels: int, pixels: bytes) -> bytes:
    if channels not in (1, 3, 4):
        raise ValueError("channels must be 1, 3, or 4")
    if len(pixels) != width * height * channels:
        raise ValueError("pixel byte count does not match dimensions")
    color_type = {1: 0, 3: 2, 4: 6}[channels]
    stride = width * channels
    raw = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(height))
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_painted_metal(output: str | Path, *, size: int = 512, seed: int = 1, spec: PaintedMetalSpec = PaintedMetalSpec()) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fields = painted_metal_fields(size, seed, spec)
    maps: dict[str, dict[str, object]] = {}
    for name, packed in fields.items():
        channels, pixels = packed
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "sha256": _sha256(data), "channels": channels}
    manifest = {
        "schema": "axm.game-assets.native-pbr.v0.1",
        "kind": "painted_metal",
        "seed": seed,
        "size": [size, size],
        "spec": {
            "paint_rgb": list(spec.paint_rgb),
            "metal_rgb": list(spec.metal_rgb),
            "paint_roughness": spec.paint_roughness,
            "metal_roughness": spec.metal_roughness,
            "wear": spec.wear,
            "scratches": spec.scratches,
            "grain_scale": spec.grain_scale,
        },
        "maps": maps,
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "notes": [
                "PBR-style authored channels, not a measured scan.",
                "Wear history is procedural and seed-driven.",
                "Normal map is derived from the generated height field.",
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (root / "material.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256(manifest_bytes)
    return manifest
