// Render an HTML file to PDF with Chromium via Playwright.
//
// Usage (run from the repository root, with the video project's Playwright
// installation on NODE_PATH):
//
//   NODE_PATH=videos/node_modules node scripts/render_pdf.cjs in.html out.pdf
//
// Chromium writes a running header and footer only when asked to. This script
// never asks: `displayHeaderFooter` is explicitly false and no headerTemplate or
// footerTemplate is supplied, so no page number, title, URL, date or attribution
// can appear at the top or bottom of any page. That is a hard requirement of this
// repository, not a preference, which is why the setting is stated here rather
// than left to a default.

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

async function main() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    console.error('usage: node scripts/render_pdf.cjs <input.html> <output.pdf>');
    process.exit(2);
  }
  if (!fs.existsSync(input)) {
    console.error(`input html not found: ${input}`);
    process.exit(2);
  }

  const html = fs.readFileSync(input, 'utf8');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    // `load` is enough: the report pulls in no remote fonts or images, so there
    // is no later network event to wait for.
    await page.setContent(html, { waitUntil: 'load' });
    await page.emulateMedia({ media: 'print' });
    await page.pdf({
      path: output,
      format: 'A4',
      printBackground: true,
      displayHeaderFooter: false,
      preferCSSPageSize: true,
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
    });
  } finally {
    await browser.close();
  }

  const bytes = fs.statSync(output).size;
  if (bytes <= 0) {
    console.error('chromium produced an empty pdf');
    process.exit(1);
  }
  console.log(`rendered ${path.basename(output)} (${bytes} bytes)`);
}

main().catch((err) => {
  console.error(err && err.message ? err.message : String(err));
  process.exit(1);
});
