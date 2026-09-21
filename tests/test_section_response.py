from types import SimpleNamespace

import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    ConnectionData,
    SectionData,
    SolutionResultData,
    TransformationData,
)
from openseespy_studio.section_response import (
    automatic_moment_curvature_spec,
    build_section_response_specs,
    section_component_catalog,
    section_response_sources,
    validate_section_response_request,
)


def test_2d_section_component_catalog_is_semantic():
    catalog = section_component_catalog(2)

    assert list(catalog) == ["P", "Mz"]
    assert catalog["P"]["index"] == 0
    assert catalog["Mz"]["index"] == 1
    assert catalog["Mz"]["pair_label"] == "Mz–κz"


def test_zero_length_section_is_a_direct_section_response_source():
    model = StructuralModel("zero-section", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    connection = ConnectionData(
        10,
        "Section spring",
        "zeroLengthSection",
        1,
        2,
        section_tag=4,
    )

    sources = section_response_sources(model, {10: connection})

    assert len(sources) == 1
    source = sources[0]
    assert source["element_tag"] == 10
    assert source["element_kind"] == "zeroLengthSection"
    assert source["query_mode"] == "direct"
    assert source["locations"] == [1]
    assert source["components"] == ["P", "Mz"]


def test_force_beam_column_exposes_each_integration_point():
    model = StructuralModel("beam-sections", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.add_element(
        21,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=7,
        transf_tag=1,
        integration_points=5,
    )

    sources = section_response_sources(model)
    assert len(sources) == 1
    source = sources[0]
    assert source["query_mode"] == "indexed"
    assert source["locations"] == [1, 2, 3, 4, 5]
    assert source["components"] == ["P", "Mz", "My", "T"]


def test_section_response_validation_rejects_wrong_component_and_ip():
    model = StructuralModel("beam-sections", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0)
    model.add_element(
        3,
        1,
        2,
        element_type="dispBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=3,
    )

    with pytest.raises(ValueError, match="not available for ndm=2"):
        validate_section_response_request(
            model,
            None,
            element_tag=3,
            section_number=1,
            component="My",
        )

    with pytest.raises(ValueError, match="valid locations are 1, 2, 3"):
        validate_section_response_request(
            model,
            None,
            element_tag=3,
            section_number=4,
            component="Mz",
        )


def test_classic_moment_curvature_reuses_generic_section_semantics():
    model = StructuralModel("classic-mk", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0)
    connection = ConnectionData(
        1,
        "Moment curvature section",
        "zeroLengthSection",
        1,
        2,
        section_tag=1,
    )
    analysis = AnalysisSettingsData(
        1,
        "Moment curvature",
        "Static",
        integrator="DisplacementControl",
        control_node=2,
        control_dof=3,
        displacement_increment=0.001,
    )

    spec = automatic_moment_curvature_spec(
        model,
        connections={1: connection},
        active_analysis=analysis,
    )

    assert spec is not None
    assert spec["key"] == "auto:moment-curvature"
    assert spec["component"] == "Mz"
    assert spec["force_index"] == 1
    assert spec["deformation_index"] == 1
    assert spec["query_mode"] == "direct"
    assert spec["automatic"] is True


def test_explicit_section_response_records_only_requested_beam_ip():
    model = StructuralModel("requested-section", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0)
    model.add_element(
        8,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=4,
    )
    analysis = AnalysisSettingsData(
        2,
        "Static",
        "Static",
        integrator="LoadControl",
        steps=2,
    )
    request = SimpleNamespace(
        analysis_tag=2,
        result_type="SectionResponse",
        element_scope=[8],
        settings={"section": 3, "component": "Mz"},
    )

    specs = build_section_response_specs(
        model,
        solution_results={9: request},
        active_analysis=analysis,
    )

    assert len(specs) == 1
    assert specs[0]["key"] == "request:9"
    assert specs[0]["element_tag"] == 8
    assert specs[0]["section_number"] == 3
    assert specs[0]["component"] == "Mz"
    assert specs[0]["query_mode"] == "indexed"


def test_generator_emits_indexed_section_response_only_for_request():
    model = StructuralModel("requested-section-script", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 0.0, 3.0)
    model.set_fixity(1, (1, 1, 1))
    model.add_element(
        8,
        1,
        2,
        element_type="forceBeamColumn",
        section_tag=1,
        transf_tag=1,
        integration_points=4,
    )
    sections = {
        1: SectionData(
            1,
            "Elastic section",
            "Elastic",
            parameters={
                "E": 30.0e9,
                "A": 0.1,
                "Iz": 1.0e-3,
                "Iy": 1.0e-3,
                "G": 12.0e9,
                "J": 1.0e-3,
            },
        )
    }
    transformations = {
        1: TransformationData(
            1,
            "Column",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    }
    analysis = AnalysisSettingsData(
        2,
        "Static",
        "Static",
        integrator="LoadControl",
        steps=2,
    )
    request = SolutionResultData(
        9,
        2,
        "Base M-kappa",
        "SectionResponse",
        element_scope=[8],
        settings={"section": 3, "component": "Mz"},
    )

    script = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
        analyses={2: analysis},
        active_analysis_tag=2,
        solution_results={9: request},
    )

    compile(script, "<generic-section-response>", "exec")
    assert "'request:9'" in script
    assert "'section_number': 3" in script
    assert "_studio_sr_section" in script
    assert (
        "ops.eleResponse(_studio_sr_element, 'section', "
        "_studio_sr_section, 'force')"
    ) in script
