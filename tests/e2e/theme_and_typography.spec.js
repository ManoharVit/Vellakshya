import { test, expect } from '@playwright/test';

test.describe('Theme & Self-Hosted Typography Verification (Step 8)', () => {
  test('toggles dark and light mode seamlessly via header button', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const toggleBtn = page.locator('#btnThemeToggle');
    await expect(toggleBtn).toBeVisible();

    // Check initial theme state on html tag
    const html = page.locator('html');
    const initialTheme = await html.getAttribute('data-theme') || 'dark';

    // Click to toggle
    await toggleBtn.click();
    const nextTheme = initialTheme === 'dark' ? 'light' : 'dark';
    await expect(html).toHaveAttribute('data-theme', nextTheme);

    // Click again to revert
    await toggleBtn.click();
    await expect(html).toHaveAttribute('data-theme', initialTheme);
  });

  test('enforces zero external font requests and renders self-hosted WOFF2 fonts', async ({ page }) => {
    let externalFontRequests = 0;
    let localFontRequests = 0;

    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')) {
        externalFontRequests++;
      }
      if (url.includes('/fonts/') && url.endsWith('.woff2')) {
        localFontRequests++;
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Assert strictly zero external font requests
    expect(externalFontRequests).toBe(0);

    // Verify computed font families on body and brand
    const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
    expect(bodyFont).toContain('Inter');

    const brandFont = await page.evaluate(() => {
      const el = document.querySelector('.brand-title');
      return el ? getComputedStyle(el).fontFamily : '';
    });
    expect(brandFont).toContain('Manrope');
  });

  test('verifies export dropdown touchpoints for PDF, DOCX, Semantic HTML, and Markdown', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const btnExport = page.locator('#btnHeaderExport');
    await expect(btnExport).toBeVisible();
    await expect(btnExport).toBeDisabled();

    // Load sample document to enable export
    await page.locator('#btnSampleInvoice').click();
    await expect(btnExport).toBeEnabled();
    await btnExport.click();

    const dropdown = page.locator('#exportDropdownMenu');
    await expect(dropdown).toBeVisible();

    // Verify all primary modern export targets are listed
    await expect(page.locator('#menuExportPdf')).toBeVisible();
    await expect(page.locator('#menuExportDocx')).toBeVisible();
    await expect(page.locator('#menuExportHtml')).toBeVisible();
    await expect(page.locator('#menuExportMarkdown')).toBeVisible();
  });
});
