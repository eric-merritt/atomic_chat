"""Test that filesystem tools are importable from the tools package."""
import os
import tempfile


def test_filesystem_tools_importable():
    from tools.filesystem import FILESYSTEM_TOOLS
    assert len(FILESYSTEM_TOOLS) == 13
    names = {t.name for t in FILESYSTEM_TOOLS}
    assert "read_file" in names
    assert "write_file" in names
    assert "tree" in names
    assert "grep" not in names  # grep belongs to codesearch


def test_read_file_works():
    from tools.filesystem import read_file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        path = f.name
    try:
        result = read_file.invoke({"path": path})
        assert "line1" in result
        assert "line2" in result
    finally:
        os.unlink(path)


def test_write_file_works():
    from tools.filesystem import write_file
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.txt")
        result = write_file.invoke({"path": path, "content": "hello"})
        assert "Wrote" in result
        with open(path) as f:
            assert f.read() == "hello"
