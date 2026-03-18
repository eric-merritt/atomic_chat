"""Test that filesystem tools are importable from the tools package."""
import os
import tempfile


def test_filesystem_tools_importable():
    from tools.filesystem import FILESYSTEM_TOOLS
    assert len(FILESYSTEM_TOOLS) == 12
    names = {t.name for t in FILESYSTEM_TOOLS}
    assert "read" in names
    assert "write" in names
    assert "tree" in names
    assert "grep" not in names  # grep belongs to codesearch


def test_read_works():
    from tools.filesystem import read
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        path = f.name
    try:
        result = read.invoke({"path": path})
        assert "line1" in result
        assert "line2" in result
    finally:
        os.unlink(path)


def test_write_works():
    from tools.filesystem import write
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.txt")
        result = write.invoke({"path": path, "content": "hello"})
        assert "Wrote" in result
        with open(path) as f:
            assert f.read() == "hello"
