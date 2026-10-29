import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Ubiquitous Export & Download Touchpoints', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('top header export button and dropdown are present and functional', async ({ page }) => {
    const btnHeaderExport = page.locator('#btnHeaderExport');
    await expect(btnHeaderExport).toBeVisible();
    await expect(btnHeaderExport).toBeDisabled();

    // Load sample document to enable export
    await page.locator('#btnSampleInvoice').click();
    await expect(btnHeaderExport).toBeEnabled();

    const dropdown = page.locator('#exportDropdownMenu');
    await expect(dropdown).toBeHidden();

    // Open dropdown
    await btnHeaderExport.click();
    await expect(dropdown).toBeVisible();

    // Verify all 4 export options exist
    await expect(page.locator('#menuExportPdf')).toBeVisible();
    await expect(page.locator('#menuExportHtml')).toBeVisible();
    await expect(page.locator('#menuExportMarkdown')).toBeVisible();
    await expect(page.locator('#menuExportImages')).toBeVisible();

    // Press Escape closes dropdown
    await page.keyboard.press('Escape');
    await expect(dropdown).toBeHidden();
  });

  test('sidebar contains highlighted Export & Download Hub', async ({ page }) => {
    const exportHubNav = page.locator('[data-tool="export-hub"]');
    await expect(exportHubNav).toBeVisible();
    await expect(exportHubNav).toContainText('Export & Download Hub');

    // Click to navigate to Export Hub
    await exportHubNav.click();
    await expect(exportHubNav).toHaveClass(/active/);
    await expect(page.locator('#currentToolTitle')).toContainText('Export & Download Hub');

    // Verify the export cards list is displayed
    await expect(page.locator('#btnHubDlPdf')).toBeVisible();
    await expect(page.locator('#btnHubExportHtml')).toBeVisible();
    await expect(page.locator('#btnHubExportDocx')).toBeVisible();
    await expect(page.locator('#btnHubExportMd')).toBeVisible();
    await expect(page.locator('#btnHubExportImages')).toBeVisible();
    await expect(page.locator('#btnHubExportAudit')).toBeVisible();
  });

  test('single primary export button exists in header without duplicate download buttons', async ({ page }) => {
    // 1. Upload sample document
    await page.locator('[data-tool="pdf-to-html"]').click();
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);

    // 2. Top header export button is the single primary export action
    const btnHeaderExport = page.locator('#btnHeaderExport');
    await expect(btnHeaderExport).toBeVisible();
    await expect(btnHeaderExport).toContainText('Export');

    // 3. Verify redundant buttons are removed / cut to one
    await expect(page.locator('#btnWorkspaceDlPdf')).toHaveCount(0);
    await expect(page.locator('.btn-card-dl')).toHaveCount(0);
    await expect(page.locator('#btnPreviewExport')).toBeHidden();
  });
});
