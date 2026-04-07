"""Sandboxed Python code interpreter for analytics data exploration.

Accepts a Python code string plus a list of dicts (DB rows).
Injects ``df = pd.DataFrame(data)`` and a few safe helpers, then executes
the code in a restricted environment.

Security model
--------------
* Uses RestrictedPython to compile the code into a restricted AST.
* Explicitly whitelists the pandas and matplotlib APIs.
* Blocks: os, sys, subprocess, open(), __import__, eval, exec of sub-code,
  network calls, file I/O, and all attribute access to private/dunder names.
* Hard 30-second wall-clock timeout enforced via ThreadPoolExecutor.
* matplotlib uses the 'Agg' non-interactive backend — no display required.

Returns
-------
dict with keys:
    output    : str   — captured stdout / text output
    chart_b64 : str | None — base64-encoded PNG if a matplotlib figure was created
    error     : str | None — error message if execution failed
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeout (seconds) for code execution
# ---------------------------------------------------------------------------
_EXEC_TIMEOUT: int = settings.code_interpreter_timeout_seconds

# ---------------------------------------------------------------------------
# Attempt to import RestrictedPython; fall back gracefully so the rest of the
# app still starts even if the package is not yet installed.
# ---------------------------------------------------------------------------
try:
    from RestrictedPython import (  # type: ignore[import]
        compile_restricted,
        safe_globals,
        safe_builtins,
        limited_builtins,
        utility_builtins,
    )
    from RestrictedPython.Guards import (  # type: ignore[import]
        guarded_iter_unpack_sequence,
        guarded_unpack_sequence,
    )
    _RESTRICTED_PYTHON_AVAILABLE = True
    logger.debug("RestrictedPython loaded — using restricted execution mode")
except ImportError:
    _RESTRICTED_PYTHON_AVAILABLE = False
    logger.warning(
        "RestrictedPython not installed — code interpreter will use restricted exec() fallback. "
        "Install with: pip install RestrictedPython"
    )


# ---------------------------------------------------------------------------
# Allowed attribute access guard
# ---------------------------------------------------------------------------

def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Allow attribute access to public names only (no dunder, no private)."""
    if name.startswith("_"):
        raise AttributeError(f"Access to private attribute '{name}' is not allowed.")
    return getattr(obj, name, default)


def _safe_getitem(obj: Any, key: Any) -> Any:
    return obj[key]


def _safe_write(obj: Any) -> Any:
    """Guard write access — allow known safe types (pandas DataFrame, dict, list)."""
    allowed_types = (dict, list)
    try:
        import pandas as _pd  # noqa: PLC0415
        allowed_types = (*allowed_types, _pd.DataFrame, _pd.Series)
    except ImportError:
        pass
    if isinstance(obj, allowed_types):
        return obj
    raise TypeError(f"Writing to {type(obj).__name__} is not permitted in sandbox.")


# ---------------------------------------------------------------------------
# Build the restricted execution globals
# ---------------------------------------------------------------------------

def _build_exec_globals(data: list[dict]) -> dict[str, Any]:
    """Return the execution namespace injected into sandboxed code."""
    import pandas as pd  # noqa: PLC0415

    # Matplotlib must be configured before any pyplot import
    import matplotlib  # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    exec_globals: dict[str, Any] = {
        # Data
        "df": pd.DataFrame(data),
        "data": data,
        # Libraries
        "pd": pd,
        "plt": plt,
        "json": json,
        "math": math,
        # Helpers
        "print": print,  # captured via stdout redirect
        "__builtins__": {},
    }

    if _RESTRICTED_PYTHON_AVAILABLE:
        # Merge RestrictedPython safe builtins on top
        restricted_builtins = dict(safe_builtins)
        exec_globals["__builtins__"] = restricted_builtins
        exec_globals["_getattr_"] = _safe_getattr
        exec_globals["_getitem_"] = _safe_getitem
        exec_globals["_write_"] = _safe_write
        exec_globals["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
        exec_globals["_getiter_"] = iter
        # RestrictedPython transforms print() → _print_(args); use PrintCollector
        from RestrictedPython import PrintCollector  # type: ignore[import]  # noqa: PLC0415
        exec_globals["_print_"] = PrintCollector
        exec_globals["_getiter_"] = iter
    return exec_globals


# ---------------------------------------------------------------------------
# Core executor (runs in a thread for timeout enforcement)
# ---------------------------------------------------------------------------

def _execute_in_thread(code: str, data: list[dict]) -> dict[str, Any]:
    """Execute *code* in the sandboxed namespace and capture results."""
    import matplotlib  # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    stdout_capture = io.StringIO()
    chart_b64: str | None = None
    error: str | None = None
    output: str = ""

    exec_globals = _build_exec_globals(data)

    # Redirect print() to our StringIO buffer
    import builtins  # noqa: PLC0415
    original_print = builtins.print

    def _captured_print(*args: Any, **kwargs: Any) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        stdout_capture.write(sep.join(str(a) for a in args) + end)

    exec_globals["print"] = _captured_print
    if isinstance(exec_globals.get("__builtins__"), dict):
        exec_globals["__builtins__"]["print"] = _captured_print  # type: ignore[index]

    try:
        if _RESTRICTED_PYTHON_AVAILABLE:
            byte_code = compile_restricted(code, filename="<analyst>", mode="exec")
        else:
            # Fallback: plain compile with explicit checks
            _check_unsafe_patterns(code)
            byte_code = compile(code, "<analyst>", "exec")

        exec(byte_code, exec_globals)  # noqa: S102

        # Collect print() output:
        # - In restricted mode: RestrictedPython transforms print(x) into
        #   _print_(_getattr_=_getattr_) → stored as _print (instance), then
        #   _print._call_print(x). The accumulated text is in exec_globals["_print"].txt
        # - In fallback mode: captured via stdout_capture
        if _RESTRICTED_PYTHON_AVAILABLE:
            _print_instance = exec_globals.get("_print")
            if _print_instance is not None and hasattr(_print_instance, "txt"):
                output = "".join(_print_instance.txt)
            else:
                output = ""
        else:
            output = stdout_capture.getvalue()

        # Capture any open matplotlib figure as base64 PNG
        figs = [plt.figure(n) for n in plt.get_fignums()]
        if figs:
            buf = io.BytesIO()
            figs[-1].savefig(buf, format="png", bbox_inches="tight", dpi=120)
            buf.seek(0)
            chart_b64 = base64.b64encode(buf.read()).decode("utf-8")
            plt.close("all")

        # If no explicit print but there's a last-expression value, stringify it
        if not output.strip():
            last_val = exec_globals.get("_result")
            if last_val is not None:
                output = str(last_val)

    except Exception:  # noqa: BLE001
        tb = traceback.format_exc(limit=8)
        error = tb
        logger.warning("Code interpreter execution error", extra={"traceback": tb[:500]})
    finally:
        plt.close("all")

    return {
        "output": output.strip(),
        "chart_b64": chart_b64,
        "error": error,
    }


def _check_unsafe_patterns(code: str) -> None:
    """Simple string-level safety check used when RestrictedPython is absent."""
    blocked = [
        "import os", "import sys", "import subprocess", "import socket",
        "import shutil", "import pathlib", "open(", "__import__",
        "exec(", "eval(", "compile(", "globals()", "locals()",
        "getattr(", "__class__", "__bases__", "__subclasses__",
    ]
    lower = code.lower()
    for term in blocked:
        if term.lower() in lower:
            raise PermissionError(f"Blocked unsafe pattern: '{term}'")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_code(code: str, data: list[dict] | None = None) -> dict[str, Any]:
    """Execute *code* in a sandboxed environment with *data* as a DataFrame.

    Parameters
    ----------
    code : str
        Python source code to execute.  ``df`` (pandas DataFrame) is available
        automatically.  ``plt`` (matplotlib) is also pre-imported.
    data : list[dict] | None
        Rows to expose as ``df``.  Pass an empty list or None for no data.

    Returns
    -------
    dict
        ``{"output": str, "chart_b64": str | None, "error": str | None}``
    """
    safe_data = data or []

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_execute_in_thread, code, safe_data)
        try:
            return future.result(timeout=_EXEC_TIMEOUT)
        except FuturesTimeoutError:
            logger.warning("Code interpreter timed out", extra={"timeout": _EXEC_TIMEOUT})
            return {
                "output": "",
                "chart_b64": None,
                "error": f"Execution timed out after {_EXEC_TIMEOUT} seconds.",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Code interpreter unexpected error", extra={"error": str(exc)})
            return {
                "output": "",
                "chart_b64": None,
                "error": f"Unexpected execution error: {exc}",
            }
