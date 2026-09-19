from openseespy_studio.live_convergence import (
    parse_opensees_convergence_line,
)


def test_parse_norm_unbalance_iteration_line():
    line = (
        "CTestNormUnbalance::test() - iteration: 2 current Norm: "
        "1.40925e-14 (max: 1e-08, Norm deltaX: 0.00103448)"
    )

    parsed = parse_opensees_convergence_line(line)

    assert parsed == {
        "test": "NormUnbalance",
        "iteration": 2,
        "norm": 1.40925e-14,
        "tolerance": 1.0e-8,
        "failed": False,
    }


def test_parse_norm_disp_incr_iteration_line():
    line = (
        "CTestNormDispIncr::test() - iteration: 3 current Norm: "
        "3.25479e-19 (max: 1e-08, Norm R: 7.32283e-15)"
    )

    parsed = parse_opensees_convergence_line(line)

    assert parsed is not None
    assert parsed["test"] == "NormDispIncr"
    assert parsed["iteration"] == 3
    assert parsed["norm"] == 3.25479e-19
    assert parsed["tolerance"] == 1.0e-8


def test_parse_failure_line_without_iteration_is_marked_failed():
    line = (
        "WARNING: CTestNormUnbalance::test() - failed to converge "
        "after: 25 iterations current Norm: 909944 "
        "(max: 1e-06, Norm deltaX: 22.8693)"
    )

    parsed = parse_opensees_convergence_line(line)

    assert parsed is not None
    assert parsed["test"] == "NormUnbalance"
    assert parsed["norm"] == 909944.0
    assert parsed["tolerance"] == 1.0e-6
    assert parsed["failed"] is True


def test_non_convergence_console_line_is_ignored():
    assert parse_opensees_convergence_line("OpenSees > analyze failed") is None
