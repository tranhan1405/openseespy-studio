# OpenSeesPy Studio

**OpenSeesPy Studio** is a desktop pre/post-processing environment for
[OpenSeesPy](https://openseespydoc.readthedocs.io/). It combines a
tree-based engineering workflow inspired by Abaqus/ANSYS with direct,
readable OpenSeesPy generation and research-oriented nonlinear analysis
tools.

> **Status:** research alpha — version **0.2.0a1**. The project is usable for
> supported workflows, but engineering results should still be independently
> verified before design or publication use.

## What is implemented

### Modeling and pre-processing

- Tree-based project/model navigator with synchronized viewport selection.
- Interactive PyVista/VTK 3-D viewport.
- Quick 3-D frame grid generation.
- Quick planar 2-D frame generation using the Studio 3-D/6-DOF backend with
  automatic out-of-plane restraints.
- Quick 1-D column / experimental specimen workflow.
- Node and frame-element creation plus copy, move, rotate, mirror and delete.
- Fixed, pinned and custom restraints; equalDOF, rigidLink and rigidDiaphragm.
- Geometric transformations and elastic/nonlinear beam-column formulations.
- Project save/open, OpenSeesPy source export and undo/redo.

### Materials, sections and interfaces

Supported uniaxial material families include:

- Elastic
- Steel01 / Steel02
- ReinforcingSteel
- Concrete01 / Concrete02 / Concrete04
- Hysteretic / Pinching4
- Bond_SP01
- ElasticPPGap
- FRPConfinedConcrete02
- MinMax / Fatigue
- Parallel / Series

Section workflows include elastic sections and Fiber sections using native
OpenSees patch/layer/fiber commands, with common RC section templates and
nonlinear material assignment.

Research interface workflows include:

- zeroLength
- twoNodeLink
- zeroLengthSection
- Bond_SP01 strain-penetration interfaces
- base translational/rotational springs
- RC-column FRP retrofit helpers

### Loads, mass and earthquake input

- Nodal mass assignment.
- Seismic mass-source generation from self mass and selected load patterns.
- TimeSeries and load-pattern objects.
- Nodal loads, prescribed displacements and beam loads.
- Built-in and local earthquake-record workflows with scaling.
- Multi-component NLTH excitation.
- Custom, uniform, triangular, mass-proportional and mode-informed lateral
  loading workflows where supported by the selected analysis template.

### Analysis

Studio currently supports:

- Static
- Modal
- Pushover
- Cyclic
- Nonlinear Time History (NLTH)

The analysis layer includes configurable convergence tests/algorithms,
fallback recovery, adaptive cutback, progress events and isolated worker
execution.

### Results and research diagnostics

Available post-processing includes:

- undeformed/deformed model views
- mode shapes and modal participation summaries
- nodal displacement/reaction histories and contours
- local/member forces
- hinge/yield-state diagnostics
- time-history plots and motion playback
- fiber stress/strain inspection
- convergence histories and fallback/cutback diagnostics
- cyclic hysteresis, backbone and reversal/cycle summaries

For Quick 1-D Column specimens, Studio can additionally capture and separate:

- base-section moment-curvature response
- base-interface moment-rotation response
- critical steel/concrete fiber histories
- Bond_SP01 stress-slip histories
- member/interface drift-equivalent contributions
- reversal strength/stiffness degradation
- branch and detected closed-cycle energy

### Experimental comparison and calibration

Cyclic experimental CSV/TSV data can be imported and overlaid against
OpenSees results.

The calibration subsystem supports:

1. material-parameter grid sweeps
2. adaptive coarse-to-fine refinement
3. weighted objective scoring from available experimental metrics
4. calibration history and round-best parameter trajectories
5. multi-objective Pareto fronts (P1, P2, ...)
6. per-case Jobs for direct inspection
7. preview/apply of a selected calibrated case with Undo support
8. CSV export of scalar, objective and Pareto metadata

Pareto analysis is descriptive: Studio does not automatically decide which
non-dominated case should be adopted.

## Installation from source

### Windows

The supported development runtime is **64-bit Python 3.12**.

Using Conda:

```powershell
conda create -n openseespy-studio python=3.12 -y
conda activate openseespy-studio

python -m pip install --upgrade pip
python -m pip install -e .
```

Verify the complete runtime:

```powershell
python -m openseespy_studio --self-check
```

Launch Studio:

```powershell
python -m openseespy_studio
```

or:

```powershell
openseespy-studio
```

The package currently targets:

```text
Python >= 3.12, < 3.13
OpenSeesPy >= 3.8.0.0, < 3.9
```

## Standalone Windows build

The repository contains a reproducible Windows packaging workflow:

```text
Python / OpenSeesPy / PySide6 / PyVista
              ↓
        PyInstaller onedir
              ↓
 packaged executable --self-check
              ↓
          portable ZIP
              ↓
          Inno Setup
              ↓
 OpenSeesPy-Studio-*-Setup.exe
```

The installer targets 64-bit Windows and installs under the current user's
local application directory, so administrator privileges are not required.

GitHub Actions workflow:

```text
.github/workflows/windows-package.yml
```

Local PyInstaller build:

```powershell
python -m pip install -e . pyinstaller
pyinstaller packaging\openseespy_studio.spec --noconfirm --clean
.\dist\OpenSeesPyStudio\OpenSeesPyStudio.exe --self-check
```

The Inno Setup definition is:

```text
packaging/windows_installer.iss
```

## Verification strategy

Studio uses several verification layers rather than treating GUI tests as
solver validation.

### 1. Unit and offscreen GUI tests

```bash
python -m pytest -q -m "not integration"
```

These cover model/project logic, generators, templates, post-processing,
calibration and Qt behavior.

### 2. Real OpenSeesPy integration test

```bash
python -m pip install -e . pytest
python -m pytest -q -m integration tests/test_opensees_integration.py
```

This generates a structural model through Studio's code generator, executes
the generated Python through the Studio solver worker using the real
OpenSeesPy runtime, and checks displacement, reaction and convergence output.

### 3. Runtime / packaged self-check

```bash
python -m openseespy_studio --self-check
```

The same command is executed against the packaged Windows executable. It
checks imports, bundled resources and a small real OpenSees solve.

These checks establish software/runtime consistency; they do **not** replace
benchmarking a research model against theory, published examples or
experimental data.

## Architecture

```text
GUI actions / templates
          ↓
ProjectDatabase + StructuralModel
          ↓
Validation / model checks
          ↓
Readable OpenSeesPy generator
          ↓
Isolated solver worker
          ↓
OpenSeesPy
          ↓
Result schema / Jobs
          ↓
Post-processing / research diagnostics
          ↓
Experimental comparison / calibration / Pareto
```

The internal project model is the source of truth. The GUI does not edit
generated Python source strings directly.

## Current limitations

- Studio supports a curated subset of OpenSees/OpenSeesPy commands rather
  than every possible element, material and analysis option.
- General arbitrary OpenSeesPy script import/reconstruction is not complete.
- Advanced research workflows still require engineering judgment about
  constitutive models, discretization, convergence and validation.
- Very large models can require reduced viewport annotations and careful
  post-processing choices.
- The standalone packaging workflow currently targets Windows x64.

## Near-term roadmap

Priority is now **verification, stability and distribution**, not simply
adding more buttons:

- expand real-solver benchmark cases for static, modal, cyclic and NLTH
- add reproducible benchmark/reference datasets
- add release notes and versioned Windows artifacts
- continue performance profiling for large 3-D models
- strengthen project backward-compatibility tests
- add supported script import/source-to-entity workflows

## License

MIT.
