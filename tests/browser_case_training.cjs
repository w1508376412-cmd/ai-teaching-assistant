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
  page.on("pageerror", error => errors.push(error.message));
  try {
    await page.request.post(base + "/api/session/login", { data: { student_no: "CASE-E2E", name: "情景功能测试" } });
    const pre = await (await page.request.post(base + "/api/assessments/start", { data: { phase: "pre" } })).json();
    if (!pre.submitted) await page.request.post(base + `/api/assessments/${pre.id}/submit`, { data: { answers: Object.fromEntries(pre.questions.map(q => [q.id, q.options[0].id])), revision: pre.revision } });
    await page.goto(base + "/#cases");
    await page.waitForSelector("#diseaseOptions input");
    const selectCase = async index => {
      await page.locator("#casePickerTrigger").click();
      await page.locator(`[data-case-index="${index}"]`).click();
    };
    const selectValue = (group, value) => page.locator(`input[name="${group}"]`).evaluateAll((inputs, choice) => {
      const input = inputs.find(node => node.value === choice);
      if (!input || input.disabled) throw new Error("Choice missing or disabled: " + choice);
      input.click();
    }, value);
    const submit = () => page.locator("#decisionForm button[type=submit]").click();

    for (let index = 0; index < cases.length; index++) {
      await selectCase(index);
      assert.equal(await page.locator(".decision-column:visible").count(), 4);
      assert.equal(await page.locator("#diseaseOptions input[type=radio]").count(), 4);
      for (const group of ["tests", "treatments", "measures"]) {
        assert.equal(await page.locator(`input[name="${group}"][type=checkbox]`).count(), 4);
      }
      assert.equal(await page.locator("#decisionForm input:disabled").count(), 0);
      assert.equal(await page.locator("#decisionFeedback").textContent(), "");
      assert(!(await page.locator(".dossier").textContent()).includes(cases[index].knowledge_disease));
    }

    await selectCase(1);
    for (const group of ["possible_diseases", "tests", "treatments", "measures"]) {
      await selectValue(group, cases[1].correct_answers[group][0]);
    }
    await selectCase(0);
    await selectCase(1);
    assert.equal(await page.locator("#decisionForm input:checked").count(), 4);

    await page.route("**/evaluate", route => route.fulfill({
      status: 502, contentType: "application/json", body: JSON.stringify({ detail: "本地测试：暂时不可用" }),
    }));
    await submit();
    await page.waitForFunction(() => document.querySelector("#decisionFeedback").textContent.includes("提交未完成"));
    assert.equal(await page.locator("#decisionForm input:checked").count(), 4);
    assert.equal(await page.locator("#decisionForm input:disabled").count(), 0);
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
    assert.equal(await page.locator("#decisionForm input:disabled").count(), 16);

    for (const width of [1440, 842, 390]) {
      await page.setViewportSize({ width, height: 844 });
      for (let index = 0; index < cases.length; index++) {
        await selectCase(index);
        const layout = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          cards: [...document.querySelectorAll(".decision-column")].map(el => el.getBoundingClientRect().width),
          clipped: [...document.querySelectorAll(".option-card > span")].some(el => el.scrollHeight > el.clientHeight + 2),
        }));
        assert(!layout.overflow, `Page overflow at ${width}, case ${index}`);
        assert(!layout.clipped, `Clipped option at ${width}, case ${index}`);
        assert(layout.cards.every(cardWidth => Math.abs(cardWidth - layout.cards[0]) < 1));
      }
      await selectCase(0);
      await page.locator("#decisionBoard").screenshot({ path: `${output}/clinical-all-${width}.png` });
    }
    await page.setViewportSize({ width: 1440, height: 844 });
    const visualTokens = await page.evaluate(() => {
      const number = getComputedStyle(document.querySelector(".decision-heading > span"));
      const title = getComputedStyle(document.querySelector(".decision-heading strong"));
      const option = document.querySelector(".option-card > span");
      const optionStyle = getComputedStyle(option);
      const checkbox = getComputedStyle(option, "::before");
      const list = getComputedStyle(document.querySelector(".option-list"));
      return {
        number: number.fontSize,
        title: title.fontSize,
        option: optionStyle.fontSize,
        checkboxWidth: checkbox.width,
        checkboxRadius: checkbox.borderRadius,
        gap: list.rowGap,
      };
    });
    assert.deepEqual(visualTokens, {
      number: "24px",
      title: "17px",
      option: "12px", // Existing smaller option typography, approved on 2026-09-14.
      checkboxWidth: "16px",
      checkboxRadius: "1px",
      gap: "10px",
    });
    assert.deepEqual(errors, []);
    console.log("PASS: all 10 cases show four decision cards; restored visual scale; submit/retry; case-switch race; 1440/842/390px.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
