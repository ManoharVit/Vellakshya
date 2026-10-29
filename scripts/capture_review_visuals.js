const { chromium } = require('playwright');
const path = require('path');

const ARTIFACT_DIR = '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2
  });
  const page = await context.newPage();

  console.log('Navigating to http://localhost:8000 ...');
  await page.goto('http://localhost:8000');
  await page.waitForLoadState('networkidle');

  // 1. Capture Dark Mode default state
  await page.screenshot({
    path: path.join(ARTIFACT_DIR, 'pr_dark_mode_conformance.png'),
    fullPage: false
  });
  console.log('Saved pr_dark_mode_conformance.png');

  // 2. Switch to Light Mode via theme toggle
  const themeToggle = page.locator('#btnThemeToggle');
  await themeToggle.click();
  await page.waitForTimeout(500);

  // Verify data-theme attribute is light
  const themeAttr = await page.getAttribute('html', 'data-theme');
  console.log(`Current data-theme: ${themeAttr}`);

  // Capture Light Mode clean state
  await page.screenshot({
    path: path.join(ARTIFACT_DIR, 'pr_light_mode_conformance.png'),
    fullPage: false
  });
  console.log('Saved pr_light_mode_conformance.png');

  // 3. Load sample document to inspect active stepper & controls in Light Mode
  await page.locator('#btnSampleInvoice').click();
  await page.waitForTimeout(1000);

  await page.screenshot({
    path: path.join(ARTIFACT_DIR, 'pr_light_mode_document_loaded.png'),
    fullPage: false
  });
  console.log('Saved pr_light_mode_document_loaded.png');

  await browser.close();
  console.log('Visual capture complete!');
})();
