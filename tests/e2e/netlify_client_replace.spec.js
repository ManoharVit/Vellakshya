import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');
const CV_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/cv_test.pdf');

test.describe('In-Browser Client PDF Engine (Netlify Simulation)', () => {
  test('replaces text in-browser when backend /api is blocked or unreachable', async ({ page }) => {
    // Intercept and abort /api/* requests to simulate Netlify without backend
    await page.route('**/api/edit/replace-text', (route) => route.abort('failed'));

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Upload test PDF
    const fileInput = page.locator('#repUploadArea input[type="file"], input[type="file"]');
    await fileInput.first().setInputFiles(SAMPLE_PDF_PATH);
    await page.waitForTimeout(1000);

    // Open Word Find bar
    await page.locator('#btnToggleWordFind').click();
    await page.waitForTimeout(300);

    // Search for a word present in the sample PDF
    const searchInput = page.locator('#wfbSearchInput');
    await searchInput.fill('Sample');
    await page.waitForTimeout(500);

    const matchBadge = page.locator('#wfbMatchBadge');
    await expect(matchBadge).not.toHaveClass(/not-found/);

    // Replace with "ReplacedWord"
    const replaceInput = page.locator('#wfbReplaceInput');
    await replaceInput.fill('ReplacedWord');

    // Click Replace
    await page.locator('#wfbBtnReplace').click();
    await page.waitForTimeout(1000);

    // Verify zero error toasts appeared
    const errorToast = page.locator('.app-toast.toast-error');
    await expect(errorToast).toHaveCount(0);

    // Verify active document was updated with the 1 edit saved in memory
    const docName = page.locator('#previewDocName');
    await expect(docName).toHaveAttribute('title', /1 edit saved/i);
  });

  test('replaces "Giri" with "Manohar" in CV document cleanly without backend', async ({ page }) => {
    await page.route('**/api/edit/replace-text', (route) => route.abort('failed'));

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Upload CV test PDF
    const fileInput = page.locator('#repUploadArea input[type="file"], input[type="file"]');
    await fileInput.first().setInputFiles(CV_PDF_PATH);
    await page.waitForTimeout(1000);

    // Open Word Find bar
    await page.locator('#btnToggleWordFind').click();
    await page.waitForTimeout(300);

    // Search for "Giri"
    const searchInput = page.locator('#wfbSearchInput');
    await searchInput.fill('Giri');
    await page.waitForTimeout(500);

    const matchBadge = page.locator('#wfbMatchBadge');
    await expect(matchBadge).toContainText('1 of 1');

    // Replace with "Manohar"
    const replaceInput = page.locator('#wfbReplaceInput');
    await replaceInput.fill('Manohar');

    // Click Replace
    await page.locator('#wfbBtnReplace').click();
    await page.waitForTimeout(1000);

    // Verify active document updated with 1 edit saved
    const docName = page.locator('#previewDocName');
    await expect(docName).toHaveAttribute('title', /1 edit saved/i);

    // Now search for "Manohar" and verify it is matched
    await searchInput.fill('Manohar');
    await page.waitForTimeout(500);
    await expect(matchBadge).toContainText('1 of 1');

    // Search for "Giri" and verify it is no longer found (0 of 0 or not-found)
    await searchInput.fill('Giri');
    await page.waitForTimeout(500);
    await expect(matchBadge).toHaveClass(/not-found/);
  });
});
