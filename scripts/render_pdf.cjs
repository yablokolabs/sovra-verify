// Render an HTML file to PDF with Chromium via Playwright.
//
// Usage (run from the repository root, with the video project's Playwright
// installation on NODE_PATH):
//
//   NODE_PATH=videos/node_modules node scripts/render_pdf.cjs in.html out.pdf
//
// Optional third argument: the font families the document requires.
//
//   NODE_PATH=videos/node_modules node scripts/render_pdf.cjs in.html out.pdf Archivo,Nunito
//
// A font that fails to load does not fail the render: Chromium substitutes a
// system face and the PDF looks finished. The names passed here are checked in
// the rendered document instead, and a missing family exits non-zero rather than
// printing a document in the wrong typeface.
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
  const [input, output, expectedFontsArg] = process.argv.slice(2);
  if (!input || !output) {
    console.error('usage: node scripts/render_pdf.cjs <input.html> <output.pdf> [Family,Family]');
    process.exit(2);
  }
  const expectedFonts = (expectedFontsArg || '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
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
    // A web font is fetched when the document first needs it, which can be after
    // the load event. Waiting for the font set to settle is what keeps a report
    // from printing in the fallback face; it resolves immediately for a document
    // that uses no web font, so the existing report is unaffected.
    await page.evaluate(async () => {
      if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
      }
    });
    if (expectedFonts.length > 0) {
      const report = await page.evaluate((families) => {
        const faces = Array.from(document.fonts || []).map((face) => ({
          family: face.family.replace(/["']/g, ''),
          status: face.status,
        }));
        const missing = families.filter(
          (family) => !faces.some((face) => face.family === family)
        );
        // `document.fonts.check` is true for a family with no @font-face at all,
        // so it is reported alongside the face list rather than trusted alone.
        const unchecked = families.filter((family) => {
          try {
            return !(document.fonts && document.fonts.check(`1em "${family}"`));
          } catch (err) {
            return true;
          }
        });
        return { faces, missing, unchecked };
      }, expectedFonts);
      const rendered = report.faces.map((face) => `${face.family}:${face.status}`).join(', ');
      console.log(`fonts in the rendered document: ${rendered || 'none'}`);
      const failed = report.faces.filter((face) => face.status === 'error').map((face) => face.family);
      if (report.missing.length > 0 || report.unchecked.length > 0 || failed.length > 0) {
        console.error(
          'the document would print in a substitute face: ' +
            `not registered: ${report.missing.join(', ') || 'none'}; ` +
            `failed to decode: ${failed.join(', ') || 'none'}; ` +
            `not available: ${report.unchecked.join(', ') || 'none'}`
        );
        process.exit(1);
      }
      console.log(`required fonts loaded: ${expectedFonts.join(', ')}`);
    }
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
