// @ts-check
import { test, expect } from '@playwright/test';

test('Random Hours homepage renders its key sections', async ({ page }, testInfo) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Random Hours/);
  await expect(page.getByRole('heading', { name: /Stories told in frames/i })).toBeVisible();
  await expect(page.locator('#work')).toBeAttached();
  await expect(page.locator('#editing')).toBeAttached();
  await expect(page.locator('#about')).toBeAttached();
  await expect(page.locator('#contact')).toBeAttached();

  const screenshotName = testInfo.project.name === 'mobile-chromium' ? 'mobile.png' : 'desktop.png';
  await page.screenshot({ path: `test-results/screenshots/${screenshotName}`, fullPage: true });
});

test('primary navigation links point to existing sections', async ({ page }) => {
  await page.goto('/');
  for (const section of ['work', 'editing', 'about', 'contact']) {
    await expect(page.locator(`#primary-navigation a[href="#${section}"]`)).toHaveCount(1);
    await expect(page.locator(`#${section}`)).toHaveCount(1);
  }
});

test('mobile navigation opens and closes', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Mobile-only interaction test');
  await page.goto('/');
  const menu = page.getByRole('button', { name: /menu/i });
  const navigation = page.locator('#primary-navigation');

  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(navigation.getByRole('link', { name: 'Work' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Work' }).click();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
});
