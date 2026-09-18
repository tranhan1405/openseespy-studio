# OpenSeesPy Studio

A desktop GUI pre/post processor for **OpenSeesPy**, combining a tree-based workflow inspired by Abaqus/ANSYS with fast viewport and selection ideas from LS-PrePost.

## Current MVP

- Tree-based model navigator
- Interactive 3-D viewport with PyVista/VTK
- GUI generation of regular 3-D frame grids
- Nodes, frame members and support visualization
- Node/element property inspection
- Readable OpenSeesPy code generation
- Export generated models to `.py`
- Execute the generated model with OpenSeesPy

## Architecture

```text
GUI actions
   ↓
Internal StructuralModel
   ├── nodes
   ├── elements
   ├── constraints
   └── later: materials / sections / loads / analysis
   ↓
OpenSeesPy code generator
   ↓
OpenSeesPy solver
   ↓
Results / visualization
```

The internal model is the source of truth. The GUI does not directly edit Python source strings, which keeps geometry operations, property editing, undo/redo and future import/export manageable.

## Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
python run.py
```

or:

```bash
pip install -e .
openseespy-studio
```

## Current workflow

1. Start the application.
2. Open **Geometry → Frame Grid**.
3. Define X/Y bay counts, bay widths, storeys and storey height.
4. Generate the model.
5. The model tree, 3-D viewport and generated OpenSeesPy source update together.
6. Select a node or element in the tree to inspect its properties.
7. Use **File → Export .py** to save the model.
8. Use **Analysis → Run** to execute it with OpenSeesPy.

## Roadmap

### M1 — Geometry foundation
- [x] Internal model database
- [x] Regular 3-D frame generator
- [x] Model tree
- [x] PyVista viewport
- [x] OpenSeesPy code export
- [ ] Create / move / delete node with mouse
- [ ] Create element by picking two nodes
- [ ] Tree ↔ viewport selection/highlight
- [ ] Box / polygon selection
- [ ] Copy / array / mirror / divide / merge
- [ ] Undo / redo command stack

### M2 — OpenSees entities
- [ ] Materials
- [ ] Sections
- [ ] Geometric transformations
- [ ] Constraints / equalDOF / rigidLink
- [ ] Time series and load patterns
- [ ] Recorders

### M3 — Analysis
- [ ] Analysis configuration tree
- [ ] Static / pushover / modal / transient presets
- [ ] Solver console
- [ ] Convergence diagnostics

### M4 — Post-processing
- [ ] Deformed shape
- [ ] Mode shapes
- [ ] Nodal displacement / reaction contours
- [ ] Element forces
- [ ] Time-history plots
- [ ] Animation

### M5 — Code ↔ GUI
- [ ] Import supported OpenSeesPy scripts
- [ ] Command recorder for dynamically generated models
- [ ] Source-to-entity navigation

## Design direction

The default UI is tree-based because large structural models are easier to navigate when entities remain visible and organized. LS-PrePost-style selection, query and geometry tools will be integrated into the toolbar and viewport.

## License

MIT.
