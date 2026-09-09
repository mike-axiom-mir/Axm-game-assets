#!/usr/bin/env python3
"""Dependency-free diagnostic mesh rasterizer for AXM Game Asset Forge."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

from native_geometry import Mesh, face_normal, triangulate
from native_pbr import png_bytes


@dataclass(frozen=True, slots=True)
class ViewSpec:
    name: str
    u_axis: int
    v_axis: int
    depth_axis: int
    depth_sign: float


VIEWS = {
    "front": ViewSpec("front", 0, 1, 2, 1.0),
    "side": ViewSpec("side", 2, 1, 0, 1.0),
    "top": ViewSpec("top", 0, 2, 1, 1.0),
}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _edge(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    return (px - ax) * (by - ay) - (py - ay) * (bx - ax)


def render(mesh: Mesh, *, view: str = "front", size: int = 128, margin: float = 0.06) -> dict[str, object]:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view}")
    if size < 16:
        raise ValueError("preview size must be >=16")
    spec = VIEWS[view]
    tri = triangulate(mesh)
    if not tri.vertices or not tri.faces:
        raise ValueError("preview needs triangle geometry")

    projected = [(vertex[spec.u_axis], vertex[spec.v_axis], vertex[spec.depth_axis] * spec.depth_sign) for vertex in tri.vertices]
    us = [value[0] for value in projected]
    vs = [value[1] for value in projected]
    ds = [value[2] for value in projected]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    min_d, max_d = min(ds), max(ds)
    span_u = max(max_u - min_u, 1e-9)
    span_v = max(max_v - min_v, 1e-9)
    span_d = max(max_d - min_d, 1e-9)
    pad = size * margin
    frame_span = size - 1 - 2.0 * pad
    scale = frame_span / max(span_u, span_v)
    content_width = span_u * scale
    content_height = span_v * scale
    origin_x = (size - 1 - content_width) * 0.5
    origin_y = (size - 1 - content_height) * 0.5

    screen = [
        (
            origin_x + (u - min_u) * scale,
            size - 1 - (origin_y + (v - min_v) * scale),
            depth,
        )
        for u, v, depth in projected
    ]
    depth_buffer = [float("-inf")] * (size * size)
    silhouette = bytearray(size * size)
    normal_pixels = bytearray(size * size * 3)

    for face in tri.faces:
        a, b, c = face
        ax, ay, ad = screen[a]
        bx, by, bd = screen[b]
        cx, cy, cd = screen[c]
        area = _edge(ax, ay, bx, by, cx, cy)
        if abs(area) <= 1e-10:
            continue
        lo_x = max(0, int(min(ax, bx, cx)))
        hi_x = min(size - 1, int(max(ax, bx, cx)) + 1)
        lo_y = max(0, int(min(ay, by, cy)))
        hi_y = min(size - 1, int(max(ay, by, cy)) + 1)
        normal = face_normal(tri, face)
        normal_rgb = tuple(max(0, min(255, round((component * 0.5 + 0.5) * 255.0))) for component in normal)
        for py in range(lo_y, hi_y + 1):
            y = py + 0.5
            for px in range(lo_x, hi_x + 1):
                x = px + 0.5
                w0 = _edge(bx, by, cx, cy, x, y) / area
                w1 = _edge(cx, cy, ax, ay, x, y) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-8 or w1 < -1e-8 or w2 < -1e-8:
                    continue
                depth = ad * w0 + bd * w1 + cd * w2
                index = py * size + px
                if depth <= depth_buffer[index]:
                    continue
                depth_buffer[index] = depth
                silhouette[index] = 255
                base = index * 3
                normal_pixels[base:base + 3] = bytes(normal_rgb)

    depth_pixels = bytearray(size * size)
    covered = 0
    left = top = size
    right = bottom = -1
    for index, depth in enumerate(depth_buffer):
        if depth == float("-inf"):
            continue
        covered += 1
        x, y = index % size, index // size
        left, right = min(left, x), max(right, x)
        top, bottom = min(top, y), max(bottom, y)
        depth_pixels[index] = max(0, min(255, round((depth - min_d) / span_d * 255.0)))

    content_bounds = None
    if covered:
        content_bounds = {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": right - left + 1,
            "height": bottom - top + 1,
        }

    silhouette_png = png_bytes(size, size, 1, bytes(silhouette))
    depth_png = png_bytes(size, size, 1, bytes(depth_pixels))
    normal_png = png_bytes(size, size, 3, bytes(normal_pixels))
    return {
        "view": view,
        "size": [size, size],
        "covered_pixels": covered,
        "coverage": covered / (size * size),
        "projection": {
            "type": "orthographic",
            "fit": "contain",
            "aspect_preserved": True,
            "world_span": [span_u, span_v, span_d],
            "pixels_per_world_unit": scale,
            "content_bounds_px": content_bounds,
        },
        "silhouette_png": silhouette_png,
        "depth_png": depth_png,
        "normal_png": normal_png,
        "hashes": {
            "silhouette": _sha256(silhouette_png),
            "depth": _sha256(depth_png),
            "normal": _sha256(normal_png),
        },
    }


def _review_board_html(report: dict[str, object]) -> str:
    cards = []
    for view in report["views"]:
        projection = view["projection"]
        bounds = projection["content_bounds_px"]
        span = projection["world_span"]
        bounds_label = f'{bounds["width"]} × {bounds["height"]} px' if bounds else "no covered pixels"
        for signal in ("silhouette", "depth", "normal"):
            label = f"{view['view'].title()} {signal.title()}"
            filename = f"{view['view']}-{signal}.png"
            cards.append(
                f'<article class="frame" data-signal="{signal}" data-view="{view["view"]}">'
                f'<h2><span>{view["view"]}</span>{signal}</h2>'
                f'<button type="button" class="inspect" aria-pressed="false" aria-label="Inspect {label}">'
                f'<img src="{filename}" alt="{label} diagnostic" width="{view["size"][0]}" '
                f'height="{view["size"][1]}" loading="lazy"></button>'
                '<dl>'
                f'<div><dt>Coverage</dt><dd>{view["coverage"]:.1%}</dd></div>'
                f'<div><dt>Bounds</dt><dd>{bounds_label}</dd></div>'
                f'<div><dt>World span</dt><dd>{span[0]:.3g} × {span[1]:.3g}</dd></div>'
                '</dl>'
                f'<a href="{filename}" target="_blank">Open original PNG</a>'
                '</article>'
            )
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__MESH__ · Diagnostic Review Board</title>
<style>
:root{color-scheme:dark;--bg:#071014;--panel:#0c1b21;--raised:#132a31;--line:#41616a;--text:#eff9f8;--muted:#9bb1b5;--signal:#76e4d5;--focus:#ffe990}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% 0,#19353d 0,#071014 50%);color:var(--text);font-family:system-ui,sans-serif}header,main,footer{width:min(1180px,calc(100% - 32px));margin:auto}header{padding:28px 0 18px}h1{margin:4px 0 8px;font-size:clamp(1.7rem,4vw,3rem);overflow-wrap:anywhere}.eyebrow,dt{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.11em}.boundary{max-width:75ch;color:var(--muted);line-height:1.5}.summary{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.summary span{border:1px solid var(--line);border-radius:999px;padding:6px 10px;color:var(--signal);font-size:.82rem}.controls{display:flex;gap:7px;flex-wrap:wrap;padding:12px 0 18px}button{font:inherit}.filter{border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--text);padding:9px 13px;cursor:pointer}.filter[aria-pressed="true"]{background:var(--signal);border-color:var(--signal);color:#03100f;font-weight:700}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.frame{min-width:0;padding:12px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,var(--panel),#091419)}.frame[data-selected="true"]{grid-column:1/-1;border-color:var(--signal);box-shadow:0 0 0 1px var(--signal)}.frame h2{display:flex;justify-content:space-between;margin:0 0 9px;font-size:.92rem;text-transform:capitalize}.frame h2 span{color:var(--signal)}.inspect{display:block;width:100%;border:0;padding:0;background:#020608;cursor:zoom-in}.inspect[aria-pressed="true"]{cursor:zoom-out}.inspect img{display:block;width:100%;height:auto;max-height:360px;object-fit:contain;image-rendering:pixelated}.frame[data-selected="true"] .inspect img{max-height:min(68vh,720px)}dl{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0}dl div{min-width:0}dd{margin:3px 0 0;font-size:.78rem;overflow-wrap:anywhere}.frame a,footer a{color:var(--signal);font-size:.82rem}button:focus-visible,a:focus-visible{outline:3px solid var(--focus);outline-offset:3px}.frame[hidden]{display:none}footer{padding:24px 0 36px;color:var(--muted);font-size:.82rem}@media(max-width:760px){header,main,footer{width:min(100% - 22px,1180px)}header{padding-top:18px}.grid{grid-template-columns:1fr}.frame[data-selected="true"]{grid-column:auto}.controls{margin-inline:-11px;padding-inline:11px}.inspect img{max-height:none}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
</style></head><body>
<header><div class="eyebrow">AXM Game Asset Forge · review surface</div><h1>__MESH__</h1><p class="boundary">Aspect-preserving orthographic software diagnostics. These frames expose silhouette, depth, and face-normal signals; they are not engine renders, aesthetic approval, or CANON.</p><div class="summary"><span>__VIEW_COUNT__ views</span><span>__FRAME_COUNT__ frames</span><span>__SIZE__ px source</span><span>contain fit</span></div></header>
<main><nav class="controls" aria-label="Diagnostic signal filter"><button type="button" class="filter" data-filter="all" aria-pressed="true">All · __FRAME_COUNT__</button><button type="button" class="filter" data-filter="silhouette" aria-pressed="false">Silhouette</button><button type="button" class="filter" data-filter="depth" aria-pressed="false">Depth</button><button type="button" class="filter" data-filter="normal" aria-pressed="false">Normals</button></nav><section class="grid" aria-label="Diagnostic frames">__CARDS__</section><p id="announcer" class="eyebrow" aria-live="polite">Showing all __FRAME_COUNT__ diagnostic frames.</p></main>
<footer>Exact frame hashes and projection metrics: <a href="preview-report.json">preview-report.json</a>. Select a frame to enlarge it; use Arrow keys, Home, or End to move across visible frames.</footer>
<script>
const filters=[...document.querySelectorAll('.filter')],frames=[...document.querySelectorAll('.frame')],announcer=document.querySelector('#announcer');
function visibleFrames(){return frames.filter(frame=>!frame.hidden)}
function show(signal){filters.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.filter===signal)));frames.forEach(frame=>{frame.hidden=signal!=='all'&&frame.dataset.signal!==signal;frame.dataset.selected='false';frame.querySelector('.inspect').setAttribute('aria-pressed','false')});const count=visibleFrames().length;announcer.textContent=`Showing ${count} ${signal==='all'?'diagnostic':signal} frame${count===1?'':'s'}.`}
filters.forEach(button=>button.addEventListener('click',()=>show(button.dataset.filter)));
frames.forEach(frame=>{const inspect=frame.querySelector('.inspect');inspect.addEventListener('click',()=>{const selected=frame.dataset.selected!=='true';frames.forEach(item=>{item.dataset.selected='false';item.querySelector('.inspect').setAttribute('aria-pressed','false')});frame.dataset.selected=String(selected);inspect.setAttribute('aria-pressed',String(selected));if(selected)announcer.textContent=`Inspecting ${frame.dataset.view} ${frame.dataset.signal}.`});inspect.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const visible=visibleFrames(),index=visible.indexOf(frame),next=event.key==='Home'?0:event.key==='End'?visible.length-1:(index+(event.key==='ArrowRight'?1:-1)+visible.length)%visible.length;visible[next].querySelector('.inspect').focus()})});
</script></body></html>
"""
    first_view = report["views"][0]
    return (template.replace("__MESH__", escape(str(report["mesh"])))
            .replace("__VIEW_COUNT__", str(len(report["views"])))
            .replace("__FRAME_COUNT__", str(len(cards)))
            .replace("__SIZE__", str(first_view["size"][0]))
            .replace("__CARDS__", "".join(cards)))


def write_preview(mesh: Mesh, output: str | Path, *, size: int = 128, views=("front", "side", "top")) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    reports = []
    for view in views:
        result = render(mesh, view=view, size=size)
        for kind in ("silhouette", "depth", "normal"):
            (root / f"{view}-{kind}.png").write_bytes(result.pop(f"{kind}_png"))
        reports.append(result)
    report = {
        "mesh": mesh.name,
        "views": reports,
        "truth": "Aspect-preserving orthographic diagnostic software rasterizer only; not an in-engine acceptance render.",
        "review": {
            "html": "review.html",
            "report": "preview-report.json",
            "authority": "presentation_only_no_automatic_acceptance",
        },
    }
    (root / "preview-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "review.html").write_text(_review_board_html(report), encoding="utf-8")
    return report
