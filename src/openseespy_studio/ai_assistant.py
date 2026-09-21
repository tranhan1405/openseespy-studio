from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol


SARE_AI_SYSTEM_PROMPT = """You are the read-only engineering assistant embedded in SARE,
the Structural Analysis & Research Environment for OpenSeesPy.

Use the available tools to inspect the SARE project before making claims about
the current model. Be concise, technical, and explicit about uncertainty.
Distinguish OpenSees/SARE model-definition problems from solver/runtime
problems. Never claim that you modified, fixed, ran, or saved the model: this
assistant is read-only. Do not invent tags, properties, results, validation
issues, convergence histories, or solver messages.

For structural-engineering questions, state the relevant model evidence and
then explain the likely cause or implication. If more model information is
needed, call a read-only tool. When numerical results are truncated, say so.
"""


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _tagged(items: Any, tag: int) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    target = int(tag)
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            if int(item.get("tag", -1)) == target:
                return dict(item)
        except (TypeError, ValueError):
            continue
    return None


def compact_for_llm(
    value: Any,
    *,
    max_depth: int = 5,
    max_items: int = 40,
    max_string: int = 12000,
    _depth: int = 0,
) -> Any:
    """Bound tool output so a large FE model/result cannot flood the prompt."""
    if _depth >= max_depth:
        if isinstance(value, dict):
            return {"_truncated": f"{len(value)} keys"}
        if isinstance(value, (list, tuple)):
            return {"_truncated": f"{len(value)} items"}
        return value

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[-max_string:] + "\n[earlier text omitted]"

    if isinstance(value, dict):
        items = list(value.items())
        result = {
            str(key): compact_for_llm(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
                _depth=_depth + 1,
            )
            for key, item in items[:max_items]
        }
        if len(items) > max_items:
            result["_omitted_keys"] = len(items) - max_items
        return result

    if isinstance(value, (list, tuple)):
        values = list(value)
        result = [
            compact_for_llm(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
                _depth=_depth + 1,
            )
            for item in values[:max_items]
        ]
        if len(values) > max_items:
            result.append({"_omitted_items": len(values) - max_items})
        return result

    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def prepare_project_snapshot(project: dict[str, Any]) -> dict[str, Any]:
    """Make a read-only project snapshot suitable for local AI tool lookup."""
    payload = dict(project)
    model = dict(payload.get("model", {}))
    payload["model"] = model

    # Ground-motion arrays can contain tens of thousands of values. The MVP
    # exposes useful metadata/sample values without copying whole records into
    # an LLM tool response.
    compact_series: list[dict[str, Any]] = []
    for raw in payload.get("time_series", []):
        item = dict(raw)
        values = list(item.pop("values", []) or [])
        if values:
            numeric = [float(value) for value in values]
            item["value_summary"] = {
                "count": len(numeric),
                "min": min(numeric),
                "max": max(numeric),
                "first": numeric[:8],
                "last": numeric[-8:] if len(numeric) > 8 else [],
            }
        compact_series.append(item)
    payload["time_series"] = compact_series

    compact_sections: list[dict[str, Any]] = []
    for raw in payload.get("sections", []):
        item = dict(raw)
        fibers = list(item.get("fibers", []) or [])
        if len(fibers) > 80:
            item["fiber_count"] = len(fibers)
            item["fibers"] = fibers[:40]
            item["fibers_truncated"] = True
        compact_sections.append(item)
    payload["sections"] = compact_sections
    return payload


def project_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    project = snapshot.get("project", {})
    model = project.get("model", {}) if isinstance(project, dict) else {}
    analyses = project.get("analyses", []) if isinstance(project, dict) else []
    materials = project.get("materials", []) if isinstance(project, dict) else []
    sections = project.get("sections", []) if isinstance(project, dict) else []
    return {
        "project_name": project.get("name", "Untitled"),
        "units": project.get("units", {}),
        "model": {
            "name": model.get("name", ""),
            "ndm": model.get("ndm"),
            "ndf": model.get("ndf"),
            "node_count": len(model.get("nodes", []) or []),
            "element_count": len(model.get("elements", []) or []),
        },
        "counts": {
            "materials": len(materials or []),
            "sections": len(sections or []),
            "transformations": len(project.get("transformations", []) or []),
            "constraints": len(project.get("constraints", []) or []),
            "connections": len(project.get("connections", []) or []),
            "time_series": len(project.get("time_series", []) or []),
            "load_patterns": len(project.get("load_patterns", []) or []),
            "nodal_loads": len(project.get("nodal_loads", []) or []),
            "element_loads": len(project.get("element_loads", []) or []),
            "analyses": len(analyses or []),
            "recorders": len(project.get("recorders", []) or []),
        },
        "material_index": [
            {
                "tag": item.get("tag"),
                "name": item.get("name"),
                "type": item.get("material_type"),
            }
            for item in materials
            if isinstance(item, dict)
        ],
        "section_index": [
            {
                "tag": item.get("tag"),
                "name": item.get("name"),
                "type": item.get("section_type"),
            }
            for item in sections
            if isinstance(item, dict)
        ],
        "analysis_index": [
            {
                "tag": item.get("tag"),
                "name": item.get("name"),
                "type": item.get("analysis_type"),
            }
            for item in analyses
            if isinstance(item, dict)
        ],
        "active_analysis_tag": project.get("active_analysis_tag"),
        "focus": snapshot.get("focus"),
    }


def _selection_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    selection = snapshot.get("selection")
    if not isinstance(selection, dict):
        return {"available": False, "reason": "Selection context is disabled."}

    project = snapshot.get("project", {})
    model = project.get("model", {}) if isinstance(project, dict) else {}
    nodes = model.get("nodes", []) if isinstance(model, dict) else []
    elements = model.get("elements", []) if isinstance(model, dict) else []

    node_tags = [int(tag) for tag in selection.get("nodes", [])]
    element_tags = [int(tag) for tag in selection.get("elements", [])]
    node_details = [
        item for tag in node_tags
        if (item := _tagged(nodes, tag)) is not None
    ]
    element_details: list[dict[str, Any]] = []
    for tag in element_tags:
        item = _tagged(elements, tag)
        if item is None:
            continue
        detail = dict(item)
        section_tag = detail.get("section_tag")
        material_tag = detail.get("truss_material_tag")
        if section_tag is not None:
            detail["section"] = _tagged(
                project.get("sections", []),
                int(section_tag),
            )
        if material_tag is not None:
            detail["material"] = _tagged(
                project.get("materials", []),
                int(material_tag),
            )
        element_details.append(detail)

    return {
        "available": True,
        "node_tags": node_tags,
        "element_tags": element_tags,
        "nodes": node_details,
        "elements": element_details,
        "focus": snapshot.get("focus"),
    }


def execute_read_only_tool(
    name: str,
    arguments: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Execute one SARE read-only AI tool against an immutable snapshot."""
    project = snapshot.get("project", {})
    if not isinstance(project, dict):
        project = {}

    if name == "get_model_summary":
        result: Any = project_summary(snapshot)

    elif name == "get_selection":
        result = _selection_detail(snapshot)

    elif name == "get_material":
        tag = int(arguments["tag"])
        item = _tagged(project.get("materials", []), tag)
        result = (
            {"found": True, "material": item}
            if item is not None
            else {"found": False, "tag": tag}
        )

    elif name == "get_section":
        tag = int(arguments["tag"])
        item = _tagged(project.get("sections", []), tag)
        result = (
            {"found": True, "section": item}
            if item is not None
            else {"found": False, "tag": tag}
        )

    elif name == "get_analysis":
        raw_tag = arguments.get("tag")
        if raw_tag is None:
            raw_tag = project.get("active_analysis_tag")
        if raw_tag is None:
            result = {"found": False, "reason": "No active analysis."}
        else:
            tag = int(raw_tag)
            item = _tagged(project.get("analyses", []), tag)
            result = (
                {"found": True, "analysis": item}
                if item is not None
                else {"found": False, "tag": tag}
            )

    elif name == "get_validation_issues":
        if "validation" not in snapshot:
            result = {
                "available": False,
                "reason": "Validation context is disabled.",
            }
        else:
            result = {
                "available": True,
                "issues": snapshot.get("validation", []),
            }

    elif name == "get_solver_log":
        if "solver_log" not in snapshot:
            result = {
                "available": False,
                "reason": "Solver-log context is disabled.",
            }
        else:
            result = {
                "available": True,
                "tail": snapshot.get("solver_log", ""),
            }

    elif name == "get_job_results":
        jobs = snapshot.get("jobs")
        if not isinstance(jobs, list):
            result = {
                "available": False,
                "reason": "Job context is disabled.",
            }
        elif not jobs:
            result = {"available": True, "found": False, "reason": "No jobs."}
        else:
            raw_job_id = arguments.get("job_id")
            if raw_job_id is None:
                job = jobs[-1]
            else:
                target = int(raw_job_id)
                job = next(
                    (
                        item for item in jobs
                        if int(item.get("job_id", -1)) == target
                    ),
                    None,
                )
            if job is None:
                result = {
                    "available": True,
                    "found": False,
                    "job_id": raw_job_id,
                }
            else:
                result = {
                    "available": True,
                    "found": True,
                    "job": job,
                }

    else:
        result = {"error": f"Unknown read-only SARE tool: {name}"}

    return compact_for_llm(result)


OPENAI_READ_ONLY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_model_summary",
        "description": (
            "Get SARE project/model dimensions, object counts, tag indexes, "
            "active analysis, and current focused tree object."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_selection",
        "description": (
            "Get the currently selected nodes/elements and their model "
            "properties, including referenced section/material when available."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_material",
        "description": "Get one SARE material definition by positive integer tag.",
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "integer", "minimum": 1}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_section",
        "description": "Get one SARE section definition by positive integer tag.",
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "integer", "minimum": 1}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_analysis",
        "description": (
            "Get an analysis definition by tag. Omit tag to inspect the active "
            "analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": ["integer", "null"], "minimum": 1}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_validation_issues",
        "description": "Get current SARE model-check errors, warnings, and suggestions.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_solver_log",
        "description": "Get the tail of the current/recent SARE solver console output.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_job_results",
        "description": (
            "Get a compact completed/running Job record and captured result "
            "data. Omit job_id for the latest available Job."
        ),
        "parameters": {
            "type": "object",
            "properties": {"job_id": {"type": ["integer", "null"], "minimum": 1}},
            "additionalProperties": False,
        },
    },
]


class LLMProvider(Protocol):
    def ask(
        self,
        prompt: str,
        *,
        snapshot: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        ...


@dataclass(slots=True)
class OpenAIProvider:
    model: str = "gpt-5.6-luna"
    api_key: str | None = None
    max_tool_rounds: int = 6
    client: Any | None = None

    def _client(self):
        if self.client is not None:
            return self.client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI Python SDK is not installed. Reinstall/update the "
                "SARE project dependencies (pip install -e .)."
            ) from exc

        key = (self.api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise RuntimeError(
                "No OpenAI API key is configured. Set OPENAI_API_KEY or enter "
                "an API key in the SARE AI Assistant panel. The panel key is "
                "used for this session only."
            )
        return OpenAI(api_key=key)

    def ask(
        self,
        prompt: str,
        *,
        snapshot: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        client = self._client()
        conversation: list[dict[str, str]] = []
        for item in history or []:
            role = str(item.get("role", "")).strip()
            text = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and text:
                conversation.append({"role": role, "content": text})
        conversation.append({"role": "user", "content": str(prompt)})

        focus = compact_for_llm(snapshot.get("focus"))
        context_note = (
            "SARE local context focus: " + _json_text(focus)
            if focus
            else "SARE local context focus: none."
        )
        instructions = SARE_AI_SYSTEM_PROMPT + "\n\n" + context_note

        response = client.responses.create(
            model=self.model,
            instructions=instructions,
            input=conversation,
            tools=OPENAI_READ_ONLY_TOOLS,
        )

        for _round in range(max(1, int(self.max_tool_rounds))):
            calls = [
                item
                for item in getattr(response, "output", []) or []
                if getattr(item, "type", "") == "function_call"
            ]
            if not calls:
                text = str(getattr(response, "output_text", "") or "").strip()
                if not text:
                    raise RuntimeError(
                        "The LLM response completed without text output."
                    )
                return text

            outputs: list[dict[str, str]] = []
            for call in calls:
                raw_arguments = getattr(call, "arguments", "{}") or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                result = execute_read_only_tool(
                    str(getattr(call, "name", "")),
                    arguments,
                    snapshot,
                )
                outputs.append({
                    "type": "function_call_output",
                    "call_id": str(getattr(call, "call_id", "")),
                    "output": _json_text(result),
                })

            response = client.responses.create(
                model=self.model,
                instructions=instructions,
                previous_response_id=str(getattr(response, "id", "")),
                input=outputs,
                tools=OPENAI_READ_ONLY_TOOLS,
            )

        raise RuntimeError(
            "The assistant exceeded the read-only tool-call round limit."
        )
