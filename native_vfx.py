#!/usr/bin/env python3
"""AXM deterministic socket-driven VFX burst state v0.1."""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import cos, pi, radians, sin, sqrt
from typing import Sequence

from native_attachment import Socket, socket_matrix, transform_direction
from native_geometry import Vec3
from native_skin import transform_point


@dataclass(frozen=True, slots=True)
class BurstEmitter:
    name: str
    count: int
    cone_degrees: float
    speed_min: float
    speed_max: float
    lifetime_min: float
    lifetime_max: float
    size_min: float
    size_max: float
    color_start: tuple[float, float, float, float]
    color_end: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Particle:
    origin: Vec3
    velocity: Vec3
    lifetime: float
    size: float
    color_start: tuple[float, float, float, float]
    color_end: tuple[float, float, float, float]


def _normalize(value: Vec3) -> Vec3:
    length = sqrt(sum(component * component for component in value))
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _dot(a: Vec3, b: Vec3) -> float:
    return sum(x * y for x, y in zip(a, b))


def muzzle_flash_emitter() -> BurstEmitter:
    return BurstEmitter(
        name="muzzle_flash",
        count=28,
        cone_degrees=9.0,
        speed_min=3.0,
        speed_max=9.5,
        lifetime_min=0.025,
        lifetime_max=0.085,
        size_min=0.018,
        size_max=0.065,
        color_start=(1.0, 0.82, 0.32, 1.0),
        color_end=(1.0, 0.18, 0.02, 0.0),
    )


def emit_burst(socket: Socket, emitter: BurstEmitter, *, seed: int) -> list[Particle]:
    if emitter.count < 1:
        raise ValueError("burst emitter count must be positive")
    if emitter.cone_degrees < 0.0 or emitter.cone_degrees > 180.0:
        raise ValueError("burst cone must be within [0,180]")
    if emitter.speed_min < 0.0 or emitter.speed_max < emitter.speed_min:
        raise ValueError("invalid burst speed range")
    if emitter.lifetime_min <= 0.0 or emitter.lifetime_max < emitter.lifetime_min:
        raise ValueError("invalid burst lifetime range")
    if emitter.size_min <= 0.0 or emitter.size_max < emitter.size_min:
        raise ValueError("invalid burst size range")
    rng = random.Random(seed)
    transform = socket_matrix(socket)
    origin = transform_point(transform, (0.0, 0.0, 0.0))
    cone = radians(emitter.cone_degrees)
    particles = []
    for _ in range(emitter.count):
        # Uniform-ish cone sample around socket-local +Z.
        cos_theta = 1.0 - rng.random() * (1.0 - cos(cone))
        sin_theta = sqrt(max(0.0, 1.0 - cos_theta * cos_theta))
        phi = rng.random() * 2.0 * pi
        local_direction = (sin_theta * cos(phi), sin_theta * sin(phi), cos_theta)
        direction = _normalize(transform_direction(transform, local_direction))
        speed = rng.uniform(emitter.speed_min, emitter.speed_max)
        particles.append(Particle(
            origin=origin,
            velocity=tuple(component * speed for component in direction),  # type: ignore[arg-type]
            lifetime=rng.uniform(emitter.lifetime_min, emitter.lifetime_max),
            size=rng.uniform(emitter.size_min, emitter.size_max),
            color_start=emitter.color_start,
            color_end=emitter.color_end,
        ))
    return particles


def sample_particle(particle: Particle, time: float) -> dict[str, object]:
    if time < 0.0:
        raise ValueError("particle sample time must be non-negative")
    t = min(time, particle.lifetime)
    normalized_age = min(1.0, t / particle.lifetime)
    position = tuple(particle.origin[axis] + particle.velocity[axis] * t for axis in range(3))
    color = tuple(
        particle.color_start[index] + (particle.color_end[index] - particle.color_start[index]) * normalized_age
        for index in range(4)
    )
    return {
        "position": position,
        "color": color,
        "size": particle.size,
        "normalized_age": normalized_age,
        "alive": time < particle.lifetime,
    }


def burst_evidence(socket: Socket, emitter: BurstEmitter, particles: Sequence[Particle]) -> dict[str, object]:
    if not particles:
        raise ValueError("burst evidence needs particles")
    transform = socket_matrix(socket)
    forward = _normalize(transform_direction(transform, (0.0, 0.0, 1.0)))
    direction_dots = []
    speeds = []
    lifetimes = []
    sizes = []
    for particle in particles:
        speed = sqrt(sum(value * value for value in particle.velocity))
        direction = _normalize(particle.velocity)
        direction_dots.append(_dot(direction, forward))
        speeds.append(speed)
        lifetimes.append(particle.lifetime)
        sizes.append(particle.size)
    return {
        "emitter": emitter.name,
        "particles": len(particles),
        "socket_origin": list(transform_point(transform, (0.0, 0.0, 0.0))),
        "socket_forward": list(forward),
        "min_forward_dot": min(direction_dots),
        "mean_forward_dot": sum(direction_dots) / len(direction_dots),
        "speed_range_observed": [min(speeds), max(speeds)],
        "lifetime_range_observed": [min(lifetimes), max(lifetimes)],
        "size_range_observed": [min(sizes), max(sizes)],
        "truth": "Deterministic emitter-state evidence only. Renderer sprites/meshes, lighting, smoke, exposure and gameplay timing remain separate gates.",
    }
