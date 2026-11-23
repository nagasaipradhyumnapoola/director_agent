#!/usr/bin/env node
// Bounded Chromium DevTools Protocol probe for the DIRECTOR website pilot.
// Launches a headless local browser, runs a real user journey, keyboard and
// mobile checks, captures bounded evidence, and writes JSON. No shell.

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const browserPath = arg("--browser", "");
const site = arg("--site", "");
const outPath = path.resolve(arg("--out", "probe.json"));
const shotDir = path.resolve(arg("--shot-dir", "shots"));
const timeoutMs = Number(arg("--timeout", "30000"));
const MAX_TEXT = 4000;
const MAX_REQUESTS = 100;

let child = null;
let finished = false;

function killTree() {
  if (!child) return;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/T", "/F", "/PID", String(child.pid)], {
        windowsHide: true,
        timeout: 8000,
      });
    } else {
      child.kill("SIGKILL");
    }
  } catch (_) {}
}

function writeOut(payload, code) {
  if (finished) return;
  finished = true;
  try {
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf8");
  } catch (_) {}
  killTree();
  process.exit(code);
}

function fail(message) {
  writeOut({ ok: false, error: String(message).slice(0, 500) }, 2);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class CDP {
  constructor(url) {
    this.url = url;
    this.ws = new WebSocket(url);
    this.seq = 0;
    this.pending = new Map();
    this.listeners = new Map();
  }
  async open() {
    await new Promise((resolve, reject) => {
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error("websocket error"));
    });
    this.ws.onmessage = (event) => this.handle(event.data);
    this.ws.onerror = () => {};
    this.ws.onclose = () => {
      for (const entry of this.pending.values()) entry.reject(new Error("websocket closed"));
      this.pending.clear();
    };
  }
  handle(data) {
    let text = data;
    if (typeof text !== "string") {
      try {
        text = Buffer.from(text).toString("utf8");
      } catch (_) {
        return;
      }
    }
    let message;
    try {
      message = JSON.parse(text);
    } catch (_) {
      return;
    }
    if (message.id) {
      const entry = this.pending.get(message.id);
      if (!entry) return;
      this.pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message || "cdp error"));
      else entry.resolve(message.result || {});
      return;
    }
    if (message.method) {
      const callbacks = this.listeners.get(message.method) || [];
      for (const callback of callbacks) {
        try {
          callback(message.params || {});
        } catch (_) {}
      }
    }
  }
  on(method, callback) {
    const list = this.listeners.get(method) || [];
    list.push(callback);
    this.listeners.set(method, list);
  }
  send(method, params = {}) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (error) {
        this.pending.delete(id);
        reject(error);
      }
    });
  }
  close() {
    try {
      this.ws.close();
    } catch (_) {}
  }
}

function waitEvent(cdp, method, ms) {
  return new Promise((resolve, reject) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      reject(new Error("timeout waiting for " + method));
    }, ms);
    cdp.on(method, (params) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(params);
    });
  });
}

async function waitForFile(file, ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (fs.existsSync(file)) return true;
    await sleep(100);
  }
  return false;
}

function boundedPush(list, value, cap) {
  if (list.length < cap) list.push(value);
}

function pressKey(cdp, key, code, vk, text) {
  return (async () => {
    const down = {
      type: "keyDown",
      key,
      code,
      windowsVirtualKeyCode: vk,
      nativeVirtualKeyCode: vk,
    };
    if (text) down.text = text;
    await cdp.send("Input.dispatchKeyEvent", down);
    await cdp.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key,
      code,
      windowsVirtualKeyCode: vk,
      nativeVirtualKeyCode: vk,
    });
  })();
}

async function main() {
  const startedAt = Date.now();
  if (!browserPath || !fs.existsSync(browserPath)) return fail("browser executable missing");
  if (!site || !fs.existsSync(site)) return fail("site entry missing");
  fs.mkdirSync(shotDir, { recursive: true });
  const profile = path.resolve("profile");
  fs.mkdirSync(profile, { recursive: true });

  const args = [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-breakpad",
    "--metrics-recording-only",
    "--mute-audio",
    "--remote-debugging-port=0",
    "--remote-allow-origins=*",
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--user-data-dir=" + profile,
    "about:blank",
  ];
  let stderr = "";
  child = spawn(browserPath, args, {
    cwd: process.cwd(),
    windowsHide: true,
    stdio: ["ignore", "ignore", "pipe"],
  });
  child.stderr.on("data", (chunk) => {
    if (stderr.length < 4000) stderr += String(chunk);
  });
  child.on("exit", (code) => {
    if (!finished && code !== 0) fail("browser exited early: " + stderr.slice(0, 400));
  });

  const portFile = path.join(profile, "DevToolsActivePort");
  if (!(await waitForFile(portFile, 15000))) return fail("DevToolsActivePort not created");
  const lines = fs.readFileSync(portFile, "utf8").split(/\r?\n/);
  const port = Number(lines[0]);
  const browserPathWs = lines[1] || "";
  if (!port || !browserPathWs) return fail("invalid DevToolsActivePort");

  let browserCdp = null;
  try {
    browserCdp = new CDP(`ws://127.0.0.1:${port}${browserPathWs}`);
    await browserCdp.open();
  } catch (_) {
    browserCdp = null;
  }

  let target = null;
  const listDeadline = Date.now() + 10000;
  while (Date.now() < listDeadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await response.json();
      target = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl) || null;
      if (target) break;
    } catch (_) {}
    await sleep(150);
  }
  if (!target) return fail("no page target");

  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  const consoleErrors = [];
  const requests = [];
  cdp.on("Runtime.exceptionThrown", (params) => {
    const detail = params.exceptionDetails || {};
    boundedPush(consoleErrors, { source: "exception", text: String(detail.text || detail.exception?.description || "exception").slice(0, 300) }, 50);
  });
  cdp.on("Runtime.consoleAPICalled", (params) => {
    if (params.type === "error") {
      const text = (params.args || [])
        .map((item) => String(item.value ?? item.description ?? ""))
        .join(" ")
        .slice(0, 300);
      boundedPush(consoleErrors, { source: "console", text }, 50);
    }
  });
  cdp.on("Log.entryAdded", (params) => {
    const entry = params.entry || {};
    if (entry.level === "error") {
      boundedPush(consoleErrors, { source: "log", text: String(entry.text || "").slice(0, 300) }, 50);
    }
  });
  cdp.on("Network.requestWillBeSent", (params) => {
    const request = params.request || {};
    boundedPush(requests, { url: String(request.url || "").slice(0, 500), type: params.type || "" }, MAX_REQUESTS);
  });

  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Log.enable");
  await cdp.send("Network.enable");
  await cdp.send("Accessibility.enable");

  const url = pathToFileURL(path.resolve(site)).href;
  const loaded = waitEvent(cdp, "Page.loadEventFired", 15000);
  await cdp.send("Page.navigate", { url });
  await loaded.catch(() => {});
  await sleep(350);

  async function evaluate(expression) {
    const result = await cdp.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: false,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error("evaluate exception: " + String(result.exceptionDetails.text || "").slice(0, 200));
    }
    return result.result ? result.result.value : null;
  }

  const steps = [];
  async function step(name, fn) {
    try {
      const value = await fn();
      steps.push({
        name,
        ok: Boolean(value && value.ok),
        reason: String((value && value.reason) || "").slice(0, 300),
        details: value && value.details ? value.details : null,
      });
    } catch (error) {
      steps.push({ name, ok: false, reason: String(error.message || error).slice(0, 300), details: null });
    }
  }

  await step("search", async () => {
    const controls = await evaluate(`(() => {
      const input = document.querySelector('#search');
      const button = document.querySelector('#search-button');
      const results = document.querySelector('#results');
      if (!input || !button || !results) return { ok: false, reason: 'search controls missing' };
      input.focus();
      input.value = 'mug';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      button.click();
      return { ok: true };
    })()`);
    await sleep(250);
    const visible = await evaluate(`(() => {
      const results = document.querySelector('#results');
      return Boolean(results && !results.hidden && document.querySelectorAll('.product').length > 0);
    })()`);
    return { ok: Boolean(controls && controls.ok && visible), reason: visible ? "" : "no visible results" };
  });

  await step("add_to_cart", async () => {
    const clicked = await evaluate(`(() => {
      const element = document.querySelector('#add-to-cart');
      if (!element) return { ok: false, reason: 'add control missing' };
      element.click();
      return { ok: true };
    })()`);
    await sleep(250);
    const cart = await evaluate(`(document.querySelector('#cart') || {}).textContent || ''`);
    return {
      ok: Boolean(clicked && clicked.ok && /Cart:\s*1\b/.test(String(cart))),
      reason: String(cart).slice(0, 100),
      details: { cart_text: String(cart).slice(0, 100) },
    };
  });

  await step("checkout", async () => {
    const clicked = await evaluate(`(() => {
      const element = document.querySelector('#checkout');
      if (!element) return { ok: false, reason: 'checkout control missing' };
      element.click();
      return { ok: true };
    })()`);
    await sleep(250);
    const confirmation = await evaluate(`(() => {
      const element = document.querySelector('#confirmation');
      if (!element) return null;
      return { hidden: Boolean(element.hidden), text: String(element.textContent || '').slice(0, 200) };
    })()`);
    return {
      ok: Boolean(clicked && clicked.ok && confirmation && !confirmation.hidden && /Order confirmed/i.test(confirmation.text)),
      reason: confirmation ? (confirmation.hidden ? "confirmation hidden" : "confirmation shown") : "confirmation missing",
      details: confirmation,
    };
  });

  const journeyOk = steps.every((item) => item.ok);

  const reloaded = waitEvent(cdp, "Page.loadEventFired", 10000);
  await cdp.send("Page.reload", { ignoreCache: true });
  await reloaded.catch(() => {});
  await sleep(250);

  async function focusBody() {
    await evaluate(`(() => { document.body.setAttribute('tabindex', '-1'); document.body.focus(); return true; })()`);
  }
  async function activeElement() {
    return evaluate(`(() => {
      const element = document.activeElement;
      if (!element) return null;
      return {
        tag: element.tagName.toLowerCase(),
        id: element.id || '',
        role: element.getAttribute('role') || '',
        text: String(element.textContent || '').trim().slice(0, 80),
      };
    })()`);
  }

  const sequence = [];
  await focusBody();
  for (let i = 0; i < 16; i += 1) {
    await pressKey(cdp, "Tab", "Tab", 9);
    await sleep(40);
    const info = await activeElement();
    if (info) sequence.push(info);
  }
  const addReachable = sequence.some((item) => item.id === "add-to-cart" || /Add to cart/i.test(item.text));
  const checkoutReachable = sequence.some((item) => item.id === "checkout" || /Checkout/i.test(item.text));

  let addActivated = false;
  let addFocusedByKeyboard = false;
  await focusBody();
  for (let i = 0; i < 20; i += 1) {
    await pressKey(cdp, "Tab", "Tab", 9);
    await sleep(40);
    const info = await activeElement();
    if (info && (info.id === "add-to-cart" || /Add to cart/i.test(info.text))) {
      addFocusedByKeyboard = true;
      break;
    }
  }
  if (addFocusedByKeyboard) {
    await pressKey(cdp, "Enter", "Enter", 13, "\r");
    await sleep(250);
    const cart = await evaluate(`(document.querySelector('#cart') || {}).textContent || ''`);
    addActivated = /Cart:\s*1\b/.test(String(cart));
  }

  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await sleep(200);
  const desktopOverflow = await evaluate(`(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);

  async function screenshot(name) {
    const capture = await cdp.send("Page.captureScreenshot", { format: "png" });
    const buffer = Buffer.from(String(capture.data || ""), "base64");
    if (buffer.length > 8 * 1024 * 1024) throw new Error("screenshot too large");
    const target = path.join(shotDir, name);
    fs.writeFileSync(target, buffer);
    return {
      name,
      sha256: crypto.createHash("sha256").update(buffer).digest("hex"),
      bytes: buffer.length,
    };
  }
  const screenshots = [];
  screenshots.push(await screenshot("desktop.png"));

  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await sleep(250);
  const mobileOverflow = await evaluate(`(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }))()`);
  screenshots.push(await screenshot("mobile.png"));

  const ax = await cdp.send("Accessibility.getFullAXTree");
  const axNodes = (ax.nodes || []).slice(0, 300).map((node) => ({
    role: (node.role && node.role.value) || "",
    name: String((node.name && node.name.value) || "").slice(0, 120),
    ignored: Boolean(node.ignored),
  }));
  const addNode = axNodes.find((node) => /Add to cart/i.test(node.name)) || null;
  const searchNode =
    axNodes.find(
      (node) => /search/i.test(node.name) && ["searchbox", "textbox", "combobox"].includes(node.role)
    ) || null;

  const externalRequests = [];
  const seen = new Set();
  for (const request of requests) {
    if (/^https?:\/\//i.test(request.url) && !seen.has(request.url)) {
      seen.add(request.url);
      if (externalRequests.length < 20) externalRequests.push(request);
    }
  }

  let browserVersion = null;
  if (browserCdp) {
    try {
      browserVersion = await browserCdp.send("Browser.getVersion");
    } catch (_) {}
  }

  const payload = {
    ok: true,
    url,
    browser: browserPath,
    browser_version: browserVersion ? browserVersion.product : null,
    journey: { steps, ok: journeyOk },
    keyboard: {
      sequence,
      add_reachable: addReachable,
      checkout_reachable: checkoutReachable,
      add_focused_by_keyboard: addFocusedByKeyboard,
      add_activated: addActivated,
    },
    mobile: {
      width: 390,
      scroll_width: Number(mobileOverflow && mobileOverflow.scrollWidth),
      client_width: Number(mobileOverflow && mobileOverflow.clientWidth),
      overflow_px: Number(mobileOverflow && mobileOverflow.scrollWidth) - Number(mobileOverflow && mobileOverflow.clientWidth),
    },
    desktop: {
      width: 1280,
      scroll_width: Number(desktopOverflow && desktopOverflow.scrollWidth),
      client_width: Number(desktopOverflow && desktopOverflow.clientWidth),
      overflow_px: Number(desktopOverflow && desktopOverflow.scrollWidth) - Number(desktopOverflow && desktopOverflow.clientWidth),
    },
    console_errors: consoleErrors,
    network: {
      total_requests: requests.length,
      external_requests: externalRequests,
      external_count: externalRequests.length,
    },
    accessibility: {
      nodes: axNodes,
      add_role: addNode ? addNode.role : null,
      add_name: addNode ? addNode.name : null,
      search_name: searchNode ? searchNode.name : null,
      search_role: searchNode ? searchNode.role : null,
    },
    screenshots,
    runtime_ms: Date.now() - startedAt,
  };

  if (browserCdp) {
    try {
      await browserCdp.send("Browser.close");
    } catch (_) {}
    browserCdp.close();
  }
  cdp.close();
  writeOut(payload, 0);
}

const watchdog = setTimeout(() => fail("probe watchdog timeout"), timeoutMs + 8000);
watchdog.unref();

main().catch((error) => fail(error && error.message ? error.message : error));


