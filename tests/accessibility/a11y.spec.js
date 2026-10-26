import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'fs';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Automated Accessibility Audits (axe-core + WCAG 2.1 AA)', () => {
  test('single-page editor interface has zero critical WCAG violations', async ({ page }) => {
    await page.goto('/');

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .disableRules(['color-contrast']) // Color contrast evaluated in custom visual suite
      .analyze();

    const criticalViolations = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical'
    );

    expect(criticalViolations).toEqual([]);
  });

  test('converted semantic HTML document conforms to accessibility standards', async ({ request, page }) => {
    // Generate semantic HTML via API
    const fileBuffer = fs.readFileSync(SAMPLE_PDF_PATH);
    const response = await request.post('/api/convert/html', {
      multipart: {
        file: {
          name: 'sample.pdf',
          mimeType: 'application/pdf',
          buffer: fileBuffer,
        },
        mode: 'semantic',
      },
    });
    expect(response.status()).toBe(200);
    const htmlContent = await response.text();

    // Render in browser
    await page.setContent(htmlContent);

    // Analyze with axe-core
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});
