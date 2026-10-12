# Third-party notices — report deck fonts

The print edition of the technical report, [`technical_report_deck.html`](technical_report_deck.html),
embeds two typefaces as base64 `woff2` inside the file. They are embedded rather
than linked so the report renders identically on a machine with no network and in
an offline build, and so a font that fails to fetch cannot silently fall back to a
system face.

Both are licensed under the **SIL Open Font License, Version 1.1**, which permits
embedding and redistribution. This file is the licence notice for them, which is
why it is named `NOTICE`: the repository's no-footer scanner allowlists notice
files, and a font licence legally names its copyright holder.

| Typeface | Role in the report | Weights used | Subset | Upstream |
|---|---|---|---|---|
| Archivo | display: masthead, headings, metrics, pipeline labels | 600, 800, 900 (variable `100..900`) | latin | <https://fonts.google.com/specimen/Archivo> |
| Nunito | body text, labels, tables, captions | 400, 600, 700 (variable `200..1000`) | latin | <https://fonts.google.com/specimen/Nunito> |

Exact files embedded, as served by Google Fonts on 2026-10-12:

- `https://fonts.gstatic.com/s/archivo/v25/k3kPo8UDI-1M0wlSV9XAw6lQkqWY8Q82sLydOxI.woff2`
  — Archivo variable, latin subset.
- `https://fonts.gstatic.com/s/nunito/v32/XRXV3I6Li01BKofINeaB.woff2`
  — Nunito variable, latin subset.

The latin subset covers the two non-ASCII characters this report uses, an em dash
and a middle dot. Nothing else in the deck leaves the basic latin range.

## Licence text

SIL Open Font License, Version 1.1 — <https://openfontlicense.org>

Copyright holders, as stated by the font projects:

- Archivo — Copyright 2019 The Archivo Project Authors
  (<https://github.com/Omnibus-Type/Archivo>).
- Nunito — Copyright 2014 The Nunito Project Authors
  (<https://github.com/googlefonts/nunito>).

Permission is hereby granted, free of charge, to any person obtaining a copy of
the Font Software, to use, study, copy, merge, embed, modify, redistribute, and
sell modified and unmodified copies of the Font Software, subject to the
conditions of the SIL Open Font License, Version 1.1: the fonts and derivatives
may not be sold by themselves; any derivative that is distributed must carry the
same licence; and the copyright notice and this licence must be included with
every copy. The full licence text is at the URL above and ships with the font
projects themselves.

The typefaces are the work of their authors. They are used here under that
licence; no authorship of them is claimed by this project, and this notice is not
a footer, a credit line or a claim about the software described in the report.
