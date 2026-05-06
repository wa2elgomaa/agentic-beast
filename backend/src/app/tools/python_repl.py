"""Persistent Python REPL tool for Strands agents — uses SDK invocation state.

The sandbox (exec namespace) is stored in ``invocation_state["_sandbox"]`` so it
persists across all tool calls within one agent invocation without closures or
factory functions.

After ``db_tool`` injects data, the sandbox contains:
- ``rows``  — list of dicts (one per result row)
- ``df``    — pandas DataFrame of the same rows

To produce a chart, assign a matplotlib Figure to ``visualization`` and set
``visualization_caption`` to a description string. Both are read from
``invocation_state["_sandbox"]`` by AnalyticsAgent.execute() after the run.

Exported
--------
* ``python_repl`` — standalone Strands @tool, pass directly to Agent(tools=[...])
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from strands.tools import tool
from strands.types.tools import ToolContext


@tool(context=True)
def python_repl(code: str, tool_context: ToolContext) -> str:
    """Execute Python code in a persistent analytics sandbox.

    Variables persist across calls within one agent turn via SDK invocation state.
    After db_tool is called, the following are available:
    - rows  — list of dicts (one per result row)
    - df    — pandas DataFrame of the same rows

    To produce a chart, assign a matplotlib Figure to ``visualization``
    and set ``visualization_caption`` to a short description. Example:

    ```python
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    visualization_caption = "Top 5 videos by views on Instagram"
    visualization, ax = plt.subplots(figsize=(10, 4))
    ax.bar([r['content'] for r in rows], [r['video_views'] for r in rows])
    ax.set_title(visualization_caption)
    plt.tight_layout()
    ```

    Do NOT call plt.show() or save the figure to disk.

    Args:
        code: Python code to execute.
        tool_context: SDK-provided execution context (injected automatically).

    Returns:
        Captured stdout/stderr output.
    """
    sandbox = tool_context.invocation_state.setdefault("_sandbox", {})
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(code, sandbox)  # noqa: S102
    except Exception as exc:
        stderr_buf.write(f"\n[ExecutionError] {type(exc).__name__}: {exc}")

    # If the code assigned a matplotlib Figure to `visualization`, save it as a
    # base64 PNG and store in the process-level chart store (thread-safe).
    # Primary path: model assigned a Figure to `visualization`.
    # Fallback path: capture any open matplotlib figure (model may have used plt directly).
    fig = sandbox.get("visualization")
    if fig is None:
        # Fallback: if matplotlib was imported and has open figures, grab the current one.
        try:
            import matplotlib.pyplot as _mplt_check
            fignums = _mplt_check.get_fignums()
            if fignums:
                fig = _mplt_check.figure(fignums[-1])
        except Exception:
            pass

    if fig is not None:
        try:
            import io as _io
            import base64 as _base64
            import matplotlib.figure as _mfig
            import matplotlib.pyplot as _mplt

            if isinstance(fig, _mfig.Figure):
                buf = _io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
                buf.seek(0)
                chart_b64 = _base64.b64encode(buf.getvalue()).decode()
                chart_caption = str(sandbox.get("visualization_caption", "Analytics chart"))
                buf.close()
                _mplt.close(fig)
                # Store in sandbox for any in-process reader (best effort)
                sandbox["_chart_b64"] = chart_b64
                sandbox["_chart_caption"] = chart_caption
                # Primary store: process-level, thread-safe — accessible from any thread
                from app.tools.python_executor_tool import store_latest_chart
                store_latest_chart(chart_b64, chart_caption)
        except Exception:
            pass  # Chart capture is best-effort

    parts = []
    if stdout_buf.getvalue():
        parts.append(f"STDOUT:\n{stdout_buf.getvalue()}")
    if stderr_buf.getvalue():
        parts.append(f"STDERR:\n{stderr_buf.getvalue()}")
    output = "\n".join(parts) if parts else "Code executed successfully."

    # If the LLM printed a data URI in stdout (e.g. from manual base64 encoding),
    # intercept it: save to disk and strip it from the output so it doesn't bloat
    # the LLM context.  The URL is stored in the sandbox for AnalyticsAgent to pick up.
    if "data:image/" in output and "base64," in output and sandbox.get("_chart_b64") is None:
        try:
            import re as _re
            _m = _re.search(r'data:image/(?:png|jpeg|jpg);base64,([A-Za-z0-9+/=\n\r\s]+)', output)
            if _m:
                raw = _m.group(1).replace("\n", "").replace("\r", "").replace(" ", "")
                caption = str(sandbox.get("visualization_caption", "Analytics chart"))
                sandbox["_chart_b64"] = raw
                sandbox["_chart_caption"] = caption
                try:
                    from app.tools.python_executor_tool import store_latest_chart
                    store_latest_chart(raw, caption)
                except Exception:
                    pass
                # Strip the large data URI from output to avoid bloating the LLM context
                output = _re.sub(
                    r'!\[[^\]]*\]\(data:image/[^)]+\)|data:image/[^;]+;base64,[A-Za-z0-9+/=\n\r\s]+',
                    '[chart captured]',
                    output,
                )
        except Exception:
            pass

    return output
