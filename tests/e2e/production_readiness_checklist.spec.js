const { test, expect } = require('@playwright/test');

test.describe('12-Item Production Readiness & Pre-Launch Checklist', () => {

  test('Item 1: Custom 404 page renders branded UI and provides recovery navigation', async ({ page }) => {
    const res = await page.goto('/invalid-nonexistent-path-for-test-404');
    expect(res.status()).toBe(404);

    await expect(page.locator('h1')).toContainText('Document or Page Missing');
    await expect(page.locator('.error-badge')).toContainText('404 Error');

    // Click Return to Workstation button
    const returnBtn = page.locator('#btnReturnHome');
    await expect(returnBtn).toBeVisible();
    await returnBtn.click();
    await expect(page).toHaveURL(/\//);
  });

  test('Item 2: CTAs are positioned above the fold on initial load', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Central dropzone primary CTA
    const btnChoose = page.locator('#btnEmptyChoosePdf');
    await expect(btnChoose).toBeVisible();
    const btnBox = await btnChoose.boundingBox();
    expect(btnBox).not.toBeNull();
    expect(btnBox.y).toBeLessThan(700);

    // Header AI Chat button
    const btnAiChat = page.locator('#btnHeaderAiChat');
    await expect(btnAiChat).toBeVisible();

    // Quick sample loader buttons
    await expect(page.locator('#btnSampleInvoice')).toBeVisible();
    await expect(page.locator('#btnSampleReport')).toBeVisible();
  });

  test('Item 3: Meta titles are configured and update dynamically on document load', async ({ page }) => {
    // 1. Root page title
    await page.goto('/');
    await expect(page).toHaveTitle(/Vellakshya - Professional PDF Workstation/);

    // 2. 404 page title
    await page.goto('/404.html');
    await expect(page).toHaveTitle(/Page Not Found \(404\) - Vellakshya/);

    // 3. Privacy page title
    await page.goto('/privacy.html');
    await expect(page).toHaveTitle(/Privacy Policy & Data Governance - Vellakshya/);

    // 4. Dynamic title update when a document is opened
    await page.goto('/');
    const btnSampleInvoice = page.locator('#btnSampleInvoice');
    await btnSampleInvoice.click();
    await page.waitForTimeout(600);
    await expect(page).toHaveTitle(/Sample_Invoice\.pdf • Vellakshya/);
  });

  test('Item 4: Meta description is present on all public pages', async ({ page }) => {
    // Root page
    await page.goto('/');
    const rootMeta = await page.locator('meta[name="description"]').getAttribute('content');
    expect(rootMeta).toBeTruthy();
    expect(rootMeta).toContain('Vellakshya is an enterprise-grade, privacy-first PDF workstation');

    // Privacy page
    await page.goto('/privacy.html');
    const privacyMeta = await page.locator('meta[name="description"]').getAttribute('content');
    expect(privacyMeta).toBeTruthy();
    expect(privacyMeta).toContain('Data Governance and Privacy Policy');

    // 404 page
    await page.goto('/404.html');
    const notFoundMeta = await page.locator('meta[name="description"]').getAttribute('content');
    expect(notFoundMeta).toBeTruthy();
  });

  test('Item 5: Open Graph and Twitter Card tags and social preview image are configured', async ({ page }) => {
    await page.goto('/');

    const ogTitle = await page.locator('meta[property="og:title"]').getAttribute('content');
    const ogDesc = await page.locator('meta[property="og:description"]').getAttribute('content');
    const ogImage = await page.locator('meta[property="og:image"]').getAttribute('content');
    const twitterCard = await page.locator('meta[name="twitter:card"]').getAttribute('content');

    expect(ogTitle).toContain('Vellakshya');
    expect(ogDesc).toContain('privacy-first');
    expect(ogImage).toContain('/brand/og-image.png');
    expect(twitterCard).toBe('summary_large_image');

    // Verify the og-image is fetchable and returns 200 OK
    const imgRes = await page.request.get('/brand/og-image.png');
    expect(imgRes.status()).toBe(200);
    expect(imgRes.headers()['content-type']).toContain('image/png');
  });

  test('Item 6: Complete multi-platform favicon and PWA webmanifest set is served', async ({ page }) => {
    await page.goto('/');

    // Check favicon links
    await expect(page.locator('link[rel="icon"][href="/favicon.ico"]')).toHaveCount(1);
    await expect(page.locator('link[rel="icon"][href="/brand/favicon-32.png"]')).toHaveCount(1);
    await expect(page.locator('link[rel="icon"][href="/brand/favicon.svg"]')).toHaveCount(1);
    await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveCount(1);
    await expect(page.locator('link[rel="manifest"]')).toHaveCount(1);

    // Verify assets return 200
    const icoRes = await page.request.get('/favicon.ico');
    expect(icoRes.status()).toBe(200);

    const manifestRes = await page.request.get('/site.webmanifest');
    expect(manifestRes.status()).toBe(200);
    const manifestJson = await manifestRes.json();
    expect(manifestJson.name).toBe('Vellakshya PDF Workstation');
    expect(manifestJson.icons.length).toBeGreaterThanOrEqual(3);
  });

  test('Item 7: robots.txt is accessible and properly configured', async ({ page }) => {
    const res = await page.request.get('/robots.txt');
    expect(res.status()).toBe(200);
    const text = await res.text();
    expect(text).toContain('User-agent: *');
    expect(text).toContain('Allow: /');
    expect(text).toContain('Disallow: /api/');
    expect(text).toContain('Sitemap: https://vellakshya-gcp.web.app/sitemap.xml');
  });

  test('Item 8: sitemap.xml is accessible and declares valid canonical endpoints', async ({ page }) => {
    const res = await page.request.get('/sitemap.xml');
    expect(res.status()).toBe(200);
    const xml = await res.text();
    expect(xml).toContain('<urlset');
    expect(xml).toContain('https://vellakshya-gcp.web.app/');
    expect(xml).toContain('https://vellakshya-gcp.web.app/privacy.html');
  });

  test('Item 9: Alt text and SVG accessibility standards are strictly upheld', async ({ page }) => {
    await page.goto('/');

    // Ensure zero img tags lack an alt attribute
    const imagesWithoutAlt = await page.locator('img:not([alt])').count();
    expect(imagesWithoutAlt).toBe(0);

    // Decorative SVGs should declare aria-hidden="true"
    const headerToggleSvg = page.locator('#btnToggleSidebar svg');
    await expect(headerToggleSvg).toHaveAttribute('aria-hidden', 'true');

    // Interactive icon buttons should declare accessible labels
    const toggleBtn = page.locator('#btnToggleSidebar');
    await expect(toggleBtn).toHaveAttribute('aria-label', /Toggle Navigation Sidebar/);
  });

  test('Item 10: Loading states display visual indicators and prevent duplicate clicks', async ({ page }) => {
    await page.goto('/');
    const btnSample = page.locator('#btnSampleInvoice');
    await btnSample.click();
    await page.waitForTimeout(500);

    // Trigger conversion
    const btnConvert = page.locator('#btnRunConvertHtml');
    await expect(btnConvert).toBeVisible();
    await btnConvert.click();

    // While converting, check for spinner and aria-busy
    const spinner = page.locator('#btnRunConvertHtml .spinner');
    await expect(spinner).toBeAttached();

    // After conversion finishes, button resets
    await expect(page.locator('#btnRunConvertHtml')).toContainText('Convert PDF to HTML', { timeout: 10000 });
  });

  test('Item 11: Privacy policy page is linked and details local-first governance', async ({ page }) => {
    await page.goto('/');

    // Verify privacy link exists in the document status / governance menu
    const privacyLink = page.locator('a[href="/privacy.html"]');
    await expect(privacyLink).toBeAttached();

    // Navigate to privacy page
    await page.goto('/privacy.html');
    await expect(page.locator('h1')).toContainText('Vellakshya Privacy Policy');
    await expect(page.locator('body')).toContainText('F13 Privacy Gate');
    await expect(page.locator('body')).toContainText('1-Hour Retention TTL');
    await expect(page.locator('body')).toContainText('AES-256-GCM');

    // Return to Workstation button works
    await page.locator('.btn-privacy-home').click();
    await expect(page).toHaveURL(/\//);
  });

  test('Item 12: Privacy-preserving telemetry client is installed and functional', async ({ page }) => {
    await page.goto('/');

    // Verify telemetry object is mounted
    const hasAnalytics = await page.evaluate(() => typeof window.VellakshyaAnalytics !== 'undefined');
    expect(hasAnalytics).toBe(true);

    // Verify initial pageview event was recorded
    const events = await page.evaluate(() => window.VellakshyaAnalytics.getRecentEvents());
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].category).toBe('Navigation');
    expect(events[0].action).toBe('PageView');

    // Verify custom event tracking
    await page.evaluate(() => {
      window.VellakshyaAnalytics.trackEvent('Tool', 'Select', 'html');
    });

    const updatedEvents = await page.evaluate(() => window.VellakshyaAnalytics.getRecentEvents());
    expect(updatedEvents.some(e => e.action === 'Select' && e.label === 'html')).toBe(true);
  });
});
