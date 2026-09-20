from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def _write_result(
    result_path: Path | None,
    *,
    status: str,
    namespace: dict[str, Any],
    error: str = "",
) -> None:
    if result_path is None:
        return

    payload = {
        "status": status,
        "error": error,
        "results": namespace.get("_studio_results", {}),
    }
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_script(
    script_path: Path,
    result_path: Path | None = None,
) -> int:
    if not script_path.exists():
        print(
            f"[Studio worker] Script not found: {script_path}",
            file=sys.stderr,
            flush=True,
        )
        _write_result(
            result_path,
            status="failed",
            namespace={},
            error=f"Script not found: {script_path}",
        )
        return 2

    print(f"[Studio worker] Running: {script_path}", flush=True)
    namespace: dict[str, Any] = {
        "__name__": "__main__",
        "__file__": str(script_path),
        "__package__": None,
    }

    try:
        source = script_path.read_text(encoding="utf-8")
        code = compile(source, str(script_path), "exec")
        exec(code, namespace)
    except SystemExit as exc:
        code_value = exc.code
        if code_value is None:
            _write_result(
                result_path,
                status="completed",
                namespace=namespace,
            )
            return 0
        if isinstance(code_value, int):
            status = "completed" if code_value == 0 else "failed"
            _write_result(
                result_path,
                status=status,
                namespace=namespace,
                error="" if code_value == 0 else f"SystemExit({code_value})",
            )
            return code_value
        message = str(code_value)
        print(message, file=sys.stderr, flush=True)
        _write_result(
            result_path,
            status="failed",
            namespace=namespace,
            error=message,
        )
        return 1
    except BaseException:
        error = traceback.format_exc()
        print(error, file=sys.stderr, flush=True)
        _write_result(
            result_path,
            status="failed",
            namespace=namespace,
            error=error,
        )
        return 1

    _write_result(
        result_path,
        status="completed",
        namespace=namespace,
    )
    print("[Studio worker] Completed successfully.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenSeesPy Studio analysis worker"
    )
    parser.add_argument("script", type=Path)
    parser.add_argument("--result-file", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_script(args.script, args.result_file)


if __name__ == "__main__":
    raise SystemExit(main())
