import { expect, test } from "@playwright/test";
import { logout, PASSWORD } from "./helpers";

test("a visitor can sign up, sign out and sign back in; bad credentials are rejected", async ({ page }) => {
  const email = `e2e.${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("E2E Tester").first()).toBeVisible();

  await logout(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrong-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("form [role=alert]")).toContainText(/invalid email or password/i);

  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("E2E Tester").first()).toBeVisible();
});

test("protected pages redirect anonymous visitors to sign in", async ({ page }) => {
  await page.goto("/claims");
  await expect(page).toHaveURL(/\/login\?next=%2Fclaims/);
  await page.goto("/staff/claims");
  await expect(page).toHaveURL(/\/login/);
});
