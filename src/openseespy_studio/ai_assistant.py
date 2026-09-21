from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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
needed, call a read-only tool. When the context focus names a node, element,
material, section, connection, or analysis tag, use the matching get_* tool
before diagnosing that object. When numerical results are truncated, say so.
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

    elif name == "get_node":
        try:
            tag = int(arguments["tag"])
        except (KeyError, TypeError, ValueError):
            result = {"error": "get_node requires an integer tag."}
        else:
            model = project.get("model", {})
            item = _tagged(
                model.get("nodes", []) if isinstance(model, dict) else [],
                tag,
            )
            if item is None:
                result = {"found": False, "tag": tag}
            else:
                connected_elements = [
                    int(element.get("tag"))
                    for element in model.get("elements", [])
                    if (
                        isinstance(element, dict)
                        and tag in {
                            int(element.get("i", -1)),
                            int(element.get("j", -1)),
                        }
                    )
                ]
                result = {
                    "found": True,
                    "node": item,
                    "connected_elements": connected_elements,
                    "nodal_loads": [
                        load
                        for load in project.get("nodal_loads", [])
                        if (
                            isinstance(load, dict)
                            and int(load.get("node_tag", -1)) == tag
                        )
                    ],
                    "prescribed_displacements": [
                        load
                        for load in project.get(
                            "prescribed_displacements",
                            [],
                        )
                        if (
                            isinstance(load, dict)
                            and int(load.get("node_tag", -1)) == tag
                        )
                    ],
                    "constraints": [
                        constraint
                        for constraint in project.get("constraints", [])
                        if (
                            isinstance(constraint, dict)
                            and (
                                int(constraint.get("retained_node", -1)) == tag
                                or tag in {
                                    int(value)
                                    for value in constraint.get(
                                        "constrained_nodes",
                                        [],
                                    )
                                }
                            )
                        )
                    ],
                }

    elif name == "get_element":
        try:
            tag = int(arguments["tag"])
        except (KeyError, TypeError, ValueError):
            result = {"error": "get_element requires an integer tag."}
        else:
            model = project.get("model", {})
            item = _tagged(
                model.get("elements", []) if isinstance(model, dict) else [],
                tag,
            )
            if item is None:
                result = {"found": False, "tag": tag}
            else:
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
                transf_tag = detail.get("transf_tag")
                if transf_tag is not None:
                    detail["transformation"] = _tagged(
                        project.get("transformations", []),
                        int(transf_tag),
                    )
                detail["element_loads"] = [
                    load
                    for load in project.get("element_loads", [])
                    if (
                        isinstance(load, dict)
                        and int(load.get("element_tag", -1)) == tag
                    )
                ]
                result = {"found": True, "element": detail}

    elif name == "get_connection":
        try:
            tag = int(arguments["tag"])
        except (KeyError, TypeError, ValueError):
            result = {"error": "get_connection requires an integer tag."}
        else:
            item = _tagged(project.get("connections", []), tag)
            if item is None:
                result = {"found": False, "tag": tag}
            else:
                detail = dict(item)
                section_tag = detail.get("section_tag")
                if section_tag is not None:
                    detail["section"] = _tagged(
                        project.get("sections", []),
                        int(section_tag),
                    )
                material_defs: dict[str, Any] = {}
                for dof, material_tag in dict(
                    detail.get("materials_by_dof", {})
                ).items():
                    material_defs[str(dof)] = _tagged(
                        project.get("materials", []),
                        int(material_tag),
                    )
                if material_defs:
                    detail["material_definitions_by_dof"] = material_defs
                result = {"found": True, "connection": detail}

    elif name == "get_material":
        try:
            tag = int(arguments["tag"])
        except (KeyError, TypeError, ValueError):
            result = {"error": "get_material requires an integer tag."}
        else:
            item = _tagged(project.get("materials", []), tag)
            result = (
                {"found": True, "material": item}
                if item is not None
                else {"found": False, "tag": tag}
            )

    elif name == "get_section":
        try:
            tag = int(arguments["tag"])
        except (KeyError, TypeError, ValueError):
            result = {"error": "get_section requires an integer tag."}
        else:
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
            try:
                tag = int(raw_tag)
            except (TypeError, ValueError):
                result = {"error": "get_analysis tag must be an integer."}
            else:
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
                try:
                    target = int(raw_job_id)
                except (TypeError, ValueError):
                    target = None
                    job = None
                else:
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
        "strict": False,
        "name": "get_model_summary",
        "description": (
            "Get SARE project/model dimensions, object counts, tag indexes, "
            "active analysis, and current focused tree object."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "strict": False,
        "name": "get_selection",
        "description": (
            "Get the currently selected nodes/elements and their model "
            "properties, including referenced section/material when available."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "strict": False,
        "name": "get_node",
        "description": "Get one SARE structural node by positive integer tag.",
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "integer", "minimum": 1}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "strict": False,
        "name": "get_element",
        "description": (
            "Get one SARE frame/truss element by tag, including its referenced "
            "section or truss material when available."
        ),
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "integer", "minimum": 1}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "strict": False,
        "name": "get_connection",
        "description": (
            "Get one SARE zeroLength, zeroLengthSection, or twoNodeLink "
            "connection by positive integer tag."
        ),
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "integer", "minimum": 1}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "strict": False,
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
        "strict": False,
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
        "strict": False,
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
        "strict": False,
        "name": "get_validation_issues",
        "description": "Get current SARE model-check errors, warnings, and suggestions.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "strict": False,
        "name": "get_solver_log",
        "description": "Get the tail of the current/recent SARE solver console output.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "strict": False,
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


def ollama_read_only_tools() -> list[dict[str, Any]]:
    """Convert SARE's read-only tool schemas to Ollama's chat-tool format."""
    result: list[dict[str, Any]] = []
    for tool in OPENAI_READ_ONLY_TOOLS:
        result.append({
            "type": "function",
            "function": {
                "name": str(tool.get("name", "")),
                "description": str(tool.get("description", "")),
                "parameters": dict(tool.get("parameters", {})),
            },
        })
    return result


def _validate_local_ollama_host(host: str) -> str:
    normalized = str(host).strip().rstrip("/") or "http://localhost:11434"
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(
            "Ollama host must use http:// or https://."
        )
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(
            "The free SARE Ollama provider is local-only. Use localhost, "
            "127.0.0.1, or ::1 so project context is not sent to a remote host."
        )
    return normalized


@dataclass(slots=True)
class OllamaProvider:
    """Free/local Ollama provider using the native /api/chat endpoint."""
    model: str = "qwen3.5:4b"
    host: str = "http://localhost:11434"
    max_tool_rounds: int = 6
    timeout: float = 180.0
    transport: Any | None = None

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.transport is not None:
            result = self.transport(path, payload)
            if not isinstance(result, dict):
                raise RuntimeError("Ollama transport returned invalid JSON.")
            return result

        host = _validate_local_ollama_host(self.host)
        url = host + "/" + str(path).lstrip("/")
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(self.timeout)) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            if exc.code == 404:
                raise RuntimeError(
                    f"Ollama model {self.model!r} is not installed. Run: "
                    f"ollama pull {self.model}"
                ) from exc
            raise RuntimeError(
                f"Ollama HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Cannot connect to local Ollama at "
                f"{host}. Install/start Ollama, then run "
                f"'ollama pull {self.model}'."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Local Ollama request failed: {exc}"
            ) from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Ollama returned a non-JSON response."
            ) from exc
        if not isinstance(result, dict):
            raise RuntimeError("Ollama returned invalid response data.")
        if result.get("error"):
            detail = str(result.get("error"))
            if "not found" in detail.lower():
                raise RuntimeError(
                    f"Ollama model {self.model!r} is not installed. Run: "
                    f"ollama pull {self.model}"
                )
            raise RuntimeError("Ollama error: " + detail)
        return result

    def ask(
        self,
        prompt: str,
        *,
        snapshot: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        _validate_local_ollama_host(self.host)
        model = str(self.model).strip()
        if not model:
            raise RuntimeError("Choose an Ollama model before sending.")

        focus = compact_for_llm(snapshot.get("focus"))
        context_note = (
            "SARE local context focus: " + _json_text(focus)
            if focus
            else "SARE local context focus: none."
        )
        instructions = SARE_AI_SYSTEM_PROMPT + "\n\n" + context_note

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
        ]
        for item in history or []:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": str(prompt)})

        tools = ollama_read_only_tools()
        for _round in range(max(1, int(self.max_tool_rounds))):
            response = self._post_json(
                "/api/chat",
                {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                },
            )
            raw_message = response.get("message", {})
            if not isinstance(raw_message, dict):
                raise RuntimeError("Ollama response has no valid message.")

            tool_calls = raw_message.get("tool_calls", []) or []
            if not isinstance(tool_calls, list):
                tool_calls = []

            if not tool_calls:
                content = str(raw_message.get("content", "") or "").strip()
                if not content:
                    raise RuntimeError(
                        "Ollama completed without text output. Use a model "
                        "with tool support, such as qwen3.5:4b."
                    )
                return content

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": str(raw_message.get("content", "") or ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for call in tool_calls:
                function = (
                    call.get("function", {})
                    if isinstance(call, dict)
                    else {}
                )
                if not isinstance(function, dict):
                    function = {}
                name = str(function.get("name", ""))
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                result = execute_read_only_tool(
                    name,
                    arguments,
                    snapshot,
                )
                messages.append({
                    "role": "tool",
                    "content": _json_text(result),
                })

        raise RuntimeError(
            "The local Ollama assistant exceeded the read-only tool-call "
            "round limit."
        )


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
            store=False,
        )

        for _round in range(max(1, int(self.max_tool_rounds))):
            response_output = list(
                getattr(response, "output", []) or []
            )
            calls = [
                item
                for item in response_output
                if getattr(item, "type", "") == "function_call"
            ]
            if not calls:
                text = str(getattr(response, "output_text", "") or "").strip()
                if not text:
                    raise RuntimeError(
                        "The LLM response completed without text output."
                    )
                return text

            # Keep the tool loop stateless. OpenAI's Responses API function-
            # calling guide recommends carrying response.output forward with
            # each function_call_output. This remains compatible with
            # store=False and also preserves reasoning items when present.
            conversation.extend(response_output)
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
                conversation.append({
                    "type": "function_call_output",
                    "call_id": str(getattr(call, "call_id", "")),
                    "output": _json_text(result),
                })

            response = client.responses.create(
                model=self.model,
                instructions=instructions,
                input=conversation,
                tools=OPENAI_READ_ONLY_TOOLS,
                store=False,
            )

        raise RuntimeError(
            "The assistant exceeded the read-only tool-call round limit."
        )
