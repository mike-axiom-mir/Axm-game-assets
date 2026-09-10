#!/usr/bin/env python3
"""Build a local Three.js review stage for one verified rigid GLB delivery.

The stage is a downstream realization only. It validates the exact GLB delivery
receipt, copies a caller-pinned local Three.js runtime with its license, and
creates an offline browser surface. It never mutates Game Asset Genome/source
state and never grants visual approval, runtime adoption, merge, or CANON.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any

from native_glb_delivery import (
    DELIVERY_SCHEMA,
    READY_STATE,
    GlbDeliveryError,
    validate_glb_delivery,
)

REVIEW_SCHEMA = "axm.game-assets.threejs-glb-review-stage/v0.1"
EXPECTED_FALSE_AUTHORITY = {
    "canonical_genome_mutation": False,
    "source_package_mutation": False,
    "automatic_consumer_install": False,
    "automatic_runtime_adoption": False,
    "visual_approval": False,
    "merge": False,
    "canon": False,
}


class ThreeJsReviewError(ValueError):
    """Raised when a verified GLB cannot enter the bounded review stage."""


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _strict_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ThreeJsReviewError(f"{label} must be a regular file")

    def reject_duplicates(pairs):
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ThreeJsReviewError(f"{label} contains duplicate key {key!r}")
            out[key] = value
        return out

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ThreeJsReviewError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ThreeJsReviewError(f"{label} must contain one JSON object")
    return value


def _require_regular(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ThreeJsReviewError(f"{label} must be a regular file")
    return path.read_bytes()


def _validate_delivery(glb_path: Path, receipt_path: Path) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    glb = _require_regular(glb_path, label="GLB")
    receipt = _strict_json(receipt_path, label="delivery receipt")
    try:
        validation = validate_glb_delivery(glb)
    except GlbDeliveryError as exc:
        raise ThreeJsReviewError(f"GLB structural validation failed: {exc}") from exc

    if receipt.get("schema") != DELIVERY_SCHEMA or receipt.get("status") != READY_STATE:
        raise ThreeJsReviewError("delivery receipt is not a READY verified GLB delivery")
    asset = receipt.get("asset")
    delivery = receipt.get("delivery")
    authority = receipt.get("authority")
    truth = receipt.get("truth")
    if not isinstance(asset, dict) or not isinstance(asset.get("name"), str) or not asset["name"].strip():
        raise ThreeJsReviewError("delivery receipt has no asset identity")
    if not isinstance(delivery, dict):
        raise ThreeJsReviewError("delivery receipt has no delivery evidence")
    if delivery.get("format") != "glb" or delivery.get("self_contained") is not True:
        raise ThreeJsReviewError("delivery receipt does not describe one self-contained GLB")
    if delivery.get("sha256") != _sha256_bytes(glb):
        raise ThreeJsReviewError("delivery receipt GLB digest does not match supplied bytes")
    if delivery.get("bytes") != len(glb):
        raise ThreeJsReviewError("delivery receipt byte count does not match supplied GLB")
    if delivery.get("validation") != validation:
        raise ThreeJsReviewError("delivery receipt validation does not match current GLB structure")
    if authority != EXPECTED_FALSE_AUTHORITY:
        raise ThreeJsReviewError("delivery authority widened before engine review")
    if not isinstance(truth, dict) or truth.get("rigid_snapshot_only") is not True or truth.get("skeleton_or_animation_claim") is not False:
        raise ThreeJsReviewError("delivery truth boundary is incompatible with rigid engine review")
    return glb, receipt, validation


def _validate_three_root(three_root: Path, expected_version: str) -> tuple[dict[str, Path], dict[str, str]]:
    package = _strict_json(three_root / "package.json", label="Three.js package.json")
    if package.get("name") != "three":
        raise ThreeJsReviewError("runtime root is not the Three.js package")
    if package.get("version") != expected_version:
        raise ThreeJsReviewError(
            f"Three.js version mismatch: expected {expected_version!r}, found {package.get('version')!r}"
        )

    paths = {
        "three.module.js": three_root / "build" / "three.module.js",
        "GLTFLoader.js": three_root / "examples" / "jsm" / "loaders" / "GLTFLoader.js",
        "OrbitControls.js": three_root / "examples" / "jsm" / "controls" / "OrbitControls.js",
        "BufferGeometryUtils.js": three_root / "examples" / "jsm" / "utils" / "BufferGeometryUtils.js",
        "LICENSE": three_root / "LICENSE",
    }
    digests: dict[str, str] = {}
    for name, path in paths.items():
        digests[name] = _sha256_bytes(_require_regular(path, label=f"Three.js {name}"))
    return paths, digests


def _safe_json_for_html(value: Any) -> str:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _review_html(asset_name: str, receipt: dict[str, Any], review_receipt: dict[str, Any]) -> str:
    asset = html.escape(asset_name)
    delivery_sha = html.escape(receipt["delivery"]["sha256"])
    source_sha = html.escape(str(receipt.get("source", {}).get("manifest_sha256", "not supplied")))
    consumer = receipt.get("consumer_request") or {}
    request_sha = html.escape(str(consumer.get("sha256", "not bound")))
    version = html.escape(review_receipt["runtime"]["three_version"])
    payload = _safe_json_for_html({
        "asset": asset_name,
        "delivery": receipt,
        "review": review_receipt,
    })
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>AXM Three.js Engine Stage · {asset}</title>
<style>
:root {{
  color-scheme: dark;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --bg:#070a0f; --panel:#0d131d; --panel2:#111a27; --line:#26364b; --text:#edf4ff;
  --muted:#9fb0c5; --hot:#8ed6ff; --good:#a8f0c6; --hold:#ffd89a;
}}
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:radial-gradient(circle at 50% -20%,#16263d 0,#070a0f 48%);color:var(--text)}}
body{{min-height:100vh}}
button{{font:inherit;color:inherit}}
.shell{{min-height:100vh;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,380px);gap:14px;padding:14px}}
.stage{{position:relative;min-height:620px;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#05080d;box-shadow:0 20px 70px #0008}}
canvas{{display:block;width:100%;height:100%;min-height:620px;touch-action:none}}
.stagebar{{position:absolute;left:14px;right:14px;top:14px;display:flex;gap:8px;align-items:center;justify-content:space-between;pointer-events:none}}
.badge,.status{{background:#07101bd9;border:1px solid #324962;border-radius:999px;padding:8px 11px;backdrop-filter:blur(9px);font-size:12px;letter-spacing:.08em;text-transform:uppercase}}
.status{{color:var(--hold)}}
.status[data-state="rendered"]{{color:var(--good);border-color:#356b50}}
.side{{display:flex;flex-direction:column;gap:12px;min-width:0}}
.card{{background:linear-gradient(160deg,#111a27,#0a1019);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 14px 45px #0005}}
.kicker{{margin:0 0 7px;color:var(--hot);font-size:12px;letter-spacing:.14em;text-transform:uppercase}}
h1{{font-size:clamp(24px,4vw,36px);line-height:1.02;margin:0 0 8px}}
p{{color:var(--muted);line-height:1.5;margin:.5rem 0}}
.truth{{border-color:#62502d;background:linear-gradient(160deg,#1d180f,#0d1016)}}
.truth strong{{color:var(--hold)}}
.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}}
.metric{{background:#080e16;border:1px solid #1c2b3d;border-radius:11px;padding:10px;min-width:0}}
.metric span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}}
.metric strong{{display:block;margin-top:4px;overflow-wrap:anywhere}}
.controls{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
button{{min-height:46px;border-radius:11px;border:1px solid #38516d;background:#111d2c;cursor:pointer;padding:9px 12px}}
button:hover{{background:#17283c}}
button:focus-visible{{outline:3px solid #b8e5ff;outline-offset:2px}}
button[aria-pressed="true"]{{border-color:#77c9f4;background:#173047}}
.hash{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;overflow-wrap:anywhere;color:#c8d8eb}}
.details{{font-size:12px;border-top:1px solid var(--line);padding-top:10px;margin-top:10px}}
details summary{{cursor:pointer;color:#cfe7ff;min-height:44px;display:flex;align-items:center}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#05080d;border:1px solid #1e2b3c;border-radius:10px;padding:10px;max-height:260px;overflow:auto}}
@media(max-width:800px){{
  .shell{{grid-template-columns:1fr;padding:8px}}
  .stage{{min-height:58vh}}
  canvas{{min-height:58vh}}
  .card{{padding:13px}}
}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
@media(prefers-contrast:more){{.card,.stage,button{{border-width:2px}}}}
@media(forced-colors:active){{.badge,.status,.card,.stage,button{{forced-color-adjust:auto}}}}
</style>
<script type="importmap">
{{"imports":{{"three":"./vendor/three.module.js","three/addons/":"./vendor/addons/"}}}}
</script>
</head>
<body>
<main class="shell">
  <section class="stage" aria-label="Three.js rendered GLB inspection stage">
    <canvas id="viewport" aria-label="Interactive Three.js view of {asset}"></canvas>
    <div class="stagebar">
      <span class="badge">Three.js {version} · local modules</span>
      <span class="status" id="status" data-state="loading" role="status" aria-live="polite">Loading verified GLB…</span>
    </div>
  </section>
  <aside class="side">
    <section class="card">
      <p class="kicker">AXM Game Asset Forge · engine realization</p>
      <h1>{asset}</h1>
      <p>This surface loads the exact verified GLB through a caller-pinned local Three.js runtime. Rotate, inspect material response, and compare scale without changing source or Genome state.</p>
      <div class="metrics">
        <div class="metric"><span>Meshes</span><strong id="meshCount">—</strong></div>
        <div class="metric"><span>Triangles</span><strong id="triangleCount">—</strong></div>
        <div class="metric"><span>Bounds</span><strong id="bounds">—</strong></div>
        <div class="metric"><span>Draw calls</span><strong id="drawCalls">—</strong></div>
      </div>
    </section>
    <section class="card">
      <p class="kicker">Inspection controls</p>
      <div class="controls">
        <button id="left" type="button" aria-label="Rotate asset left">Rotate left</button>
        <button id="right" type="button" aria-label="Rotate asset right">Rotate right</button>
        <button id="wire" type="button" aria-pressed="false">Wireframe</button>
        <button id="reset" type="button">Reset view</button>
      </div>
      <p>Drag to orbit · wheel/pinch to zoom · arrow keys rotate · <strong>R</strong> resets · <strong>W</strong> toggles wireframe.</p>
    </section>
    <section class="card truth">
      <p class="kicker">Truth ceiling</p>
      <p><strong>ENGINE RENDERED ≠ VISUALLY APPROVED.</strong> This is one downstream Three.js realization of a verified rigid snapshot. It does not prove final Northpole Guard quality, animation, collision fitness, runtime adoption, merge, release, or CANON.</p>
      <p class="hash"><strong>GLB</strong><br>{delivery_sha}</p>
      <p class="hash"><strong>Source manifest</strong><br>{source_sha}</p>
      <p class="hash"><strong>RTS request</strong><br>{request_sha}</p>
      <div class="details">
        <details><summary>Show exact delivery receipt</summary><pre id="rawReceipt"></pre></details>
        <details><summary>Show engine-stage receipt</summary><pre id="rawReview"></pre></details>
      </div>
    </section>
  </aside>
</main>
<script type="application/json" id="axmPayload">{payload}</script>
<script type="module">
import * as THREE from "three";
import {{ GLTFLoader }} from "three/addons/loaders/GLTFLoader.js";
import {{ OrbitControls }} from "three/addons/controls/OrbitControls.js";

const payload = JSON.parse(document.querySelector("#axmPayload").textContent);
document.querySelector("#rawReceipt").textContent = JSON.stringify(payload.delivery, null, 2);
document.querySelector("#rawReview").textContent = JSON.stringify(payload.review, null, 2);

const canvas = document.querySelector("#viewport");
const status = document.querySelector("#status");
const renderer = new THREE.WebGLRenderer({{canvas, antialias:true, alpha:false, powerPreference:"high-performance"}});
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.setClearColor(0x05080d, 1);

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x05080d, 7, 20);
const camera = new THREE.PerspectiveCamera(44, 1, 0.01, 1000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = !matchMedia("(prefers-reduced-motion: reduce)").matches;
controls.dampingFactor = 0.07;

scene.add(new THREE.HemisphereLight(0xd9efff, 0x18202c, 2.35));
const key = new THREE.DirectionalLight(0xffffff, 3.4); key.position.set(3,5,4); scene.add(key);
const rim = new THREE.DirectionalLight(0x8fd8ff, 2.0); rim.position.set(-4,2,-3); scene.add(rim);
const grid = new THREE.GridHelper(8, 16, 0x45617e, 0x1f2d3d); grid.position.y = 0; scene.add(grid);

let root = null;
let home = null;
let wireframe = false;
function setWireframe(value) {{
  wireframe = value;
  if (root) root.traverse(o => {{
    if (!o.isMesh) return;
    const materials = Array.isArray(o.material) ? o.material : [o.material];
    for (const material of materials) if (material && "wireframe" in material) material.wireframe = value;
  }});
  document.querySelector("#wire").setAttribute("aria-pressed", String(value));
}}
function fit(model) {{
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  model.position.sub(center);
  const shifted = new THREE.Box3().setFromObject(model);
  const finalSize = shifted.getSize(new THREE.Vector3());
  const maxDim = Math.max(finalSize.x, finalSize.y, finalSize.z, 0.1);
  const distance = maxDim / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.65;
  camera.position.set(distance * 0.72, Math.max(finalSize.y * 0.45, maxDim * 0.34), distance);
  controls.target.set(0, 0, 0);
  controls.minDistance = maxDim * 0.55;
  controls.maxDistance = maxDim * 8;
  controls.update();
  home = {{position: camera.position.clone(), target: controls.target.clone(), rotation: model.rotation.y}};
  document.querySelector("#bounds").textContent = `${{finalSize.x.toFixed(2)}} × ${{finalSize.y.toFixed(2)}} × ${{finalSize.z.toFixed(2)}}`;
}}
function resetView() {{
  if (!root || !home) return;
  root.rotation.y = home.rotation;
  camera.position.copy(home.position);
  controls.target.copy(home.target);
  controls.update();
}}
function rotate(delta) {{ if (root) root.rotation.y += delta; }}

const loader = new GLTFLoader();
loader.load("./asset.glb", gltf => {{
  root = gltf.scene;
  scene.add(root);
  let meshes = 0, triangles = 0;
  root.traverse(o => {{
    if (!o.isMesh || !o.geometry) return;
    meshes++;
    const index = o.geometry.index;
    const positions = o.geometry.getAttribute("position");
    triangles += index ? Math.floor(index.count / 3) : (positions ? Math.floor(positions.count / 3) : 0);
  }});
  document.querySelector("#meshCount").textContent = String(meshes);
  document.querySelector("#triangleCount").textContent = triangles.toLocaleString();
  fit(root);
  status.textContent = "Three.js rendered · inspection only";
  status.dataset.state = "rendered";
  window.__AXM_THREE_REVIEW__ = {{
    state:"rendered", asset:payload.asset, meshes, triangles,
    deliverySha256:payload.delivery.delivery.sha256,
    threeRevision:THREE.REVISION,
    authority:payload.review.authority
  }};
}}, undefined, error => {{
  status.textContent = "HELD · Three.js could not load verified GLB";
  status.dataset.state = "held";
  window.__AXM_THREE_REVIEW__ = {{state:"held", error:String(error)}};
}});

function resize() {{
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}}
new ResizeObserver(resize).observe(canvas);
resize();

document.querySelector("#left").addEventListener("click",()=>rotate(-Math.PI/12));
document.querySelector("#right").addEventListener("click",()=>rotate(Math.PI/12));
document.querySelector("#wire").addEventListener("click",()=>setWireframe(!wireframe));
document.querySelector("#reset").addEventListener("click",resetView);
addEventListener("keydown", event => {{
  if (event.key === "ArrowLeft") {{ rotate(-Math.PI/18); event.preventDefault(); }}
  if (event.key === "ArrowRight") {{ rotate(Math.PI/18); event.preventDefault(); }}
  if (event.key.toLowerCase() === "r") resetView();
  if (event.key.toLowerCase() === "w") setWireframe(!wireframe);
}});

renderer.setAnimationLoop(()=>{{
  controls.update();
  renderer.render(scene,camera);
  document.querySelector("#drawCalls").textContent = String(renderer.info.render.calls);
}});
</script>
</body>
</html>
"""


def build_threejs_review_stage(
    *,
    glb_path: str | Path,
    delivery_receipt_path: str | Path,
    three_root: str | Path,
    expected_three_version: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    glb_path = Path(glb_path)
    receipt_path = Path(delivery_receipt_path)
    three_root = Path(three_root)
    output = Path(output_dir)
    glb, receipt, validation = _validate_delivery(glb_path, receipt_path)
    runtime_paths, runtime_digests = _validate_three_root(three_root, expected_three_version)

    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise ThreeJsReviewError("output_dir must be a directory")
    output.mkdir(parents=True, exist_ok=True)
    vendor = output / "vendor"
    vendor.mkdir(exist_ok=True)

    (output / "asset.glb").write_bytes(glb)
    shutil.copyfile(receipt_path, output / "delivery-receipt.json")
    copy_map = {
        "three.module.js": "three.module.js",
        "GLTFLoader.js": "addons/loaders/GLTFLoader.js",
        "OrbitControls.js": "addons/controls/OrbitControls.js",
        "BufferGeometryUtils.js": "addons/utils/BufferGeometryUtils.js",
        "LICENSE": "THREE-LICENSE.txt",
    }
    for source_name, dest_name in copy_map.items():
        destination = vendor / dest_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime_paths[source_name], destination)

    review_receipt = {
        "schema": REVIEW_SCHEMA,
        "status": "READY_FOR_LOCAL_ENGINE_REVIEW",
        "asset": {"name": receipt["asset"]["name"]},
        "input": {
            "delivery_schema": receipt["schema"],
            "glb_sha256": receipt["delivery"]["sha256"],
            "glb_bytes": len(glb),
            "structural_validation": validation,
            "source_manifest_sha256": receipt.get("source", {}).get("manifest_sha256"),
            "consumer_request": receipt.get("consumer_request"),
        },
        "runtime": {
            "engine": "threejs",
            "three_version": expected_three_version,
            "modules": runtime_digests,
            "license_copied": True,
            "network_required_after_stage_build": False,
        },
        "truth": {
            "verified_delivery_admitted": True,
            "engine_modules_pinned_and_copied": True,
            "browser_render_observed": False,
            "aesthetic_approval_claim": False,
            "runtime_game_adoption_claim": False,
            "performance_acceptance_claim": False,
        },
        "authority": {
            "canonical_genome_mutation": False,
            "source_package_mutation": False,
            "delivery_mutation": False,
            "automatic_runtime_adoption": False,
            "visual_approval": False,
            "merge": False,
            "canon": False,
        },
    }
    (output / "review-receipt.json").write_text(
        json.dumps(review_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "index.html").write_text(
        _review_html(receipt["asset"]["name"], receipt, review_receipt), encoding="utf-8"
    )
    return review_receipt


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build a local Three.js inspection stage for one verified rigid GLB")
    p.add_argument("--glb", required=True)
    p.add_argument("--delivery-receipt", required=True)
    p.add_argument("--three-root", required=True)
    p.add_argument("--expected-three-version", required=True)
    p.add_argument("--output-dir", required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        receipt = build_threejs_review_stage(
            glb_path=args.glb,
            delivery_receipt_path=args.delivery_receipt,
            three_root=args.three_root,
            expected_three_version=args.expected_three_version,
            output_dir=args.output_dir,
        )
    except ThreeJsReviewError as exc:
        raise SystemExit(f"Three.js review stage rejected: {exc}")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
