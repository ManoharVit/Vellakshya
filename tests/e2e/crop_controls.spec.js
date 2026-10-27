import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Crop Tool & Active Document Card Polish', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.locator('[data-tool="crop-pages"]').click();
  });

  test('coordinate grid fits inside panel without horizontal scroll', async ({ page }) => {
    const panel = page.locator('.tool-panel');
    const scrollInfo = await panel.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollInfo.scrollWidth).toBeLessThanOrEqual(scrollInfo.clientWidth + 1);
  });

  test('labels each coordinate field (X0, Y0, X1, Y1) individually', async ({ page }) => {
    const labels = await page.locator('#cropBoxControls .coord-label').allTextContents();
    expect(labels).toEqual(['X0 (Left)', 'Y0 (Top)', 'X1 (Right)', 'Y1 (Bottom)']);
  });

  test('places Quick Presets above the coordinate inputs', async ({ page }) => {
    const presetIndex = await page.evaluate(() => {
      const preset = document.getElementById('cropPreset').closest('.form-group');
      const box = document.getElementById('cropBoxControls');
      const children = Array.from(preset.parentElement.children);
      return {
        presetPos: children.indexOf(preset),
        boxPos: children.indexOf(box),
      };
    });
    expect(presetIndex.presetPos).toBeLessThan(presetIndex.boxPos);
  });

  test('shortens dropdown option labels', async ({ page }) => {
    const modeOpts = await page.locator('#cropMode option').allTextContents();
    expect(modeOpts).toEqual(['Bounding Box', 'Margin Trimming']);

    const presetOpts = await page.locator('#cropPreset option').allTextContents();
    expect(presetOpts[1]).toBe('0.5" Margins (36 pt)');
    expect(presetOpts[2]).toBe('1.0" Margins (72 pt)');
    expect(presetOpts[3]).toBe('Header & Footer (50 pt)');
  });

  test('restores real filename in Active Document card and draws default crop box on preview', async ({ page }) => {
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);
    await page.waitForTimeout(1000);

    // 1. Real filename in Active Document card
    const activeFilename = page.locator('.active-card-filename');
    await expect(activeFilename).toBeVisible();
    await expect(activeFilename).toHaveText('sample.pdf');

    // 2. Default crop box drawn on preview canvas
    const cropMarker = page.locator('.locked-crop-marker');
    await expect(cropMarker).toBeVisible();
    await expect(cropMarker).toContainText('Crop Box');
    await expect(cropMarker).toContainText('[36, 36] to [576, 756] pt');
  });
});
