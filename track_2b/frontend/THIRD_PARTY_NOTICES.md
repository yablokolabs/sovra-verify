# Third-party notices

This file exists so that required licensing and provenance text lives in a dedicated file rather than
in a footer, an attribution bar or any trailing section of a screen, document, export or report. The
no-footer rule in this project does not remove any licensing obligation, and this file preserves
them.

## React

The frontend is built with React and React DOM, which are bundled into
`track_2b/frontend/dist/assets/*.js`. The bundler preserves their licence headers in that output.
Those headers are dependency licence notices, not a footer of this application, and they must not be
removed.

```
MIT License

Copyright (c) Facebook, Inc. and its affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Other bundled dependencies

The frontend build also includes Vite's and Babel's runtime helpers, whose licence headers the
bundler preserves in the same way. Their full texts are not reproduced here because they live in the
installed packages under `node_modules` and in each package's own `LICENSE` file.

## How this interacts with the footer audit

`scripts/check_no_footer.py` classifies a preserved dependency licence header inside the built bundle
separately from a footer. It reports the count, prints the file, and does not fail the run — because
the alternative would be to strip a licence notice that has to be kept. The exemption is limited to
the built bundle and to copyright-type markers that sit next to a recognisable licence signature. A
`<footer>` element, a "powered by" line, an attribution bar or a closing signature still fails
everywhere, including in the built bundle, and our own source, generated reports, exports and HTTP
responses are never eligible for the exemption.
