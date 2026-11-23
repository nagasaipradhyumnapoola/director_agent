# Fixtures

Controlled, local fixtures used by the M1 pilots. They are deliberately small
and contain seeded defects for detector validation.

- `general/clean`, `general/broken` — scanner regressions (uppercase extension,
  fake secret-like string, invalid JSON, unsupported format, links).
- `website/clean`, `website/broken` — real-browser journey, keyboard, mobile
  overflow, external request, accessibility.
- `ml/clean`, `ml/broken` — clean model vs split/target leakage.
- `research/clean`, `research/broken` — claims, conflicts, calculation, render.

The `AKIA...` and `sk-...`-style strings are **fake test values**, not
credentials. Do not replace them with real secrets.
