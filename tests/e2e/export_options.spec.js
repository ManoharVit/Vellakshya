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
    await expect(page.locator('#btnHubExportMd')).toBeVisible();
    await expect(page.locator('#btnHubExportImages')).toBeVisible();
    await expect(page.locator('#btnHubExportAudit')).toBeVisible();
  });

  test('export buttons appear on canvas toolbar, workspace subheader, and tool card upon document load', async ({ page }) => {
    // 1. Upload sample document
    await page.locator('[data-tool="pdf-to-html"]').click();
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);

    // 2. Preview canvas toolbar export button must become visible
    const btnPreviewExport = page.locator('#btnPreviewExport');
    await expect(btnPreviewExport).toBeVisible({ timeout: 10000 });
    await expect(btnPreviewExport).toContainText('Export PDF');

    // 3. Workspace sub-header export button must be present
    const btnWorkspaceExport = page.locator('#btnWorkspaceDlPdf');
    await expect(btnWorkspaceExport).toBeVisible();
    await expect(btnWorkspaceExport).toContainText('Download PDF');

    // 4. Active document card download button must be present in tool config panel
    const btnCardDl = page.locator('.btn-card-dl');
    await expect(btnCardDl).toBeVisible();
    await expect(btnCardDl).toContainText('Download');

    // 5. Switching tools must retain the workspace export button
    await page.locator('[data-tool="rotate-pages"]').click();
    await expect(btnWorkspaceExport).toBeVisible();

    await page.locator('[data-tool="inspect"]').click();
    await expect(btnWorkspaceExport).toBeVisible();
  });
});
