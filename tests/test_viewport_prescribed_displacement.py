import numpy as np

from openseespy_studio.ui.viewport import ModelViewport


def test_prescribed_displacement_axis_maps_translation_and_rotation():
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(1),
        (1.0, 0.0, 0.0),
    )
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(2),
        (0.0, 1.0, 0.0),
    )
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(3),
        (0.0, 0.0, 1.0),
    )
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(4),
        (1.0, 0.0, 0.0),
    )
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(5),
        (0.0, 1.0, 0.0),
    )
    np.testing.assert_allclose(
        ModelViewport._prescribed_displacement_axis(6),
        (0.0, 0.0, 1.0),
    )


def test_prescribed_rotation_basis_is_orthogonal_to_axis():
    for dof in (4, 5, 6):
        axis = ModelViewport._prescribed_displacement_axis(dof)
        basis_u, basis_v = ModelViewport._rotation_basis(axis)

        assert np.isclose(np.linalg.norm(basis_u), 1.0)
        assert np.isclose(np.linalg.norm(basis_v), 1.0)
        assert np.isclose(np.dot(axis, basis_u), 0.0)
        assert np.isclose(np.dot(axis, basis_v), 0.0)
        assert np.isclose(np.dot(basis_u, basis_v), 0.0)
