#!/usr/bin/env node
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const root = new URL("../test-results/threejs-glb-review/", import.meta.url);
const server = spawn("python", ["-m", "http.server", "4173", "--bind", "127.0.0.1", "--directory", root.pathname], {
  stdio: ["ignore", "pipe", "pipe"]
});

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
for (let attempt = 0; attempt < 50; attempt++) {
  try {
    const response = await fetch("http://127.0.0.1:4173/index.html");
    if (response.ok) break;
  } catch {}
  if (attempt === 49) throw new Error("local review server did not become reachable");
  await delay(100);
}

// Chromium no longer guarantees automatic software WebGL fallback in headless
// environments. Opt into its bundled SwiftShader only for this trusted local CI
// fixture so the evidence gate tests Three.js rendering rather than GPU presence.
const browser = await chromium.launch({
  headless: true,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const consoleErrors = [];
const pageErrors = [];
const externalRequests = [];
const failedResponses = [];
const requestFailures = [];
page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
page.on("pageerror", error => pageErrors.push(String(error)));
page.on("request", request => {
  const url = new URL(request.url());
  if (url.hostname !== "127.0.0.1") externalRequests.push(request.url());
});
page.on("response", response => {
  if (response.status() >= 400) failedResponses.push({ url: response.url(), status: response.status() });
});
page.on("requestfailed", request => {
  requestFailures.push({ url: request.url(), failure: request.failure() });
});

try {
  await page.goto("http://127.0.0.1:4173/index.html", { waitUntil: "domcontentloaded" });
  const webgl = await page.evaluate(() => {
    const probe = document.createElement("canvas");
    const gl = probe.getContext("webgl2") || probe.getContext("webgl");
    return { available: Boolean(gl), version: gl?.getParameter(gl.VERSION) || null };
  });
  assert.equal(webgl.available, true, `hosted Chromium has no WebGL context: ${JSON.stringify(webgl)}`);

  await page.waitForFunction(
    () => ["rendered", "held"].includes(window.__AXM_THREE_REVIEW__?.state),
    null,
    { timeout: 15000 }
  );
  const loaderWitness = await page.evaluate(() => window.__AXM_THREE_REVIEW__);
  assert.equal(
    loaderWitness?.state,
    "rendered",
    `Three.js loader did not render: ${JSON.stringify({ loaderWitness, failedResponses, requestFailures })}`
  );
  await page.waitForFunction(() => Number(document.querySelector("#drawCalls")?.textContent || 0) > 0);

  const desktop = await page.evaluate(() => {
    const witness = window.__AXM_THREE_REVIEW__;
    const buttons = [...document.querySelectorAll("button")];
    return {
      witness,
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      minButton: Math.min(...buttons.map(button => button.getBoundingClientRect().height)),
      drawCalls: Number(document.querySelector("#drawCalls").textContent),
      status: document.querySelector("#status").textContent
    };
  });
  assert.equal(desktop.witness.threeRevision, "180");
  assert.ok(desktop.witness.meshes > 0);
  assert.ok(desktop.witness.triangles > 0);
  assert.ok(desktop.drawCalls > 0);
  assert.equal(desktop.scrollWidth, desktop.viewportWidth);
  assert.ok(desktop.minButton >= 44, `desktop minimum button was ${desktop.minButton}`);
  assert.deepEqual(desktop.witness.authority, {
    canonical_genome_mutation: false,
    source_package_mutation: false,
    delivery_mutation: false,
    automatic_runtime_adoption: false,
    visual_approval: false,
    merge: false,
    canon: false
  });
  assert.match(desktop.status, /rendered/i);

  await page.locator("#wire").click();
  assert.equal(await page.locator("#wire").getAttribute("aria-pressed"), "true");
  await page.locator("#right").click();
  await page.locator("#wire").click();
  assert.equal(await page.locator("#wire").getAttribute("aria-pressed"), "false");
  await page.screenshot({ path: new URL("threejs-glb-review-desktop.png", root).pathname, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(120);
  const mobile = await page.evaluate(() => {
    const canvas = document.querySelector("#viewport").getBoundingClientRect();
    const buttons = [...document.querySelectorAll("button")];
    return {
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      canvasWidth: canvas.width,
      canvasHeight: canvas.height,
      minButton: Math.min(...buttons.map(button => button.getBoundingClientRect().height)),
      state: window.__AXM_THREE_REVIEW__?.state
    };
  });
  assert.equal(mobile.state, "rendered");
  assert.equal(mobile.scrollWidth, mobile.viewportWidth);
  assert.ok(mobile.canvasWidth >= 350, `mobile canvas width was ${mobile.canvasWidth}`);
  assert.ok(mobile.canvasHeight >= 480, `mobile canvas height was ${mobile.canvasHeight}`);
  assert.ok(mobile.minButton >= 44, `mobile minimum button was ${mobile.minButton}`);
  await page.screenshot({ path: new URL("threejs-glb-review-mobile.png", root).pathname, fullPage: true });

  assert.deepEqual(consoleErrors, []);
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(externalRequests, []);
  assert.deepEqual(failedResponses, []);
  assert.deepEqual(requestFailures, []);
  console.log(JSON.stringify({ webgl, desktop, mobile, consoleErrors, pageErrors, externalRequests, failedResponses, requestFailures }, null, 2));
} catch (error) {
  const loaderWitness = await page.evaluate(() => window.__AXM_THREE_REVIEW__).catch(() => null);
  console.error("Three.js browser witness failed", error);
  console.error(JSON.stringify({ loaderWitness, consoleErrors, pageErrors, externalRequests, failedResponses, requestFailures }, null, 2));
  await page.screenshot({ path: new URL("threejs-glb-review-failure.png", root).pathname, fullPage: true }).catch(() => {});
  throw error;
} finally {
  await browser.close();
  server.kill("SIGTERM");
}
