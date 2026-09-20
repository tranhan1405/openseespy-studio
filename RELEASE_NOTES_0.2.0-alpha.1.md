# OpenSeesPy Studio v0.2.0-alpha.1

This is the first packaged research-alpha release of OpenSeesPy Studio.

## Highlights

- Desktop OpenSeesPy pre/post-processing workflow with tree-based model management and PyVista/VTK visualization.
- Quick 3D frame, planar 2D frame and 1D column/specimen workflows.
- Elastic and Fiber sections with nonlinear concrete, steel, bond/interface and FRP-related material support.
- Static, Modal, Pushover, Cyclic and Nonlinear Time History analysis templates.
- Adaptive convergence recovery and solver diagnostics.
- Cyclic experimental comparison, calibration, adaptive coarse-to-fine refinement and Pareto analysis.
- Research-oriented column outputs including moment-curvature, interface response, fiber histories, bond-slip and drift decomposition.
- Built-in earthquake-record workflow with scaling and multi-component excitation.

## Verification for this release

The release code has passed:

- 439 unit/offscreen GUI tests on the merged main commit.
- A real OpenSeesPy integration test that generates a cantilever model through Studio, executes it through the Studio solver worker and verifies displacement, reaction and convergence results.
- Runtime self-check with OpenSeesPy 3.8.0.
- Windows source-runtime self-check.
- PyInstaller standalone build.
- Packaged GUI -> dedicated worker executable -> OpenSeesPy solver self-check.
- Portable ZIP generation.
- Inno Setup installer generation.

## Windows packages

Two Windows x64 packages are attached:

- **OpenSeesPy-Studio-0.2.0-alpha.1-Setup.exe** — recommended installer.
- **OpenSeesPy-Studio-0.2.0-alpha.1-Windows-x64-portable.zip** — portable/debug package.

The standalone package includes the Python/OpenSeesPy runtime required by Studio; users do not need to install OpenSeesPy separately.

## Research-alpha notice

This is a research-alpha release, not a design-code certification tool. Supported workflows have automated software/runtime checks, but research models should still be independently benchmarked against theory, trusted reference models or experimental data before publication or engineering use.
