import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Vellakshya Web End-to-End User Experience', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('loads single-page application header, title and brand', async ({ page }) => {
    await expect(page).toHaveTitle(/Vellakshya/);
    const brandTitle = page.locator('.brand-title');
    await expect(brandTitle).toHaveText('Vellakshya');
  });

  test('navigates sidebar tools seamlessly', async ({ page }) => {
    // 1. Click on Deep Document Inspector
    const inspectorTool = page.locator('[data-tool="inspect"]');
    await inspectorTool.click();
    await expect(inspectorTool).toHaveClass(/active/);
    const toolTitle = page.locator('#currentToolTitle');
    await expect(toolTitle).toContainText('Document Inspector');

    // 2. Click on Find & Replace tool
    const replaceTool = page.locator('[data-tool="replace-text"]');
    await replaceTool.click();
    await expect(replaceTool).toHaveClass(/active/);
    await expect(toolTitle).toContainText('Find & Replace');
  });

  test('handles file upload and document viewer initialization', async ({ page }) => {
    // Switch to PDF-to-HTML tool
    await page.locator('[data-tool="pdf-to-html"]').click();

    // Set file directly via hidden file input
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_PDF_PATH);

    // Verify preview status reflects uploaded document
    const previewStatus = page.locator('#previewStatus');
    await expect(previewStatus).toContainText('sample.pdf');
  });

  test('undo and redo buttons remain disabled when history stack is empty', async ({ page }) => {
    const btnUndo = page.locator('#btnHeaderUndo');
    const btnRedo = page.locator('#btnHeaderRedo');

    await expect(btnUndo).toBeDisabled();
    await expect(btnRedo).toBeDisabled();
  });
});
