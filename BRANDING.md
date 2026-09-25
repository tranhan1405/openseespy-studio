# FEWIZ Brand Identity

**FEWIZ** stands for **Finite Element Wizard**.

FEWIZ is a structural finite-element modeling, analysis and results environment
built around an automated **Wizard** workflow. In FEWIZ, a Wizard is not merely
a Next/Back dialog: it is a parametric model builder that converts engineering
inputs into model entities, previews the result, and creates the finite-element
objects automatically.

The Python package and project format intentionally retain the historical
`openseespy-studio` identifiers where changing them would break compatibility.

## Primary mark

The application mark is a geometric **W** built from finite-element members and
nodes. It deliberately looks like engineering/CAD geometry rather than an AI
mascot or decorative illustration.

- Navy members and outlined nodes represent the FE model.
- The blue central node provides the visual anchor.
- One red terminal member indicates generated/active model content.
- No gradients, magic wand, stars or sparkles are used.

The mark must remain recognizable at 16 x 16 px.

## Wordmark

Use **FEWIZ** as the primary wordmark. When space permits, pair it with:

> Finite Element Wizard

A useful product line is:

> Build FE models, not commands.

OpenSeesPy is the current backend, but it is not part of the primary product
name so the FEWIZ identity remains independent of a single solver backend.

## Core colors

- FEWIZ Navy: `#0B315C`
- Deep Navy: `#082643`
- FE Node Blue: `#2871B9`
- Generated/Active Red: `#E5252A`
- Light Field: `#F7FAFC`

## Usage

- App icon: structural W made from FE nodes and members.
- Ribbon/header: FEWIZ wordmark with the compact descriptor “Finite Element Wizard”.
- About dialog: product name, description and current OpenSeesPy backend.
- Wizard commands remain the signature automated model-generation workflow.
- Technical/package identifiers may retain `openseespy-studio` for compatibility.
- The legacy `sare_mark.svg` and `sare_wordmark.svg` paths are retained as
  visual aliases during the transition so older references do not break.
