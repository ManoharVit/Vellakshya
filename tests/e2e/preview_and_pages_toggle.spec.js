import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Preview and Pages Hide/Show Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('toggles Preview hide/show when clicking Preview button', async ({ page }) => {
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);
    await page.waitForTimeout(800);

    // Initial state: preview is visible
    await expect(page.locator('#interactivePdfViewer')).toBeVisible();
    await expect(page.locator('#previewHiddenPlaceholder')).not.toBeVisible();
    await expect(page.locator('.preview-tab[data-tab="preview"]')).toHaveText('Preview');

    // Click Preview to hide
    await page.locator('.preview-tab[data-tab="preview"]').click();
    await expect(page.locator('#interactivePdfViewer')).not.toBeVisible();
    await expect(page.locator('#previewHiddenPlaceholder')).toBeVisible();
    await expect(page.locator('.preview-tab[data-tab="preview"]')).toHaveText('Preview (Hidden)');

    // Click Preview to show
    await page.locator('.preview-tab[data-tab="preview"]').click();
    await expect(page.locator('#interactivePdfViewer')).toBeVisible();
    await expect(page.locator('#previewHiddenPlaceholder')).not.toBeVisible();
    await expect(page.locator('.preview-tab[data-tab="preview"]')).toHaveText('Preview');
  });

  test('toggles Pages hide/show when clicking Pages button in header and toolbar', async ({ page }) => {
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);
    await page.waitForTimeout(800);

    // Initial state: thumbnail strip is visible
    await expect(page.locator('#thumbnailStrip')).toBeVisible();
    await expect(page.locator('#btnTogglePages')).toHaveClass(/active/);

    // Click Pages header in thumbnail strip to hide
    await page.locator('#thumbnailStripHeader').click();
    await expect(page.locator('#thumbnailStrip')).not.toBeVisible();
    await expect(page.locator('#btnTogglePages')).not.toHaveClass(/active/);

    // Click Pages button in toolbar to show
    await page.locator('#btnTogglePages').click();
    await expect(page.locator('#thumbnailStrip')).toBeVisible();
    await expect(page.locator('#btnTogglePages')).toHaveClass(/active/);

    // Click Pages button in toolbar again to hide
    await page.locator('#btnTogglePages').click();
    await expect(page.locator('#thumbnailStrip')).not.toBeVisible();
  });

  test('direct restore button in hidden placeholder restores preview', async ({ page }) => {
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);
    await page.waitForTimeout(800);

    // Hide preview
    await page.locator('.preview-tab[data-tab="preview"]').click();
    await expect(page.locator('#previewHiddenPlaceholder')).toBeVisible();

    // Click "Show Document Preview" direct restore button
    await page.locator('#btnRestorePreviewDirect').click();
    await expect(page.locator('#interactivePdfViewer')).toBeVisible();
    await expect(page.locator('#previewHiddenPlaceholder')).not.toBeVisible();
  });
});
