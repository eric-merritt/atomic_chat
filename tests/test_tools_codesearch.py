"""Test that codesearch tools are importable and work."""
import os
import tempfile


def test_codesearch_tools_importable():
    from tools.codesearch import CODESEARCH_TOOLS
    assert len(CODESEARCH_TOOLS) == 3
    names = {t.name for t in CODESEARCH_TOOLS}
    assert names == {"grep", "find", "definition"}


def test_grep_works():
    from tools.codesearch import grep
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.py")
        with open(path, "w") as f:
            f.write("def hello():\n    return 'world'\n")
        result = grep.invoke({"pattern": "hello", "path": d})
        assert "hello" in result


def test_find_works():
    from tools.codesearch import find
    with tempfile.TemporaryDirectory() as d:
        for name in ["a.py", "b.py", "c.txt"]:
            open(os.path.join(d, name), "w").close()
        result = find.invoke({"pattern": "*.py", "path": d})
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result
