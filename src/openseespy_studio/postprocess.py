from __future__ import annotations

from collections.abc import Sequence


LOCAL_FORCE_COMPONENTS: tuple[str, ...] = (
    "N",
    "Vy",
    "Vz",
    "T",
    "My",
    "Mz",
)

LOCAL_FORCE_INDEX: dict[str, int] = {
    name: index
    for index, name in enumerate(LOCAL_FORCE_COMPONENTS)
}


def local_end_actions(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Return OpenSees local nodal end actions for a 3D frame element.

    OpenSees orders the 12 local-force values by the six local DOFs at
    node I followed by the six local DOFs at node J:
    Fx, Fy, Fz, Mx, My, Mz at each end.
    """
    if len(values) < 12:
        return {}
    numeric = [float(value) for value in values[:12]]
    return {
        component: (
            numeric[index],
            numeric[index + 6],
        )
        for component, index in LOCAL_FORCE_INDEX.items()
    }


def member_end_resultants(
    values: Sequence[float],
) -> dict[str, tuple[float, float]]:
    """Convert nodal end actions to a common member-section sign convention.

    The local-force response is the element action on each end node. To plot
    one continuous internal-resultant diagram from I to J, the I-end action
    is reversed while the J-end action is retained.
    """
    actions = local_end_actions(values)
    return {
        component: (-end_i, end_j)
        for component, (end_i, end_j) in actions.items()
    }


def component_end_resultants(
    values: Sequence[float],
    component: str,
) -> tuple[float, float] | None:
    component = str(component)
    if component not in LOCAL_FORCE_INDEX:
        raise ValueError(
            f"Unsupported local force component: {component}"
        )
    return member_end_resultants(values).get(component)
