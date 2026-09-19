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



def test_job_can_keep_multiple_plot_entries():
    job = JobRecord(
        job_id=4,
        analysis_tag=1,
        analysis_name="Static 1",
        analysis_type="Static",
        results={"analysis": {"type": "Static"}},
    )

    first = job.add_plot(
        name="Axial Force",
        result_type="MemberForce",
        settings={"component": "N"},
        element_scope=[2, 1, 2],
    )
    second = job.add_plot(
        name="Axial Force",
        result_type="MemberForce",
        settings={"component": "N"},
    )
    reaction = job.add_plot(
        name="Reaction FX",
        result_type="NodalReaction",
        settings={"component": "FX"},
        node_scope=[4],
    )

    assert first["plot_id"] == 1
    assert first["name"] == "Axial Force"
    assert first["element_scope"] == [1, 2]
    assert second["plot_id"] == 2
    assert second["name"] == "Axial Force 2"
    assert reaction["plot_id"] == 3
    assert job.plot(2)["name"] == "Axial Force 2"

    job.remove_plot(2)
    assert job.plot(2) is None
    assert [plot["name"] for plot in job.plots] == [
        "Axial Force",
        "Reaction FX",
    ]
