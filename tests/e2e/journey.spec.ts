import { expect, test } from "@playwright/test";
import { login, logout, report, waitForMatch } from "./helpers";

// Whole product story in a browser: report -> automatic match with explanation -> claim -> staff verification -> returned.
test("lost report is matched, claimed, verified by staff and returned", async ({ page }) => {
  const tag = `zephyr${Date.now() % 100000}`;                       // a unique word so only this pair can match
  const desc = `turquoise ${tag} skateboard with a ${tag} sticker and the initials Q.Z. written underneath`;

  await login(page, "alice@lostfound.dev");
  const lostId = await report(page, "lost", `Lost ${tag} skateboard`, desc);
  await logout(page);

  await login(page, "bob@lostfound.dev");
  const foundId = await report(page, "found", `Found ${tag} skateboard`, `Found a turquoise ${tag} skateboard, ${tag} sticker, initials Q.Z. on the bottom`);
  await logout(page);

  // Alice sees the suggestion and the arithmetic behind it
  await login(page, "alice@lostfound.dev");
  await waitForMatch(page, lostId, `Found ${tag} skateboard`);
  const card = page.locator("li", { hasText: `Found ${tag} skateboard` });
  await card.getByRole("button", { name: "Why this match?" }).click();
  await expect(page.getByText(/RRF = 1\/\(60\+1\)/)).toBeVisible();
  await expect(page.getByText("Text similarity")).toBeVisible();

  // ...and claims the found item
  await card.getByRole("button", { name: "This is mine: claim it" }).click();
  await expect(page).toHaveURL(new RegExp(`/items/${foundId}`));
  // "claim it" on a match opens the claim dialog with the match pre-linked
  await page.getByLabel("Proof of ownership").fill("The initials Q.Z. are written underneath and the sticker is a tiny sun.");
  await page.getByRole("button", { name: "Submit claim" }).click();
  await expect(page.getByText("Your claim", { exact: true })).toBeVisible();
  await logout(page);

  // Staff verify and approve
  await login(page, "staff@lostfound.dev");
  await page.goto("/staff/claims");
  await page.getByRole("link", { name: new RegExp(`Found ${tag} skateboard`) }).click();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved").first()).toBeVisible();

  await page.goto(`/items/${foundId}`);
  await expect(page.getByText("Claimed").first()).toBeVisible();
  await page.getByRole("button", { name: "Mark returned" }).click();
  await expect(page.getByText("Returned").first()).toBeVisible();

  // The audit trail has the whole story
  await page.goto("/staff/audit");
  await page.getByLabel("Row id").fill(String(foundId));
  await expect(page.getByRole("cell", { name: /status: "claimed" → "returned"|status: "open"/ }).first()).toBeVisible();
});
