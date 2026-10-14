import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  
  // Set viewport
  await page.setViewportSize({ width: 1600, height: 1000 });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  await page.goto('http://127.0.0.1:5173');
  await page.waitForTimeout(1000);

  // Login
  const emailInput = await page.$('input[type="text"], input[type="email"], input[placeholder*="icarus"]');
  if (emailInput) {
    await emailInput.fill('icarus@kiast.or.kr');
    const pwdInput = await page.$('input[type="password"]');
    if (pwdInput) await pwdInput.fill('ts2020!!'); // common password or let's try
    const submitBtn = await page.$('button:has-text("로그인")');
    if (submitBtn) await submitBtn.click();
    await page.waitForTimeout(1500);
  }

  // Open projects modal and load project 4
  const projBtn = await page.$('button:has-text("프로젝트")');
  if (projBtn) {
    await projBtn.click();
    await page.waitForTimeout(1000);
    const card = await page.$('.project-card:has-text("도심지")');
    if (card) {
      await card.click();
      await page.waitForTimeout(2000);
    }
  }

  // Take screenshot of the canvas
  await page.screenshot({ path: '/home/icarus/projects/python/fixit/storage/outputs/actual_canvas_test.png' });
  console.log('Saved actual_canvas_test.png');

  // Let's inspect the Konva Text node for block_3
  const block3Info = await page.evaluate(() => {
    // Find konva stage container or window
    return {
      title: document.title,
      textareas: Array.from(document.querySelectorAll('textarea')).map(t => t.value),
    };
  });
  console.log('Block 3 info:', JSON.stringify(block3Info));

  await browser.close();
})();
