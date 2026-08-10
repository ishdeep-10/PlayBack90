import { existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import process from "node:process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { createClerkClient } from "@clerk/backend";
import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { chromium } from "playwright-core";

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const suffix = `${Date.now()}`;
const email = `analyst+clerk_test_${suffix}@example.com`;
const password = "PB90Demo!q7V3L9x2";
const baseUrl = process.env.PB90_DEMO_URL || "https://playback90.com";
const chromePath = process.env.PB90_CHROME_PATH
  || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const videoDir = process.env.PB90_DEMO_VIDEO_DIR
  || join(tmpdir(), `playback90-signup-demo-${suffix}`);
const repositoryEnv = fileURLToPath(new URL("../../../.env", import.meta.url));

mkdirSync(videoDir, { recursive: true });
if (!process.env.CLERK_SECRET_KEY && existsSync(repositoryEnv)) process.loadEnvFile(repositoryEnv);
await clerkSetup({ dotenv: true });

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--hide-scrollbars"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 810 },
  recordVideo: { dir: videoDir, size: { width: 1440, height: 810 } },
  userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
});
const page = await context.newPage();
await setupClerkTestingToken({ page });

async function installDemoLayer() {
  await page.evaluate(() => {
    document.getElementById("pb90-demo-layer")?.remove();
    const layer = document.createElement("div");
    layer.id = "pb90-demo-layer";
    layer.innerHTML = '<div id="pb90-demo-caption"></div><div id="pb90-demo-cursor"></div>';
    const style = document.createElement("style");
    style.textContent = `
      #pb90-demo-layer { position: fixed; inset: 0; z-index: 2147483647; pointer-events: none; font-family: Inter, Arial, sans-serif; }
      #pb90-demo-caption { position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(16px); opacity: 0; padding: 13px 22px; color: #f8fafc; background: rgba(3,17,30,.88); border: 1px solid rgba(163,230,53,.32); border-radius: 999px; box-shadow: 0 16px 45px rgba(0,0,0,.34); font-size: 21px; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; transition: opacity .32s ease, transform .32s ease; backdrop-filter: blur(12px); }
      #pb90-demo-caption.show { opacity: 1; transform: translateX(-50%) translateY(0); }
      #pb90-demo-cursor { position: absolute; left: 50%; top: 50%; width: 22px; height: 22px; margin: -11px 0 0 -11px; border: 2px solid #b7ff2a; border-radius: 50%; background: rgba(183,255,42,.18); box-shadow: 0 0 0 5px rgba(183,255,42,.08), 0 4px 16px rgba(0,0,0,.35); transition: left .42s cubic-bezier(.2,.8,.2,1), top .42s cubic-bezier(.2,.8,.2,1), transform .14s ease; }
      #pb90-demo-cursor.click { transform: scale(.72); }
    `;
    layer.appendChild(style);
    document.documentElement.appendChild(layer);
    for (const element of document.querySelectorAll("*")) {
      if (element.children.length === 0 && element.textContent?.trim() === "Development mode") {
        element.style.visibility = "hidden";
      }
    }
  });
}

async function caption(text) {
  await page.evaluate((value) => {
    const node = document.getElementById("pb90-demo-caption");
    if (!node) return;
    node.textContent = value;
    node.classList.toggle("show", Boolean(value));
  }, text);
}

async function moveCursor(selector) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw new Error(`No bounding box for ${selector}`);
  await page.evaluate(({ x, y }) => {
    const cursor = document.getElementById("pb90-demo-cursor");
    if (!cursor) return;
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  await sleep(520);
}

async function click(selector) {
  await moveCursor(selector);
  await page.evaluate(() => document.getElementById("pb90-demo-cursor")?.classList.add("click"));
  await page.locator(selector).first().click();
  await sleep(150);
  await page.evaluate(() => document.getElementById("pb90-demo-cursor")?.classList.remove("click"));
  await sleep(220);
}

async function domClick(selector) {
  await moveCursor(selector);
  await page.evaluate(() => document.getElementById("pb90-demo-cursor")?.classList.add("click"));
  await page.locator(selector).first().evaluate((element) => element.click());
  await sleep(150);
}

async function smoothScrollTo(selector, durationMilliseconds = 8000) {
  const target = await page.locator(selector).evaluate(
    (element) => element.getBoundingClientRect().top + window.scrollY,
  );
  const start = await page.evaluate(() => window.scrollY);
  const steps = Math.max(1, Math.round(durationMilliseconds / 55));
  for (let index = 1; index <= steps; index += 1) {
    const progress = index / steps;
    const eased = progress < 0.5
      ? 2 * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 2) / 2;
    await page.evaluate((y) => window.scrollTo(0, y), start + (target - start) * eased);
    await sleep(55);
  }
}

let video;
let succeeded = false;
try {
  await page.goto(`${baseUrl}/sign-up`, { waitUntil: "networkidle", timeout: 90000 });
  await page.locator("input[name=emailAddress]").waitFor({ timeout: 30000 });
  video = page.video();
  await installDemoLayer();

  await caption("Create your PlayBack90 account");
  await sleep(1900);
  await caption("Use email or continue with Google");
  await click("input[name=emailAddress]");
  await page.locator("input[name=emailAddress]").pressSequentially(email, { delay: 34 });
  await sleep(450);
  await click("input[name=password]");
  await page.locator("input[name=password]").pressSequentially(password, { delay: 42 });
  await sleep(650);
  await click(".cl-formButtonPrimary");

  await page.waitForURL("**/sign-up/verify-email-address", { timeout: 30000 });
  await page.locator("input").first().waitFor({ timeout: 30000 });
  await caption("Verify your email securely");
  await click("input");
  await page.keyboard.type("424242", { delay: 125 });

  await page.waitForFunction(
    () => location.pathname === "/" || document.body.innerText.includes("Football, translated"),
    null,
    { timeout: 60000 },
  );
  await sleep(2500);
  await installDemoLayer();
  await caption("You're in — explore or import a match");
  await sleep(1800);

  await domClick('a.nav-link[href="/live-scrape"]');
  await page.waitForURL("**/live-scrape", { timeout: 30000 });
  await page.getByRole("tablist", { name: "Import source" }).waitFor({ timeout: 30000 });
  await installDemoLayer();
  await caption("Import WhoScored, Wyscout or StatsBomb data");
  await sleep(1600);
  await click('button:has-text("Wyscout JSON")');
  await sleep(1200);
  await click('button:has-text("StatsBomb JSON")');
  await sleep(1700);

  await domClick('a.nav-link[href="/"]');
  await page.waitForURL(`${baseUrl}/`, { timeout: 30000 });
  await page.locator("#league-coverage").waitFor({ state: "attached", timeout: 30000 });
  await sleep(1800);
  await installDemoLayer();
  await caption("Scroll through the PlayBack90 match journey");
  await smoothScrollTo("#league-coverage", 8500);
  await sleep(900);
  await caption("Choose a league");
  const premierLeague = 'a.coverage-logo-chip[aria-label^="Premier League"]';
  await page.locator(premierLeague).scrollIntoViewIfNeeded();
  await click(premierLeague);

  await page.waitForURL("**/matches/premier-league/**", { timeout: 90000 });
  const previousSeason = "nav.season-switcher a.season-pill:not(.is-active)";
  await page.locator(previousSeason).waitFor({ timeout: 30000 });
  await caption("Choose a completed season");
  await click(previousSeason);
  await page.waitForURL("**/matches/premier-league/2025_2026**", { timeout: 90000 });
  await page.getByRole("navigation", { name: "Fixture state" }).waitFor({ timeout: 30000 });
  await installDemoLayer();
  await caption("Browse completed matches");
  await click('nav[aria-label="Fixture state"] a[href*="state=completed"]');
  await page.waitForURL("**state=completed**", { timeout: 90000 });
  await page.locator(".explorer-fixture-select").first().waitFor({ timeout: 90000 });
  await sleep(2200);
  await installDemoLayer();
  await caption("Select a fixture");
  const palaceArsenal = page.getByRole("button", { name: "Preview Crystal Palace versus Arsenal" });
  const fixture = await palaceArsenal.count()
    ? '[aria-label="Preview Crystal Palace versus Arsenal"]'
    : ".explorer-fixture-select";
  await click(fixture);
  await page.locator(".matchday-map-preview-link").waitFor({ timeout: 10000 });
  await sleep(1300);
  await caption("Open the complete match analysis");
  await click(".matchday-map-preview-link");

  await page.waitForURL("**/analysis/**", { timeout: 90000 });
  await page.waitForFunction(() => document.body.innerText.includes("xG Flow"), null, { timeout: 90000 });
  const xgFlow = page.getByText("xG Flow", { exact: true }).first();
  await xgFlow.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -120));
  await sleep(1800);
  await installDemoLayer();
  await caption("Your match insights are ready to explore");
  await sleep(2800);
  await caption("See the match beyond the scoreline");
  await sleep(2400);
  await caption("");
  await sleep(400);
  succeeded = true;
} catch (error) {
  await page.screenshot({ path: join(videoDir, "failure.png") });
  console.error(error);
  process.exitCode = 1;
} finally {
  await context.close();
  const videoPath = video ? await video.path() : null;
  await browser.close();

  try {
    const clerk = createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY });
    const users = await clerk.users.getUserList({ emailAddress: [email] });
    await Promise.all(users.data.map((user) => clerk.users.deleteUser(user.id)));
  } catch (error) {
    console.warn(`Could not delete disposable test account ${email}:`, error);
  }

  console.log(JSON.stringify({ succeeded, videoPath }));
}
