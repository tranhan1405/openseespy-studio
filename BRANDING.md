# FEWIZ Brand Identity

**FEWIZ** stands for **Finite Element Wizard**.

FEWIZ is a structural finite-element modeling, analysis and results environment
built around an automated **Wizard** workflow. In FEWIZ, a Wizard is a
parametric model builder: engineering inputs are converted into model entities,
previewed, then created automatically.

The Python package and project format intentionally retain the historical
`openseespy-studio` identifiers where changing them would break compatibility.

## Primary mark

The official FEWIZ mark is a **W-shaped finite-element mesh ribbon**.

- The left/model side is navy and engineering blue.
- The right side transitions to **Wizard orange**, representing geometry and
  model content generated automatically by a Wizard.
- Nodes, member edges, cross-members and triangular faces make the mark read as
  an FE mesh rather than a generic connected-dot logo.
- One small orange four-point spark is retained as the automation cue.
- The app icon uses a dark navy field; light and monochrome marks are provided
  for documentation and print use.
- At 16-32 px the runtime icon simplifies the mesh automatically so the W
  silhouette remains readable.

This is the selected FEWIZ visual family. Avoid AI-style glow, 3-D rendering,
heavy gradients, mascot imagery or decorative magic-wand graphics.

## Wordmark

Use **FEWIZ** as the primary wordmark, with **FE** in engineering blue and
**WIZ** in charcoal. When space permits, pair it with:

> FINITE ELEMENT WIZARD

The mesh mark may sit to the left of the wordmark for horizontal layouts or
above it for vertical layouts.

## Core colors

- FEWIZ Navy: `#0A2E55`
- Structural Navy: `#0B315C`
- Engineering Blue: `#0B5DAA`
- Mesh Blue: `#2D86D1`
- Wizard Orange: `#F28C00`
- Dark Orange: `#C96E00`
- Charcoal: `#20272E`
- Light Field: `#F7FAFC`

## Usage

- App/taskbar icon: dark-field mesh W with the orange generated side.
- Ribbon/header: horizontal FEWIZ wordmark.
- Wizard commands: reuse the orange generation accent consistently so Wizard
  functions are recognizable as one family.
- About dialog: product name, description and current OpenSeesPy backend.
- Technical/package identifiers may retain `openseespy-studio` for compatibility.
- The legacy `sare_mark.svg` and `sare_wordmark.svg` paths remain visual
  aliases during the transition so older references do not break.

## Assets

- `fewiz_mark.svg` — primary dark-field app mark.
- `fewiz_mark_light.svg` — light-background mark.
- `fewiz_mark_mono.svg` — monochrome/print mark.
- `fewiz_wordmark.svg` — horizontal wordmark.
