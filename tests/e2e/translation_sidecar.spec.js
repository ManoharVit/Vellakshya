// @ts-check
const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.TEST_URL || "http://127.0.0.1:8000";

test.describe("Milestone 3: Translation & Multi-Format Ingestion E2E", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState("networkidle");
    // Force light theme for consistent UI assertions
    await page.evaluate(() => {
      localStorage.setItem("vellakshya_theme", "light");
      document.documentElement.setAttribute("data-theme", "light");
      document.body.classList.remove("theme-dark");
      document.body.classList.add("theme-light");
    });
  });

  test("should open Translation tool from sidebar and display controls", async ({ page }) => {
    // Open Translation tool
    const translateNav = page.locator('.nav-item[data-tool="translate"]');
    await expect(translateNav).toBeVisible();
    await translateNav.click();

    // Verify tool panel title & sections
    const headerTitle = page.locator("#currentToolTitle");
    await expect(headerTitle).toContainText("Translation");

    const srcLang = page.locator("#translateSourceLang");
    await expect(srcLang).toBeVisible();

    const tgtLang = page.locator("#translateTargetLang");
    await expect(tgtLang).toBeVisible();

    const domainSelect = page.locator("#translateDomain");
    await expect(domainSelect).toBeVisible();

    const privacyCheck = page.locator("#translateLocalFirst");
    await expect(privacyCheck).toBeVisible();
    await expect(privacyCheck).toBeChecked();

    const runBtn = page.locator("#btnRunTranslation");
    await expect(runBtn).toBeVisible();
  });

  test("should translate custom text and display side-by-side bilingual view", async ({ page }) => {
    // Open Translation tool
    await page.locator('.nav-item[data-tool="translate"]').click();

    // Select custom text scope via visible parent label
    const customScopeLabel = page.locator('label.scope-radio-btn:has(input[value="selection"])');
    await customScopeLabel.click();

    // Enter custom text
    const customText = page.locator("#translateCustomText");
    await expect(customText).toBeVisible();
    await customText.fill("Annual Compliance Report\nKey Controls and Force Majeure governing law.");

    // Select legal domain
    await page.selectOption("#translateDomain", "legal");
    // Select Spanish target
    await page.selectOption("#translateTargetLang", "es");

    // Click Translate button
    const runBtn = page.locator("#btnRunTranslation");
    await runBtn.click();

    // Assert bilingual canvas container appears
    const bilingualCanvas = page.locator("#bilingualCanvasContainer");
    await expect(bilingualCanvas).toBeVisible({ timeout: 10000 });

    // Check domain badge
    const domainBadge = page.locator("#bilingualDomainBadge");
    await expect(domainBadge).toContainText("LEGAL");

    // Check language pair
    const langPair = page.locator("#bilingualLangPair");
    await expect(langPair).toContainText("Spanish");

    // Check segments exist on both source and target sides
    const srcSegs = page.locator("#bilingualSourceSegments .bilingual-segment");
    const tgtSegs = page.locator("#bilingualTargetSegments .bilingual-segment");

    await expect(srcSegs).toHaveCount(2);
    await expect(tgtSegs).toHaveCount(2);

    // Verify hover pairing
    await srcSegs.first().hover();
    await expect(tgtSegs.first()).toHaveClass(/seg-hover/);

    // Check Sync Scroll button
    const syncBtn = page.locator("#btnToggleScrollSync");
    await expect(syncBtn).toContainText("Sync Scroll: ON");
    await syncBtn.click();
    await expect(syncBtn).toContainText("Sync Scroll: OFF");

    // Capture screenshot for visual audit
    await page.screenshot({
      path: "/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0/bilingual_translation_canvas_e2e.png",
      fullPage: false,
    });
  });

  test("should ingest multi-format Markdown document and load into workspace", async ({ page }) => {
    // Inject multi-format file via fetch and client ingest handler
    const ingestResult = await page.evaluate(async () => {
      const mdContent = "# SOC 2 Cloud Audit\n\nAutomated encryption and zero-trust controls.\n\n| Item | Pass |\n|---|---|\n| IAM | Yes |";
      const blob = new Blob([mdContent], { type: "text/markdown" });
      const file = new File([blob], "audit_spec.md", { type: "text/markdown" });
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/ai/ingest-multi-format?allow_external_ai=false", {
        method: "POST",
        body: formData,
      });
      return await res.json();
    });

    expect(ingestResult.status).toBe("success");
    expect(ingestResult.detected_format).toBe("MARKDOWN");
    expect(ingestResult.page_count).toBeGreaterThanOrEqual(1);

    // Now test downloading the synthesized PDF and loading into workspace
    await page.evaluate(async (url) => {
      const res = await fetch(url);
      const blob = await res.blob();
      const pdfFile = new File([blob], "audit_spec.pdf", { type: "application/pdf" });
      // @ts-ignore
      window.setActivePdf(pdfFile);
    }, ingestResult.pdf_url);

    await page.waitForTimeout(1000);

    // Verify preview canvas active
    const previewContainer = page.locator("#previewContainer");
    await expect(previewContainer).toBeVisible();

    const previewDocName = page.locator("#previewDocName");
    await expect(previewDocName).toContainText("audit_spec.pdf");
  });
});
