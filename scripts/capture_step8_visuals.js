const { chromium } = require('playwright');
const path = require('path');

const ARTIFACTS_DIR = '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0';
const SAMPLE_PDF = path.resolve(__dirname, '../test-data/sample-pdfs/sample.pdf');

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  console.log('[Step 8] Navigating to Vellakshya live workstation...');
  await page.goto('http://127.0.0.1:8000/');
  await page.waitForLoadState('networkidle');

  // 1. Upload sample document
  const fileInput = page.locator('input[type="file"]');
  await fileInput.first().setInputFiles(SAMPLE_PDF);
  await page.waitForTimeout(1000);

  // 2. Capture Dark Mode
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'step8_live_dark_mode.png'), fullPage: false });
  console.log('[Step 8] Captured step8_live_dark_mode.png');

  // 3. Open Export Menu and capture
  const btnExport = page.locator('#btnHeaderExport');
  await btnExport.click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'step8_live_export_menu.png'), fullPage: false });
  console.log('[Step 8] Captured step8_live_export_menu.png');
  await page.keyboard.press('Escape');

  // 4. Toggle to Light Mode and capture
  const toggleBtn = page.locator('#btnThemeToggle');
  await toggleBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'step8_live_light_mode.png'), fullPage: false });
  console.log('[Step 8] Captured step8_live_light_mode.png');

  // 5. Open Word Find Bar and execute in-browser replace
  await page.locator('#btnToggleWordFind').click();
  await page.waitForTimeout(300);
  await page.locator('#wfbSearchInput').fill('Sample');
  await page.waitForTimeout(400);
  await page.locator('#wfbReplaceInput').fill('Vellakshya');
  await page.locator('#wfbBtnReplace').click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'step8_live_word_replace.png'), fullPage: false });
  console.log('[Step 8] Captured step8_live_word_replace.png');

  await browser.close();
  console.log('[Step 8] Visual verification screenshots saved successfully.');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
