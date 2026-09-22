# SARE

<p align="center">
  <img src="src/openseespy_studio/resources/branding/sare_wordmark.svg"
       alt="SARE — Structural Analysis & Research Environment for OpenSees"
       width="760">
</p>

**SARE — Structural Analysis & Research Environment for OpenSees** is a
research-oriented structural simulation environment built around
[OpenSees](https://opensees.berkeley.edu/) with OpenSeesPy as its current
Python backend. It combines a tree-based engineering workflow inspired by
Abaqus/ANSYS with direct, readable OpenSeesPy generation, nonlinear analysis,
earthquake-engineering workflows, and research-focused post-processing.

SARE is intentionally positioned as an engineering and research environment,
not merely a GUI wrapper. The visual interface is one layer over a validated
project/model database, reproducible analysis definitions, solver execution,
and inspectable result workflows.

> **Status:** research alpha — version **0.2.0a1**. The project is usable for
> supported workflows, but engineering results should still be independently
> verified before design or publication use.

## What is implemented

### Modeling and pre-processing

- Tree-based project/model navigator with synchronized viewport selection.
- Interactive PyVista/VTK 3-D viewport.
- Quick 3-D frame grid generation.
- Quick planar 2-D frame generation using the SARE 3-D/6-DOF backend with
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

#### Verified Material Library

SARE includes a provenance-first **Material Library** inspired by Engineering
Data workflows. The official library accepts a constitutive parameter set only
when it can be traced to a specific source and parameter-evidence location.
Journal references require a DOI. Unsupported or merely "commonly used"
values are not silently promoted to verified presets.

The library currently contains **187 verified parameter records**:

- 2 Steel02 Grade-60 reinforcing-steel records from Carreño et al. (2020),
  DOI `10.1061/(ASCE)ST.1943-541X.0002505`.
- 50 Steel02 reinforcing-steel records from Moodley, De Risi and Afshan
  (2026), DOI `10.1016/j.jobe.2026.115378`, covering five
  material/diameter groups, five L/D ratios and two modelling
  representations.
- 50 Hysteretic reinforcing-steel records from the same Moodley et al.
  (2026) study. Exact tensile/compressive backbones come from Appendix
  Table B.2, truss cyclic parameters from Table B.3, and beam-column cyclic
  parameters from Table B.5. Section 4.2.2 is retained as evidence for the
  paper's beam-column assumption that the compression input backbone equals
  the calibrated tensile backbone.
- 12 Pinching4 grooved-fit piping-joint records from Qiu et al. (2023),
  DOI `10.1016/j.engstruct.2023.116615`.
- 17 Pinching4 cold-formed-steel wall records from Singh et al. (2024),
  DOI `10.1016/j.engstruct.2024.118833`.
- 3 Pinching4 light-frame timber connection records from Benedetti et al.
  (2022), DOI `10.3390/buildings12070981`.
- 4 Pinching4 modular CLT connection records from Bhandari et al. (2023),
  DOI `10.1016/j.engstruct.2023.116846`.
- 6 Pinching4 five-story CLT connection records from Benedetti et al.
  (2025), DOI `10.3390/buildings15050727`.
- 6 Pinching4 seismic sway-brace records from Shang et al. (2022),
  DOI `10.1016/j.jobe.2022.104826`.
- 3 records from Del Giudice et al. (2022): one Steel02 parameter set for
  0.6 mm additively manufactured micro-reinforcement and two Concrete01
  confined-core parameter sets for the tested 1:40-scale RC specimens,
  DOI `10.1002/eqe.3578`.
- 3 Steel02 parameter sets for 6082-T6, 6063-T6 and 6060-T5 structural
  aluminium from Georgantzia et al. (2024), DOI
  `10.1061/JMCEE7.MTENG-17314`.
- 2 test-specific Steel02 parameter sets for cyclic structural-steel braces
  from Doci et al. (2024), DOI `10.3390/met14121388`.
- 3 OpenSeesPy parameter sets from Caballero-Castro et al. (2025):
  unconfined and confined Concrete01 plus a Steel02 calibration for TADAS
  dampers, DOI `10.1016/j.istruc.2025.108732`.
- 2 Bond_SP01 strain-penetration records for plain and deformed Ø12
  longitudinal reinforcement from Melo, Varum and Rossetto (2020), DOI
  `10.3389/fbuil.2020.586690`.
- 4 steel records from Sosa and Caiza (2015): one complete
  ReinforcingSteel set for pile-deck connecting bars and three distinct
  ElasticPP prestressing-strand states grouped by element applicability,
  DOI `10.2174/1874149501509010236`.
- 2 Concrete02 records (unconfined and confined shear-wall concrete) from
  Hung and El-Tawil (2009), DOI `10.1002/eqe.921`.
- 1 Concrete04 beam-column concrete record from Yigitbas, Grande and
  Imbimbo (2026), DOI `10.65102/is202545`.
- 3 calibrated Fatigue wrapper records for 6082-T6, 6063-T6 and 6060-T5
  aluminium alloys from Georgantzia, Vardanega and Kashani (2025), DOI
  `10.1007/s10518-025-02097-x`.
- 2 slenderness-dependent Fatigue wrapper records for vertical reinforcing
  bars (L/D = 5 and 12.5) from Zhang et al. (2025), DOI
  `10.1007/s10518-025-02131-y`.
- 2 MinMax reinforcing-steel failure-limit records: the 0.135 tensile
  fracture-strain limit for the additively manufactured micro-rebar of
  Del Giudice et al. (2022), DOI `10.1002/eqe.3578`, and the
  -0.04/+0.12 compression/tension collapse limits used by Zhou et al.
  (2021), DOI `10.1186/s40069-021-00463-y`.
- 2 FRPConfinedConcrete02 `-JacketC` records from Teng et al. (2016):
  the CFRP-jacketed CS-R1 time-history configuration and GFRP-jacketed
  C-5 column, DOI `10.1061/(ASCE)CC.1943-5614.0000584`. The
  specimen geometry, concrete strength and FRP properties are taken from
  the validated test-column study, while Ec, ec0, ft and Ets follow the
  documented OpenSees FRPConfinedConcrete02 input relations.
- 1 Elastic CFRP-sheet record in the fibre direction from Jafari and
  Mahini (2023), using the 240 GPa modulus reported in Table 2 of the
  OpenSees FRP-retrofit study, DOI `10.3390/polym15030618`.
- 2 Steel01 records using the published three-parameter form and the exact
  OpenSees no-isotropic-hardening defaults: an A36 spherical-bearing
  component from Seo, Linzell and Hu (2013), DOI `10.1155/2013/248575`,
  and HRB400 tower reinforcement from Cheng (2019), DOI
  `10.1088/1755-1315/304/4/042054`.
- 1 FRPConfinedConcrete official-reference record. The constitutive-model
  provenance is the peer-reviewed Megalooikonomou, Monti and Santini (2012)
  ACI Structural Journal paper, DOI `10.14359/51683876`; the complete
  18-parameter numerical tuple is taken from the official OpenSees
  FRPConfinedConcrete test script and retains its documented N-mm-MPa
  convention.
- 1 normalized HystereticSmooth official-reference case based on Vaiana et
  al. (2018), DOI `10.1007/s11071-018-4282-2`; the complete ka/kb/fbar/beta
  tuple is reproduced from the official OpenSees documentation.
- 3 **reference-only** RambergOsgoodSteel post-fire reinforcing-steel
  records at 600 °C from Yao et al. (2021), covering natural, furnace and
  water cooling, DOI `10.3390/ma14020469`. The published normalized
  coefficient α is mapped exactly to the source-code coefficient
  a = α·fy/E. Stock OpenSeesPy 3.8.x reports RambergOsgoodSteel as
  temporarily removed from compiled Tcl/Py builds because of known issues
  and unreliable results, so SARE keeps these records for traceable
  reference/preview but disables project insertion, export and runtime
  material testing.

These are **published/calibrated parameter records**, not 187 unrelated
chemical materials. SARE exposes specimen/configuration, modelling
representation, applicability and limitations so a paper-specific parameter
set is not mistaken for a universal material-grade default.

For response-based models such as Pinching4 and Hysteretic, the library also
records the physical response context and source units. Force-displacement
records are stored internally in N/m-based SI quantities, moment-rotation
records in N·m/rad, and sourced stress-strain Hysteretic records store stress
in Pa and strain as decimal strain. SARE converts these values to the active
project unit system when displaying, editing and generating OpenSeesPy.
Legacy/manual Pinching4 and Hysteretic definitions without response metadata
retain their previous raw behavior for backward compatibility.

Library records store the material/grade, constitutive model, complete
parameter set, applicability, limitations, primary citation, DOI, exact
evidence location, response quantity and published units. This provenance is
copied into the project and written as comments when OpenSeesPy source is
exported.

Use **Material Library... → Insert into Project** to create a new project
material directly. Verified wrapper presets such as **Fatigue** require the
user to select an existing project base material before insertion; the same
base-material selection is preserved when a verified wrapper preset is loaded
through the Material Editor. The regular **New/Edit Material** dialog also provides
**Load Verified Preset...**, which loads the selected constitutive model,
parameters and provenance into the material being edited while preserving an
existing project's tag/name and engineering properties. If a verified
constitutive parameter is edited, SARE changes the project material status to
`modified_from_verified` rather than continuing to present it as the
unchanged published set.

Density, Poisson ratio, or other engineering defaults are not automatically
claimed as verified by a constitutive-model paper unless the library record
explicitly sources them.

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

SARE currently supports:

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

For Quick 1-D Column specimens, SARE can additionally capture and separate:

- base-section moment-curvature response
- base-interface moment-rotation response
- critical steel/concrete fiber histories
- Bond_SP01 stress-slip histories
- member/interface drift-equivalent contributions
- reversal strength/stiffness degradation
- branch and detected closed-cycle energy

### Section-to-hinge and cyclic calibration

SARE keeps the research path explicit:

1. **Moment-Curvature** runs an isolated OpenSees zeroLengthSection section
   test from an existing Section. The wizard asks only for Section, bending
   axis, axial load, maximum curvature and increment count. Temporary nodes,
   load patterns and Static DisplacementControl objects are never inserted
   into the user's structural model. The completed Job opens directly in
   **Result > Moment-Curvature**.
2. **Hinge Backbone** converts researcher-confirmed characteristic points from
   a moment-rotation curve directly, or from moment-curvature using the
   explicit assumption theta = kappa * L_eq, into a symmetric OpenSees
   Hysteretic moment-rotation material. Moment-Curvature results can open this
   builder directly with their SARE source metadata prefilled. SARE does not
   infer cracking, yield, ultimate, plastic-hinge length, pinching or
   deterioration silently.
3. **Cyclic Calibration** compares a complete model response against
   experimental cyclic data and varies selected material parameters. This is
   the appropriate stage for fitting hysteretic pinching/degradation behavior.

The resulting Hysteretic material is assigned separately through
**Model > ZeroLength / Link...**, normally to a rotational hinge DOF. A
zeroLengthSection remains a different modeling branch: it places a complete
Section object at the interface instead of a calibrated uniaxial hinge
backbone.

Cyclic experimental CSV/TSV data can be imported and overlaid against
OpenSees results.

The cyclic-calibration subsystem supports:

1. material-parameter grid sweeps
2. adaptive coarse-to-fine refinement
3. weighted objective scoring from available experimental metrics
4. calibration history and round-best parameter trajectories
5. multi-objective Pareto fronts (P1, P2, ...)
6. per-case Jobs for direct inspection
7. preview/apply of a selected calibrated case with Undo support
8. CSV export of scalar, objective and Pareto metadata

Pareto analysis is descriptive: SARE does not automatically decide which
non-dominated case should be adopted.

### SARE AI Assistant

SARE includes an optional **read-only AI Assistant** dock. The first provider
is OpenAI through the Responses API. The assistant does not execute generated
Python or modify the project. Instead, it can inspect a local project snapshot
through controlled read-only tools for:

- model summary and current node/element selection
- individual nodes, elements, materials, sections and connection objects
- active analysis settings
- current Model Check issues
- recent Job/result summaries
- recent solver-console output

Open the assistant from **Analysis > Research**, **Tools > AI Assistant**, or
right-click a Model Tree object and choose **Ask AI about this**.

The API key is never written to a SARE project. Either set it before launching
SARE:

```powershell
$env:OPENAI_API_KEY="..."
```

or enter a session-only key in the AI Assistant panel. OpenAI requests use
`store=False`. A ChatGPT subscription/login is separate from OpenAI API
credentials and billing.

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

Launch SARE:

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

SARE uses several verification layers rather than treating GUI tests as
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

This generates a structural model through SARE's code generator, executes
the generated Python through the SARE solver worker using the real
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

- SARE supports a curated subset of OpenSees/OpenSeesPy commands rather
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
