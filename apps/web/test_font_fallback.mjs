import { chromium } from 'playwright';
import fs from 'fs';

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  
  await page.setContent(`
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {
  font-family: 'NanumSquare';
  font-weight: 700;
  src: url('http://127.0.0.1:5173/fonts/NanumSquareB.ttf') format('truetype');
}
@font-face {
  font-family: 'NanumSquareRange';
  font-weight: 700;
  src: url('http://127.0.0.1:5173/fonts/NanumSquareB.ttf') format('truetype');
  unicode-range: U+0000-007F, U+1100-11FF, U+2000-206F, U+3000-303F, U+3130-318F, U+AC00-D7AF;
}
@font-face {
  font-family: 'NotoSansKR';
  font-weight: 700;
  src: url('http://127.0.0.1:5173/fonts/NotoSansKR-Bold.ttf') format('truetype');
}
</style>
</head>
<body style="background: white; padding: 20px;">
  <h3>1. NanumSquare (기존 - fallback: NotoSansKR)</h3>
  <canvas id="c1" width="400" height="50"></canvas>

  <h3>2. NanumSquareRange (unicode-range 적용 - fallback: NotoSansKR)</h3>
  <canvas id="c2" width="400" height="50"></canvas>

  <h3>3. NotoSansKR (단독)</h3>
  <canvas id="c3" width="400" height="50"></canvas>

  <script>
  async function draw() {
    await document.fonts.ready;

    // 1. Existing
    const c1 = document.getElementById('c1');
    const ctx1 = c1.getContext('2d');
    ctx1.font = 'bold 24px NanumSquare, NotoSansKR, sans-serif';
    ctx1.fillText('1단계: 선(先) S/W', 10, 35);

    // 2. With unicode-range
    const c2 = document.getElementById('c2');
    const ctx2 = c2.getContext('2d');
    ctx2.font = 'bold 24px NanumSquareRange, NotoSansKR, sans-serif';
    ctx2.fillText('1단계: 선(先) S/W', 10, 35);

    // 3. NotoSansKR
    const c3 = document.getElementById('c3');
    const ctx3 = c3.getContext('2d');
    ctx3.font = 'bold 24px NotoSansKR, sans-serif';
    ctx3.fillText('1단계: 선(先) S/W', 10, 35);
  }
  window.onload = draw;
  </script>
</body>
</html>
  `);

  await page.waitForTimeout(1500);
  await page.screenshot({ path: '/home/icarus/projects/python/fixit/storage/outputs/font_fallback_comparison.png' });
  console.log('Saved font_fallback_comparison.png');
  await browser.close();
})();
