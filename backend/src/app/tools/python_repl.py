"""A simple persistent Python REPL tool for Strands agents.

Provides a `PythonInterpreter` class that executes code in a persistent
namespace and a `get_python_repl()` helper that returns a Strands `Tool`.

This is intentionally minimal for testing and local development.
"""
from typing import Any
import io
import contextlib
import traceback
import textwrap
from pydantic import BaseModel, Field
from strands.tools import tool
from strands.types.tools import ToolResult, ToolUse

class PythonReplInput(BaseModel):
    code: str = Field(..., description="Python code to execute")


TOOL_SPEC = {
    "name": "python_repl",
    "description": textwrap.dedent(
        """
        Execute Python code in a persistent, sandboxed namespace.
        Preserves variables across calls and returns stdout and a short
        summary of created/updated variables. If a Matplotlib Figure named
        `visualization` is created, the tool will embed an SVG string
        in the textual response between <SVG>...</SVG> markers.
        """
    ),
    "inputSchema": {
        "json": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
    },
}


class PythonInterpreter:
    """Execute Python code with a persistent local namespace.

    NOTE: This is not hardened for untrusted execution. It's intended for
    development and CI-style smoke tests only.
    """

    def __init__(self) -> None:
        self._locals: dict[str, Any] = {}

    def run(self, code: str) -> str:
        """Execute `code` and return a text summary result."""
        stdout = io.StringIO()
        try:
            compiled = compile(code, "<python_repl>", "exec")
            with contextlib.redirect_stdout(stdout):
                exec(compiled, {}, self._locals)
        except Exception as exc:  # capture exception traceback
            tb = traceback.format_exc()
            return f"ERROR executing code:\n{tb}"

        out = stdout.getvalue()

        # Build a short summary of interesting variables
        keys = list(self._locals.keys())
        summary_lines = [f"OK. Executed code. Stdout:\n{out.strip()}" if out.strip() else "OK. Executed code."]
        if keys:
            summary_lines.append("Variables:")
            for k in keys:
                v = self._locals[k]
                try:
                    tname = type(v).__name__
                except Exception:
                    tname = "<unknown>"
                summary_lines.append(f" - {k}: {tname}")

        # If a Matplotlib Figure called `visualization` exists, export SVG
        if "visualization" in self._locals:
            try:
                fig = self._locals["visualization"]
                import matplotlib
                matplotlib.use("svg")
                import io as _io
                buf = _io.BytesIO()
                fig.savefig(buf, format="svg")
                svg_bytes = buf.getvalue()
                try:
                    svg_text = svg_bytes.decode("utf-8")
                except Exception:
                    svg_text = svg_bytes.decode("latin-1", errors="ignore")
                summary_lines.append("<SVG>\n" + svg_text + "\n</SVG>")
            except Exception as exc:  # if svg generation fails, include the error
                summary_lines.append(f"(visualization SVG generation failed: {exc})")

        return "\n".join(summary_lines)


@tool(name=TOOL_SPEC["name"], description=TOOL_SPEC["description"], inputSchema=TOOL_SPEC["inputSchema"]["json"])
def python_repl_tool(tool: ToolUse, **kwargs: Any) -> ToolResult:
    instance = PythonInterpreter()
    tool_input = dict(tool.get("input", {}))
    try:
        params = PythonReplInput(**tool_input)
    except Exception as exc:
        return {"toolUseId": tool.get("toolUseId"), "status": "error", "content": [{"text": f"Invalid input: {exc}"}]}

    result_text = instance.run(params.code)
    return {"toolUseId": tool.get("toolUseId"), "status": "success", "content": [{"text": result_text}]}
