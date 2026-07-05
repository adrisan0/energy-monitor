const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "../..");

function directLed() {
  const code = [
    "from flux_led import WifiLedBulb",
    "import json",
    "b=WifiLedBulb('192.168.1.29')",
    "b.query_state()",
    "print(json.dumps({'rgb':list(b.rgb) if isinstance(b.rgb, tuple) else b.rgb, 'brightness':b.brightness, 'mode':b.mode, 'is_on':b.is_on}))",
  ].join("; ");
  const out = execFileSync("docker", ["compose", "exec", "backend", "python", "-c", code], {
    encoding: "utf8",
    cwd: root,
  });
  return JSON.parse(out.trim());
}

async function apiState(page) {
  const response = await page.request.get("http://localhost:8000/api/v1/devices/6/state");
  return await response.json();
}

async function setFirstColor(page, hex) {
  await page.locator('input[type="color"]').first().fill(hex);
}

async function setFirstRange(page, value) {
  await page.locator('input[type="range"]').first().fill(String(value));
}

async function snapshot(page, label) {
  await page.waitForTimeout(2500);
  console.log(`\n### ${label}`);
  console.log("api", JSON.stringify(await apiState(page)));
  console.log("direct", JSON.stringify(directLed()));
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/v1/devices/6")) return;
    let body = "";
    try {
      body = await response.text();
    } catch {
      body = "";
    }
    console.log("HTTP", response.status(), url, body.slice(0, 300));
  });
  page.on("request", (request) => {
    const url = request.url();
    if (!url.includes("/api/v1/devices/6")) return;
    console.log("REQ", request.method(), url, request.postData() || "");
  });
  page.on("pageerror", (error) => console.log("PAGEERROR", error.message));
  page.on("console", (message) => console.log("CONSOLE", message.type(), message.text()));

  await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Luces/i }).click();
  await page.getByRole("heading", { name: "Control manual" }).waitFor({ timeout: 10000 });
  await snapshot(page, "initial UI loaded");

  await setFirstColor(page, "#ff0000");
  await setFirstRange(page, 255);
  await page.getByRole("button", { name: /^Aplicar color$/i }).click();
  await snapshot(page, "after UI manual red 255");

  await setFirstColor(page, "#00ff00");
  await setFirstRange(page, 255);
  await page.getByRole("button", { name: /^Aplicar color$/i }).click();
  await snapshot(page, "after UI manual green 255");

  const surplus = page.getByLabel(/Usar color especial de excedente/i);
  if (await surplus.isChecked()) await surplus.uncheck();
  await page.getByRole("button", { name: /^Probar automatizacion ahora$/i }).click();
  await snapshot(page, "after UI auto test no surplus");

  await page.getByRole("button", { name: /^Modo automatico$/i }).click();
  await snapshot(page, "after UI mode automatic");

  await setFirstColor(page, "#9b009e");
  await setFirstRange(page, 255);
  await page.getByRole("button", { name: /^Aplicar color$/i }).click();
  await snapshot(page, "after UI manual purple from automatic");

  await browser.close();
})();
