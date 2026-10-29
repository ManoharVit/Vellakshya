const { chromium } = require("@playwright/test");
const path = require("path");

const ARTIFACT_DIR = "/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  // 1. Dark Mode Empty State
  await page.goto("http://127.0.0.1:8000/");
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_dark_empty.png") });
  console.log("Saved: symbol_overhaul_dark_empty.png");

  // 2. Dark Mode Loaded Document (Sample Invoice)
  await page.locator("#btnSampleInvoice").click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_dark_loaded.png") });
  console.log("Saved: symbol_overhaul_dark_loaded.png");

  // 3. Export Hub in Dark Mode
  await page.locator('[data-tool="export-hub"]').click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_export_hub.png") });
  console.log("Saved: symbol_overhaul_export_hub.png");

  // 4. Word-style Find & Replace Bar in Dark Mode
  await page.locator('[data-tool="replace-text"]').click();
  await page.waitForTimeout(600);
  await page.locator("#btnToggleWordFind").click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_find_replace.png") });
  console.log("Saved: symbol_overhaul_find_replace.png");

  // 5. Light Mode Empty State
  await page.goto("http://127.0.0.1:8000/");
  await page.waitForTimeout(500);
  // Switch to light mode
  await page.locator("#btnThemeToggle").click();
  await page.waitForTimeout(200);
  await page.locator('.theme-dropdown-item[data-theme-val="light"]').click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_light_empty.png") });
  console.log("Saved: symbol_overhaul_light_empty.png");

  // 6. Light Mode Loaded Document
  await page.locator("#btnSampleInvoice").click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "symbol_overhaul_light_loaded.png") });
  console.log("Saved: symbol_overhaul_light_loaded.png");

  await browser.close();
  console.log("All screenshots captured successfully!");
})();
