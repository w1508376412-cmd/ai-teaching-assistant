// Run against the local FastAPI server with complete() mocked; no paid AI calls.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.CASE_TEST_URL || "http://127.0.0.1:8766";
const output = process.env.CASE_TEST_OUTPUT || "/private/tmp";
const cases = fs.readdirSync(path.join(__dirname, "../cases")).filter(f => f.endsWith(".json")).sort()
  .map(f => JSON.parse(fs.readFileSync(path.join(__dirname, "../cases", f), "utf8")));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 842, height: 749 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  try {
    await page.goto(base + "/#cases");
    await page.waitForSelector("#diseaseOptions input");
    const selectCase = async index => {
      await page.locator("#casePickerTrigger").click();
      await page.locator('[data-case-index="' + index + '"]').click();
    };
    const submit = () => page.locator("#decisionForm button[type=submit]").click();
    const selectValue = (group, value) => page.locator('input[name="' + group + '"]')
      .evaluateAll((inputs, value) => {
        const input = inputs.find(node => node.value === value);
        if (!input || input.disabled) throw new Error("Choice missing or disabled: " + value);
        input.click();
      }, value);

    for (let i = 0; i < cases.length; i++) {
      await selectCase(i);
      assert.equal(await page.locator("#diseaseOptions input").count(), 4);
      assert.equal(await page.locator("#decisionForm input[type=checkbox]").count(), 0);
      assert.equal(await page.locator(".decision-column.is-locked").count(), 3);
      assert.equal(await page.locator(".decision-column:visible").count(), 1);
      assert.equal(await page.locator("#decisionFeedback").textContent(), "");
      assert(!(await page.locator(".dossier").textContent()).includes(cases[i].knowledge_disease));
    }
    await selectCase(1);
    await page.screenshot({ path: output + "/clinical-before.png", fullPage: true });
    await submit();
    assert.equal(await page.locator(".decision-column.is-locked").count(), 3);

    const wrong = cases[1].options.possible_diseases[1];
    await selectValue("possible_diseases", wrong);
    // Delay diagnosis response, switch cases, then verify it cannot unlock another case.
    await page.route("**/diagnosis", async route => {
      const response = await route.fetch();
      await sleep(350);
      await route.fulfill({ response });
    });
    await submit();
    await selectCase(2);
    await sleep(600);
    assert.equal(await page.locator(".decision-column.is-locked").count(), 3);
    await selectCase(1);
    await page.waitForSelector("#testOptions input");
    await page.unroute("**/diagnosis");
    assert.equal(await page.locator("#diseaseOptions input:disabled").count(), 4);
    assert.equal(await page.locator("#diseaseOptions input:checked").inputValue(), wrong);
    assert.equal(await page.locator("#decisionFeedback").textContent(), "");
    assert((await page.locator("#decisionStatus").textContent()).includes("尚未判定对错"));
    for (const group of ["tests", "treatments", "measures"]) {
      assert.equal(await page.locator('input[name="' + group + '"]').count(), 4);
      await selectValue(group, cases[1].correct_answers[group][0]);
    }
    await selectCase(0);
    await selectCase(1);
    assert.equal(await page.locator("#decisionForm input:checked").count(), 4);
    await page.locator("#decisionBoard").screenshot({ path: output + "/clinical-decisions.png" });

    // A failed evaluation preserves choices and the locked diagnosis, and supports retry.
    await page.route("**/evaluate", route => route.fulfill({
      status: 502, contentType: "application/json", body: JSON.stringify({ detail: "本地测试：暂时不可用" }),
    }));
    await submit();
    await page.waitForFunction(() => document.querySelector("#decisionFeedback").textContent.includes("提交未完成"));
    assert.equal(await page.locator("#decisionForm input:checked").count(), 4);
    assert.equal(await page.locator("#diseaseOptions input:disabled").count(), 4);
    await page.unroute("**/evaluate");
    await page.route("**/evaluate", async route => {
      const response = await route.fetch();
      await sleep(350);
      await route.fulfill({ response });
    });
    await submit();
    await selectCase(0);
    await sleep(650);
    assert.equal(await page.locator("#decisionFeedback").textContent(), "");
    await selectCase(1);
    assert((await page.locator("#decisionFeedback").textContent()).includes("评估反馈"));
    assert((await page.locator("#decisionFeedback").textContent()).includes("登革热"));
    assert.equal(await page.locator("#decisionForm input:disabled").count(), 16);
    await page.locator("#restartDecision").click();
    assert.equal(await page.locator("#decisionForm input:checked").count(), 0);
    assert.equal(await page.locator("#decisionForm input[type=checkbox]").count(), 0);
    assert.equal(await page.locator("#decisionFeedback").textContent(), "");

    // Keyboard-operable single choice. Diagnostics and genuine clinical signs remain intact.
    await page.locator("#diseaseOptions input").first().focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowDown");
    assert.equal(await page.locator("#diseaseOptions input:checked").count(), 1);
    await submit();
    await page.waitForSelector("#testOptions input");
    for (const width of [1440, 842, 390]) {
      await page.setViewportSize({ width, height: 844 });
      for (let i = 0; i < cases.length; i++) {
        await selectCase(i);
        if (await page.locator(".decision-column.is-locked").count()) {
          await selectValue("possible_diseases", cases[i].options.possible_diseases[0]);
          await submit();
          await page.waitForSelector("#testOptions input");
        }
        const layout = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          cards: [...document.querySelectorAll(".decision-column")].map(el => ({
            width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
          })),
          clipped: [...document.querySelectorAll(".option-card > span")].some(el => el.scrollHeight > el.clientHeight + 2),
        }));
        assert(!layout.overflow, "Page overflow at " + width + ", case " + i);
        assert(!layout.clipped, "Clipped option at " + width + ", case " + i);
        assert(layout.cards.every(c => Math.abs(c.width - layout.cards[0].width) < 1));
      }
      await selectCase(1);
      await page.locator("#decisionBoard").screenshot({ path: output + "/clinical-" + width + ".png" });
    }
    assert.deepEqual(errors, []);
    console.log("PASS: all 10 cases; diagnosis gate; wrong answers; case-switch races; retry; reset; keyboard; 1440/842/390px.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
