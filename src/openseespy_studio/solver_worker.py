from __future__ import annotations

import argparse
import runpy
import sys
import traceback
from pathlib import Path


def run_script(script_path: Path) -> int:
    if not script_path.exists():
        print(f"[Studio worker] Script not found: {script_path}", file=sys.stderr, flush=True)
        return 2

    print(f"[Studio worker] Running: {script_path}", flush=True)
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(str(code), file=sys.stderr, flush=True)
        return 1
    except BaseException:
        traceback.print_exc()
        return 1

    print("[Studio worker] Completed successfully.", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenSeesPy Studio analysis worker")
    parser.add_argument("script", type=Path)
    args = parser.parse_args()
    return run_script(args.script)


if __name__ == "__main__":
    raise SystemExit(main())
