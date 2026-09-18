from openseespy_studio.jobs import JobRecord


def test_job_lifecycle():
    job = JobRecord(
        job_id=1,
        analysis_tag=2,
        analysis_name="EQ",
        analysis_type="Transient",
    )
    job.start()
    assert job.status == "Running"
    assert job.elapsed_seconds >= 0.0

    job.update_progress(
        25,
        100,
        algorithm="Newton",
        iterations=7,
        message="Newton · iter 7",
    )
    assert job.progress_current == 25
    assert job.progress_total == 100
    assert job.progress_percent == 25.0
    assert job.current_algorithm == "Newton"
    assert job.iterations == 7

    job.finish(
        "Completed",
        exit_code=0,
        message="Results captured",
        results={"analysis": {"type": "Transient"}},
    )

    assert job.status == "Completed"
    assert job.exit_code == 0
    assert job.progress_percent == 100.0
    assert job.results["analysis"]["type"] == "Transient"
    assert job.elapsed_seconds >= 0.0
