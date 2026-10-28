"""Tests for filesystem_object_enumerator.core.

Tests build a temporary tree on disk, call enumerate_filesystem, and
assert on the returned list. No wall-clock dependency, no network.
"""

from __future__ import annotations

import os
import unittest
import tempfile

from filesystem_object_enumerator import enumerate_filesystem, ObjectKind, ObjectInfo
from filesystem_object_enumerator.core import _kind_from_stat


def _make_tree() -> str:
    """Create a temporary tree and return its root path.

    Layout::

        root/
          a.txt           (4 bytes)
          b/
            c.txt         (3 bytes)
            d/
              e.txt       (2 bytes)
          f/
            (empty)
    """
    root = tempfile.mkdtemp(prefix="foe_test_")
    os.makedirs(os.path.join(root, "b", "d"))
    os.makedirs(os.path.join(root, "f"))
    with open(os.path.join(root, "a.txt"), "wb") as f:
        f.write(b"data")
    with open(os.path.join(root, "b", "c.txt"), "wb") as f:
        f.write(b"abc")
    with open(os.path.join(root, "b", "d", "e.txt"), "wb") as f:
        f.write(b"xy")
    return root


def _by_rel(infos: list[ObjectInfo], rel: str) -> ObjectInfo | None:
    for i in infos:
        if i.relative_path == rel:
            return i
    return None


class TestEnumerateFilesystem(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _make_tree()

    def test_returns_list(self) -> None:
        infos = enumerate_filesystem(self.root)
        self.assertIsInstance(infos, list)

    def test_root_not_included(self) -> None:
        infos = enumerate_filesystem(self.root)
        self.assertEqual(_by_rel(infos, "."), None)
        self.assertEqual(_by_rel(infos, ""), None)

    def test_counts_all_objects(self) -> None:
        infos = enumerate_filesystem(self.root)
        # a.txt, b, b/c.txt, b/d, b/d/e.txt, f  -> 6 objects.
        self.assertEqual(len(infos), 6)

    def test_file_kind_and_size(self) -> None:
        infos = enumerate_filesystem(self.root)
        a = _by_rel(infos, "a.txt")
        assert a is not None, "a.txt missing"
        self.assertEqual(a.kind, ObjectKind.FILE)
        self.assertEqual(a.size, 4)
        self.assertTrue(a.path.endswith("a.txt"))

    def test_directory_kind_and_size(self) -> None:
        infos = enumerate_filesystem(self.root)
        b = _by_rel(infos, "b")
        assert b is not None, "b missing"
        self.assertEqual(b.kind, ObjectKind.DIRECTORY)
        self.assertGreaterEqual(b.size, 0)

    def test_empty_directory(self) -> None:
        infos = enumerate_filesystem(self.root)
        f = _by_rel(infos, "f")
        assert f is not None, "f missing"
        self.assertEqual(f.kind, ObjectKind.DIRECTORY)
        self.assertGreaterEqual(f.size, 0)

    def test_nested_file(self) -> None:
        infos = enumerate_filesystem(self.root)
        e = _by_rel(infos, os.path.join("b", "d", "e.txt"))
        assert e is not None, "nested e.txt missing"
        self.assertEqual(e.kind, ObjectKind.FILE)
        self.assertEqual(e.size, 2)

    def test_sorted_within_directory(self) -> None:
        """At each directory level, entries come back sorted by name."""
        infos = enumerate_filesystem(self.root)
        rels = [i.relative_path for i in infos]
        # 'a.txt' sorts before 'b' before 'f' at the top level.
        top_level = [r for r in rels if os.sep not in r]
        self.assertEqual(top_level, sorted(top_level))

    def test_absolute_path_consistency(self) -> None:
        infos = enumerate_filesystem(self.root)
        for i in infos:
            self.assertTrue(
                os.path.isabs(i.path),
                f"path not absolute: {i.path}",
            )

    def test_nonexistent_root_returns_empty(self) -> None:
        infos = enumerate_filesystem(os.path.join(self.root, "does_not_exist"))
        self.assertEqual(infos, [])

    def test_file_root_returns_empty(self) -> None:
        """A root that is itself a file is not enumerable, so return []."""
        file_root = os.path.join(self.root, "a.txt")
        infos = enumerate_filesystem(file_root)
        self.assertEqual(infos, [])

    def test_broken_symlink(self) -> None:
        link = os.path.join(self.root, "broken.lnk")
        target = os.path.join(self.root, "nope")
        os.symlink(target, link)
        infos = enumerate_filesystem(self.root)
        b = _by_rel(infos, "broken.lnk")
        assert b is not None, "broken.lnk missing"
        self.assertEqual(b.kind, ObjectKind.BROKEN_LINK)
        self.assertEqual(b.size, -1)

    def test_symlink_to_file_resolves_to_file(self) -> None:
        target = os.path.join(self.root, "a.txt")
        link = os.path.join(self.root, "a_link.lnk")
        os.symlink(target, link)
        infos = enumerate_filesystem(self.root)
        x = _by_rel(infos, "a_link.lnk")
        assert x is not None, "a_link.lnk missing"
        self.assertEqual(x.kind, ObjectKind.FILE)
        self.assertEqual(x.size, 4)

    def test_symlink_to_dir_resolves_to_directory(self) -> None:
        target = os.path.join(self.root, "b")
        link = os.path.join(self.root, "b_link.lnk")
        os.symlink(target, link)
        infos = enumerate_filesystem(self.root)
        x = _by_rel(infos, "b_link.lnk")
        assert x is not None, "b_link.lnk missing"
        self.assertEqual(x.kind, ObjectKind.DIRECTORY)


class TestKindFromStat(unittest.TestCase):
    def test_broken_when_stat_failed(self) -> None:
        self.assertEqual(_kind_from_stat(None, False), ObjectKind.BROKEN_LINK)


if __name__ == "__main__":
    unittest.main()
