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

    job.finish(
        "Completed",
        exit_code=0,
        message="Results captured",
        results={"analysis": {"type": "Transient"}},
    )

    assert job.status == "Completed"
    assert job.exit_code == 0
    assert job.results["analysis"]["type"] == "Transient"
    assert job.elapsed_seconds >= 0.0
