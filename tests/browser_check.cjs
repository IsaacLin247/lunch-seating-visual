// Optional end-to-end check: NODE_PATH=<playwright installation>/node_modules
// node tests/browser_check.cjs http://localhost:8765 /tmp/seating-browser
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const base = process.argv[2] || 'http://localhost:8765';
  const output = process.argv[3] || '/tmp/seating-browser';
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [], scenarios = [], stages = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const manifest = await (await page.request.get(`${base}/data/manifest.json`)).json();
    assert.equal(manifest.scenarios.length, 6);
    const honest = await (await page.request.get(`${base}/data/honest.json`)).json();
    assert.equal(honest.config.populationSeed, 7);
    assert.ok(honest.config.provenance.effectiveSourceHash);
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.getElementById('loading').hidden, { timeout: 20000 });
    await page.screenshot({ path: path.join(output, 'room-desktop.png'), fullPage: true });
    await page.getByRole('tab', { name: /Trying to Game It/ }).click();
    assert.equal(await page.locator('#scenario-modes button').count(), 5);
    for (const button of await page.locator('#scenario-modes button').all()) {
      await button.click();
      await page.locator('#btn-last').click();
      await page.waitForTimeout(1400);
      const proof = await page.locator('#game-proof').textContent();
      assert.ok(proof.trim().length > 30);
      const coverage = (await page.locator('#g-ge1').textContent()).match(/(\d+) of (\d+)/);
      assert.ok(coverage);
      assert.equal(coverage[1], coverage[2]);
      scenarios.push({ button: await button.textContent(), proof });
    }
    await page.screenshot({ path: path.join(output, 'game-desktop.png'), fullPage: true });
    await page.getByRole('tab', { name: /The Algorithm/ }).click();
    assert.equal(await page.locator('#stage-controls button').count(), 4);
    for (const rotation of [0, 1, 15]) {
      await page.locator('#scrub').evaluate((el, value) => { el.value = String(value); el.dispatchEvent(new Event('input', { bubbles: true })); }, rotation + 1);
      const actual = Number(await page.locator('#rot-num').textContent()) - 1;
      assert.equal(actual, rotation);
      for (const snapshot of honest.rotations[actual].pipeline) {
        await page.locator(`[data-stage="${snapshot.name}"]`).click();
        assert.equal(Number(await page.locator('#stage-violations').textContent()), snapshot.cost.violations);
        assert.equal(Number((await page.locator('#stage-energy').textContent()).replaceAll(',', '')), snapshot.cost.total / 10);
        stages.push({ rotation: actual + 1, stage: snapshot.name, violations: snapshot.cost.violations });
      }
    }
    await page.locator('#stage-replay').click();
    await page.waitForTimeout(6200);
    assert.equal(await page.locator('[data-stage="final"]').getAttribute('aria-pressed'), 'true');
    await page.screenshot({ path: path.join(output, 'algorithm-desktop.png'), fullPage: true });
    await page.getByRole('tab', { name: /One Student/ }).click();
    await page.locator('#hero-select').selectOption({ index: 0 });
    await page.locator('#btn-last').click();
    await page.setViewportSize({ width: 390, height: 844 });
    for (const name of [/One Student/, /Trying to Game It/, /The Algorithm/, /The Whole Room/]) {
      await page.getByRole('tab', { name }).click();
      await page.waitForTimeout(350);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `mobile overflow: ${name}`);
    }
    await page.getByRole('tab', { name: /The Algorithm/ }).click();
    await page.screenshot({ path: path.join(output, 'algorithm-mobile.png'), fullPage: true });
    let pdfAvailable = null;
    if (!process.argv.includes('--ui-only')) {
      const pdf = await page.request.get(`${base}/article.pdf`);
      assert.equal(pdf.status(), 200);
      assert.ok((await pdf.body()).subarray(0, 5).toString() === '%PDF-');
      pdfAvailable = true;
    }
    assert.deepEqual(errors, []);
    const result = { base, scenarioFiles: manifest.scenarios, scenarios, stagesChecked: stages, javascriptErrors: errors, mobileOverflow: false, pdfAvailable };
    fs.writeFileSync(path.join(output, 'browser_results.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
