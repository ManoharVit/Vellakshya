const { test, expect } = require('@playwright/test');

test.describe('Milestone 1: Analytics & Summarizer E2E', () => {
  test('should open Document Analytics in Light Theme, analyze custom text and render statistical cards', async ({ page }) => {
    await page.goto('http://127.0.0.1:8000');
    await page.waitForLoadState('networkidle');

    // Ensure Light theme is active
    const html = page.locator('html');
    const currentTheme = await html.getAttribute('data-theme');
    if (currentTheme !== 'light') {
      await page.click('#btnThemeToggle');
      await expect(html).toHaveAttribute('data-theme', 'light');
    }

    // Click Document Analytics nav item
    const analyticsNav = page.locator('.nav-item[data-tool="analytics"]');
    await expect(analyticsNav).toBeVisible();
    await analyticsNav.click();

    // Verify tool title
    await expect(page.locator('#currentToolTitle')).toContainText('Document Analytics');

    // Enter custom text for analysis
    const sampleText = `
      The board of directors approved the enterprise cybersecurity initiative on 2026-03-15.
      All engineering departments decided to adopt local-first encryption protocols to protect sensitive records.
      The security operations team shall implement multi-factor authentication across all gateways by 2026-06-30.
      Failure to enforce these controls introduces severe regulatory liability and legal penalties under GDPR.
    `;
    await page.fill('#analyticsCustomText', sampleText);

    // Click Compute Document Profile button
    await page.click('#btnRunAnalytics');

    // Wait for results container
    const results = page.locator('#analyticsResultsContainer');
    await expect(results).toBeVisible();
    await expect(results).toContainText('Statistical Overview');
    await expect(results).toContainText('Readability Score');
    await expect(results).toContainText('Top Filtered Keywords');

    // Take screenshot of analytics panel in light mode
    await page.screenshot({
      path: '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0/analytics_tool_light_e2e.png',
      fullPage: false,
    });
  });

  test('should open Smart Summarizer, summarize sample report and render insights in Light Theme', async ({ page }) => {
    await page.goto('http://127.0.0.1:8000');
    await page.waitForLoadState('networkidle');

    // Ensure Light theme is active
    const html = page.locator('html');
    const currentTheme = await html.getAttribute('data-theme');
    if (currentTheme !== 'light') {
      await page.click('#btnThemeToggle');
      await expect(html).toHaveAttribute('data-theme', 'light');
    }

    // Load sample report PDF
    const btnSampleReport = page.locator('#btnSampleReport');
    if (await btnSampleReport.isVisible()) {
      await btnSampleReport.click();
      await page.waitForTimeout(600);
    }

    // Click Smart Summarizer nav item
    const summarizerNav = page.locator('.nav-item[data-tool="summarizer"]');
    await expect(summarizerNav).toBeVisible();
    await summarizerNav.click();

    // Verify tool title
    await expect(page.locator('#currentToolTitle')).toContainText('Smart Summarizer');

    // Verify controls
    await expect(page.locator('#sumLevel')).toBeVisible();
    await expect(page.locator('#sumLength')).toBeVisible();
    await expect(page.locator('#sumTone')).toBeVisible();
    await expect(page.locator('#sumFormat')).toBeVisible();
    await expect(page.locator('#sumAllowCloudAi')).not.toBeChecked();

    // Select Structured Report output
    await page.selectOption('#sumFormat', 'structured_report');

    // Generate Smart Summary
    await page.click('#btnRunSummarizer');

    // Wait for results
    const results = page.locator('#summarizerResultsContainer');
    await expect(results).toBeVisible();
    await expect(results).toContainText('Generated Summary');
    await expect(results).toContainText('Executive Report');

    await results.scrollIntoViewIfNeeded();

    // Take screenshot of summarizer results in light mode
    await page.screenshot({
      path: '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0/summarizer_results_light_e2e.png',
      fullPage: false,
    });
  });
});
