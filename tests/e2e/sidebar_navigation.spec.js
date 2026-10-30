const { test, expect } = require('@playwright/test');

test.describe('Sidebar Hide/Show and Section Dropdown Accordions', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage to start with clean state
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState('networkidle');
  });

  test('Sidebar expands and collapses via toggle button, collapse button, and restore button', async ({ page }) => {
    const sidebar = page.locator('#sidebarNav');
    const toggleBtn = page.locator('#btnToggleSidebar');
    const collapseBtn = page.locator('#btnCollapseSidebar');
    const restoreBtn = page.locator('#btnRestoreSidebar');

    // Initially sidebar is visible and expanded
    await expect(sidebar).toBeVisible();
    await expect(sidebar).not.toHaveClass(/collapsed/);
    await expect(restoreBtn).toBeHidden();

    // 1. Collapse via header toggle button
    await toggleBtn.click();
    await expect(sidebar).toHaveClass(/collapsed/);
    await expect(sidebar).toBeHidden();
    await expect(restoreBtn).toBeVisible();

    // 2. Restore via workspace header restore button
    await restoreBtn.click();
    await expect(sidebar).toBeVisible();
    await expect(sidebar).not.toHaveClass(/collapsed/);
    await expect(restoreBtn).toBeHidden();

    // 3. Collapse via sidebar search collapse chevron button
    await collapseBtn.click();
    await expect(sidebar).toHaveClass(/collapsed/);
    await expect(sidebar).toBeHidden();
    await expect(restoreBtn).toBeVisible();

    // 4. Restore via header toggle button
    await toggleBtn.click();
    await expect(sidebar).toBeVisible();
    await expect(sidebar).not.toHaveClass(/collapsed/);
    await expect(restoreBtn).toBeHidden();
  });

  test('Sidebar toggles via Ctrl+B / Cmd+B keyboard shortcut', async ({ page }) => {
    const sidebar = page.locator('#sidebarNav');
    const restoreBtn = page.locator('#btnRestoreSidebar');

    await expect(sidebar).toBeVisible();

    // Press Control+B to collapse
    await page.keyboard.press('Control+b');
    await expect(sidebar).toHaveClass(/collapsed/);
    await expect(sidebar).toBeHidden();
    await expect(restoreBtn).toBeVisible();

    // Press Control+B to expand
    await page.keyboard.press('Control+b');
    await expect(sidebar).toBeVisible();
    await expect(sidebar).not.toHaveClass(/collapsed/);
    await expect(restoreBtn).toBeHidden();
  });

  test('Sidebar state persists across page reload in localStorage', async ({ page }) => {
    const sidebar = page.locator('#sidebarNav');
    const toggleBtn = page.locator('#btnToggleSidebar');

    // Collapse sidebar
    await toggleBtn.click();
    await expect(sidebar).toHaveClass(/collapsed/);

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should remain collapsed
    await expect(page.locator('#sidebarNav')).toHaveClass(/collapsed/);
    await expect(page.locator('#sidebarNav')).toBeHidden();
    await expect(page.locator('#btnRestoreSidebar')).toBeVisible();
  });

  test('Each section acts as an accordion dropdown with chevron rotation', async ({ page }) => {
    const categories = page.locator('.sidebar-category');
    const count = await categories.count();
    expect(count).toBe(7);

    // Test first category: "Core Engine"
    const coreEngine = categories.first();
    const coreNav = page.locator('#sidebarNav .sidebar-nav').first();

    await expect(coreEngine).toHaveAttribute('aria-expanded', 'true');
    await expect(coreNav).toBeVisible();
    await expect(coreNav).not.toHaveClass(/collapsed/);

    // Click to collapse
    await coreEngine.click();
    await expect(coreEngine).toHaveClass(/collapsed/);
    await expect(coreEngine).toHaveAttribute('aria-expanded', 'false');
    await expect(coreNav).toHaveClass(/collapsed/);
    await expect(coreNav).toBeHidden();

    // Click again to expand
    await coreEngine.click();
    await expect(coreEngine).not.toHaveClass(/collapsed/);
    await expect(coreEngine).toHaveAttribute('aria-expanded', 'true');
    await expect(coreNav).toBeVisible();
    await expect(coreNav).not.toHaveClass(/collapsed/);

    // Test keyboard accessibility: Enter key on 2nd category ("Organize Pages")
    const orgPages = categories.nth(1);
    const orgNav = page.locator('#sidebarNav .sidebar-nav').nth(1);

    await orgPages.focus();
    await page.keyboard.press('Enter');
    await expect(orgPages).toHaveClass(/collapsed/);
    await expect(orgPages).toHaveAttribute('aria-expanded', 'false');
    await expect(orgNav).toBeHidden();

    // Space key to re-expand
    await page.keyboard.press('Space');
    await expect(orgPages).not.toHaveClass(/collapsed/);
    await expect(orgPages).toHaveAttribute('aria-expanded', 'true');
    await expect(orgNav).toBeVisible();
  });

  test('Tool search automatically expands collapsed sections when tools match', async ({ page }) => {
    const categories = page.locator('.sidebar-category');
    const orgPages = categories.nth(1);
    const orgNav = page.locator('#sidebarNav .sidebar-nav').nth(1);

    // Collapse Organize Pages
    await orgPages.click();
    await expect(orgPages).toHaveClass(/collapsed/);
    await expect(orgNav).toBeHidden();

    // Search for "Split" which is inside Organize Pages
    const searchInput = page.locator('#sidebarToolSearch');
    await searchInput.fill('Split');

    // Category should auto-expand so the matching tool item is displayed
    await expect(orgPages).not.toHaveClass(/collapsed/);
    await expect(orgPages).toHaveAttribute('aria-expanded', 'true');
    await expect(orgNav).not.toHaveClass(/collapsed/);
    await expect(orgNav).toBeVisible();

    const splitItem = orgNav.locator('.nav-item[data-tool="split-pdf"]');
    await expect(splitItem).toBeVisible();
  });

  test('Capture visual screenshots of expanded and collapsed sidebar', async ({ page }) => {
    // 1. Expanded sidebar with 2nd section collapsed to show chevron rotation
    const categories = page.locator('.sidebar-category');
    await categories.nth(1).click(); // Collapse Organize Pages
    await page.waitForTimeout(300);

    const artifactDir = '/Users/girimanoharv/.gemini/antigravity/brain/0e08655c-3da7-43d3-a0d8-178d85741da0';
    await page.screenshot({ path: `${artifactDir}/sidebar_dropdown_accordions_e2e.png` });

    // 2. Collapsed sidebar mode
    const toggleBtn = page.locator('#btnToggleSidebar');
    await toggleBtn.click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${artifactDir}/sidebar_collapsed_mode_e2e.png` });
  });
});
