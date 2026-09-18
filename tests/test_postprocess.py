from openseespy_studio.postprocess import (
    component_end_resultants,
    local_end_actions,
    member_end_resultants,
)


def _local_force_vector():
    return [
        -10.0,
        -20.0,
        -30.0,
        -40.0,
        -50.0,
        -60.0,
        10.0,
        21.0,
        31.0,
        41.0,
        51.0,
        61.0,
    ]


def test_local_end_actions_follow_3d_local_dof_order():
    actions = local_end_actions(_local_force_vector())

    assert actions["N"] == (-10.0, 10.0)
    assert actions["Vy"] == (-20.0, 21.0)
    assert actions["Vz"] == (-30.0, 31.0)
    assert actions["T"] == (-40.0, 41.0)
    assert actions["My"] == (-50.0, 51.0)
    assert actions["Mz"] == (-60.0, 61.0)


def test_member_end_resultants_reverse_i_end_action():
    resultants = member_end_resultants(_local_force_vector())

    assert resultants["N"] == (10.0, 10.0)
    assert resultants["Vy"] == (20.0, 21.0)
    assert resultants["Mz"] == (60.0, 61.0)


def test_component_end_resultants_returns_none_for_short_response():
    assert component_end_resultants([1.0, 2.0], "N") is None


def test_component_end_resultants_validates_component_name():
    try:
        component_end_resultants(_local_force_vector(), "Q")
    except ValueError as exc:
        assert "Unsupported local force component" in str(exc)
    else:
        raise AssertionError("Expected unsupported component to fail")
