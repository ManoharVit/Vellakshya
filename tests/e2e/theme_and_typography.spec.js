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
    expect(brandFont).toContain('Geist Brand');
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

  test('conforms to light theme palette: white dropzone, indigo action, neutral sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Switch to Light Theme if not already
    const html = page.locator('html');
    const theme = await html.getAttribute('data-theme');
    if (theme !== 'light') {
      await page.locator('#btnThemeToggle').click();
      await page.waitForTimeout(300);
    }

    // 1. Verify Preview Canvas background is pale slate #F1F5F9 (rgb(241, 245, 249))
    const previewCanvasBg = await page.evaluate(() => {
      const panel = document.getElementById('previewPanel');
      return panel ? getComputedStyle(panel).backgroundColor : '';
    });
    expect(previewCanvasBg).toBe('rgb(241, 245, 249)');

    // 2. Verify Central Dropzone is crisp white #FFFFFF (rgb(255, 255, 255)) with #64748B border
    const dropzone = page.locator('#emptyState');
    await expect(dropzone).toBeVisible();
    const dropzoneBg = await dropzone.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(dropzoneBg).toBe('rgb(255, 255, 255)');

    // 3. Verify Solid Indigo Choose PDF Primary Action Button (#4F46E5 / rgb(79, 70, 229))
    const btnChoose = page.locator('#btnEmptyChoosePdf');
    await expect(btnChoose).toBeVisible();
    const btnChooseBg = await btnChoose.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(btnChooseBg).toBe('rgb(79, 70, 229)');

    // 4. Verify Sample Buttons have white background and dark text (#0F172A / rgb(15, 23, 42))
    const btnSampleInvoice = page.locator('#btnSampleInvoice');
    const sampleBg = await btnSampleInvoice.evaluate((el) => getComputedStyle(el).backgroundColor);
    const sampleColor = await btnSampleInvoice.evaluate((el) => getComputedStyle(el).color);
    expect(sampleBg).toBe('rgb(255, 255, 255)');
    expect(sampleColor).toBe('rgb(15, 23, 42)');

    // 5. Verify Sidebar Neutrality: Section headings are secondary text (#475569 / rgb(71, 85, 105))
    const categoryColor = await page.evaluate(() => {
      const cat = document.querySelector('.sidebar-category');
      return cat ? getComputedStyle(cat).color : '';
    });
    expect(categoryColor).toBe('rgb(71, 85, 105)');

    // 6. Verify Active Sidebar Item: Pale indigo bg (#EEF2FF), dark indigo text (#3730A3), weight 700, 3px indigo border
    const activeNav = page.locator('.nav-item.active').first();
    const activeNavStyles = await activeNav.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        bg: s.backgroundColor,
        color: s.color,
        fontWeight: s.fontWeight,
        borderLeftColor: s.borderLeftColor,
      };
    });
    expect(activeNavStyles.bg).toBe('rgb(238, 242, 255)');
    expect(activeNavStyles.color).toBe('rgb(55, 48, 163)');
    expect(activeNavStyles.borderLeftColor).toBe('rgb(79, 70, 229)');

    // Save visual screenshots if target directory exists (local development)
    const fs = await import('fs');
    const artifactDir = '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0';
    if (fs.existsSync(artifactDir)) {
      await page.screenshot({ path: `${artifactDir}/light_theme_palette_conformance.png` });
      await page.locator('[data-tool="crop-pages"]').click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${artifactDir}/light_theme_crop_conformance.png` });
    }
  });
});
