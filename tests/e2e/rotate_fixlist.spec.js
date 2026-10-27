import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Rotate Tool and Unified Components', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('verifies rotate tool UI, live preview, syntax validation, and thumbnail controls', async ({ page }) => {
    // Switch to Rotate Pages tool
    await page.click('.nav-item[data-tool="rotate-pages"]');
    await page.waitForTimeout(400);

    // Upload test PDF
    const fileInput = page.locator("#rotateUploadArea input[type='file']");
    await fileInput.setInputFiles(SAMPLE_PDF_PATH);
    await page.waitForTimeout(1000);

    // 1. Verify file chip truncation and title attribute
    const chip = page.locator('.loaded-file-chip');
    await expect(chip).toBeVisible();
    const filenameEl = page.locator('.loaded-file-chip .chip-filename');
    await expect(filenameEl).toHaveAttribute('title', /sample\.pdf/i);

    // 2. Verify thumbnail rail is visible with per-page rotate buttons
    const thumbStrip = page.locator('#thumbnailStrip');
    await expect(thumbStrip).toBeVisible();
    const rotateBtns = page.locator('.btn-thumb-rotate');
    const rotateBtnCount = await rotateBtns.count();
    expect(rotateBtnCount).toBeGreaterThanOrEqual(1);

    // 3. Verify Delete button is hidden on Rotate screen
    const delBtns = page.locator('.btn-delete-page-direct');
    const delBtnCount = await delBtns.count();
    for (let i = 0; i < delBtnCount; i++) {
      await expect(delBtns.nth(i)).not.toBeVisible();
    }

    // 4. Verify syntax documentation
    const syntaxDocs = page.locator('.range-syntax-docs');
    await expect(syntaxDocs).toBeVisible();
    await expect(syntaxDocs).toContainText('1-5');
    await expect(syntaxDocs).toContainText('odd');
    await expect(syntaxDocs).toContainText('even');

    // 5. Test live preview badges
    const previewBadges = page.locator('.live-rotate-preview-badge');
    await expect(previewBadges.first()).toBeAttached({ timeout: 5000 });

    // 6. Test keywords validation
    const pagesInput = page.locator('#rotatePages');
    await pagesInput.fill('odd');
    await page.waitForTimeout(300);
    const feedback = page.locator('#rotatePagesFeedback');
    await expect(feedback).toContainText('Odd pages');

    await pagesInput.fill('invalid_token');
    await page.waitForTimeout(300);
    await expect(feedback).toContainText('Unrecognized token');
  });
});
