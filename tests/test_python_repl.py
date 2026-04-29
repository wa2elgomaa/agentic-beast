import re

import importlib.util as iu
import pathlib

# Load module directly to avoid importing package init which pulls heavy dependencies
spec = iu.spec_from_file_location(
    "python_repl",
    str(pathlib.Path("backend") / "src" / "app" / "tools" / "python_repl.py"),
)
mod = iu.module_from_spec(spec)
spec.loader.exec_module(mod)
PythonInterpreter = mod.PythonInterpreter


def test_python_repl_basic_execution():
    interp = PythonInterpreter()
    res = interp.run('x = 1\nprint(x)')
    assert 'OK. Executed code' in res
    assert 'Variables:' in res
    assert re.search(r"\b x:\b|\bx:\b", res) or 'x' in res


def test_python_repl_visualization_svg():
    import pytest
    pytest.importorskip("matplotlib")
    interp = PythonInterpreter()
    code = (
        "import matplotlib\n"
        "matplotlib.use('svg')\n"
        "import matplotlib.pyplot as plt\n"
        "visualization, ax = plt.subplots(1,1)\n"
        "ax.plot([1,2,3],[1,4,9])\n"
        "visualization_caption = 'test caption'\n"
    )
    res = interp.run(code)
    assert '<SVG>' in res and '</SVG>' in res
    assert 'visualization' in res
