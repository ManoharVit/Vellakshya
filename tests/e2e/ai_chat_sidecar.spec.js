const { test, expect } = require('@playwright/test');

test.describe('Milestone 2: Streaming RAG & Sidecar Chat E2E', () => {
  test('should open AI Chat drawer, stream Q&A response, display citations, and jump to page on citation click', async ({ page }) => {
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

    // Open AI Chat drawer via top header button
    const btnHeaderAiChat = page.locator('#btnHeaderAiChat');
    await expect(btnHeaderAiChat).toBeVisible();
    await btnHeaderAiChat.click();

    // Verify AI Chat drawer is visible and backdrop is NOT visible (companion sidecar)
    const drawer = page.locator('#drawerAiChat');
    await expect(drawer).toBeVisible();
    await expect(page.locator('#drawerBackdrop')).not.toBeVisible();
    await expect(page.locator('#chatDocPill')).toContainText('Sample_Enterprise_Report.pdf');

    // Type a grounded question
    const inputEl = page.locator('#chatInputText');
    await inputEl.fill('What is the executive summary of this enterprise report?');
    await page.click('#btnChatSend');

    // Verify user message appears in chat
    const userMsg = page.locator('.chat-message.user');
    await expect(userMsg).toBeVisible();
    await expect(userMsg).toContainText('What is the executive summary');

    // Wait for streamed assistant response and citation pill
    const assistantMsg = page.locator('.chat-message.assistant').nth(1);
    await expect(assistantMsg).toBeVisible({ timeout: 10000 });

    // Verify citation pills are rendered
    const citationPill = assistantMsg.locator('.citation-pill').first();
    await expect(citationPill).toBeVisible({ timeout: 10000 });
    await expect(citationPill).toContainText('Page');

    // Click citation pill to trigger page jump
    await citationPill.click();

    // Verify notification toast about navigating to citation
    const toast = page.locator('.app-toast-message');
    await expect(toast).toBeVisible();
    await expect(toast).toContainText('Navigated to verified citation');

    // Capture screenshot of sidecar chat drawer in light mode
    await page.screenshot({
      path: '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0/ai_chat_sidecar_light_e2e.png',
      fullPage: false,
    });
  });

  test('should open AI Chat from sidebar navigation and support prompt chips', async ({ page }) => {
    await page.goto('http://127.0.0.1:8000');
    await page.waitForLoadState('networkidle');

    // Load sample invoice
    const btnSampleInvoice = page.locator('#btnSampleInvoice');
    if (await btnSampleInvoice.isVisible()) {
      await btnSampleInvoice.click();
      await page.waitForTimeout(600);
    }

    // Click "Chat with Document" in sidebar under Intelligence & Analysis
    const navAiChat = page.locator('.nav-item[data-tool="ai-chat"]');
    await expect(navAiChat).toBeVisible();
    await navAiChat.click();

    // Drawer opens automatically without backdrop
    const drawer = page.locator('#drawerAiChat');
    await expect(drawer).toBeVisible();
    await expect(page.locator('#drawerBackdrop')).not.toBeVisible();

    // Click a prompt chip
    const chip = page.locator('.prompt-chip').first();
    await expect(chip).toBeVisible();
    await chip.click();

    // User message should appear
    await expect(page.locator('.chat-message.user')).toBeVisible();

    // Clear chat history
    await page.click('#btnClearChatHistory');
    await expect(page.locator('.chat-message.user')).toHaveCount(0);
    await expect(page.locator('.welcome-msg')).toBeVisible();
  });
});
