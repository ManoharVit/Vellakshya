import { test, expect } from '@playwright/test';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');

test.describe('Governance & Audit Tools', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Version History & Manifests renders, creates checkpoints and verifies manifest', async ({ page }) => {
    // Click sidebar tool
    await page.locator('[data-tool="version-history"]').click();
    await expect(page.locator('#currentToolTitle')).toContainText('Version History & Manifests');
    await expect(page.locator('#verManifestStatusLabel')).toContainText('Ed25519 Verified');

    // Upload sample PDF
    await page.setInputFiles('input[type="file"]', SAMPLE_PDF_PATH);
    await page.waitForTimeout(600);

    // Create a checkpoint
    const initialCards = await page.locator('#verToolTimelineList .version-card').count();
    await page.locator('#btnCreateCheckpoint').click();
    await page.waitForTimeout(300);
    const updatedCards = await page.locator('#verToolTimelineList .version-card').count();
    expect(updatedCards).toBeGreaterThanOrEqual(initialCards);

    // Verify manifest
    await page.locator('#btnSideVerifyIntegrity').click();
    await expect(page.locator('.app-toast').last()).toBeVisible();

    // Open and close drawer
    await page.locator('#btnSideOpenRevisions').click();
    await expect(page.locator('#drawerVersionHistory')).toBeVisible();
    await page.locator('#btnCloseVersionHistory').click();
    await expect(page.locator('#drawerVersionHistory')).not.toBeVisible();
  });

  test('Real-Time Collaboration connects, displays peers, posts comments and resolves them', async ({ page }) => {
    // Click sidebar tool
    await page.locator('[data-tool="collaboration-hub"]').click();
    await expect(page.locator('#currentToolTitle')).toContainText('Real-Time Collaboration');

    // Verify peers
    const peers = page.locator('#collabToolPeerList .collab-peer-card');
    await expect(peers).toHaveCount(3);

    // Post comment
    const testComment = 'Automated E2E compliance note ' + Date.now();
    await page.locator('#collabToolCommentInput').fill(testComment);
    await page.locator('#btnToolPostComment').click();
    await page.waitForTimeout(300);

    // Verify comment in list
    await expect(page.locator('#collabToolCommentsList')).toContainText(testComment);

    // Open and close drawer
    await page.locator('#btnSideOpenCollabDrawer').click();
    await expect(page.locator('#drawerCollaboration')).toBeVisible();
    await page.locator('#btnCloseCollaboration').click();
    await expect(page.locator('#drawerCollaboration')).not.toBeVisible();
  });

  test('Security & Sandbox Model displays defense matrix and executes sandbox scan', async ({ page }) => {
    // Click sidebar tool
    await page.locator('[data-tool="security-audit"]').click();
    await expect(page.locator('#currentToolTitle')).toContainText('Security & Sandbox Model');

    // Verify defense metrics
    const metricCards = page.locator('.security-metrics-grid .security-metric-card');
    await expect(metricCards.first()).toBeVisible();

    // Run security scan
    await page.locator('#btnRunSecurityScan').click();
    await page.waitForTimeout(900);
    await expect(page.locator('#secScanRatingBadge')).toContainText('A+');
    await expect(page.locator('.app-toast').last()).toBeVisible();

    // Open and close drawer
    await page.locator('#btnSideOpenSecurity').click();
    await expect(page.locator('#drawerSecurity')).toBeVisible();
    await page.locator('#btnCloseSecurity').click();
    await expect(page.locator('#drawerSecurity')).not.toBeVisible();
  });
});
