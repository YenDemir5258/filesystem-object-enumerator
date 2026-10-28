"""Single-pass enumeration of filesystem objects under a root path.

We use a manual stack instead of os.walk so the traversal order is
deterministic (sorted by name within each directory) and a single
stat-per-object is required. os.stat is preferred over os.lstat
because symlink targets are the more useful default for a size-and-type
reporter; broken or looping links report as broken_link rather than
raising.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath


class ObjectKind(str, Enum):
    """The resolved category of a filesystem object.

    The category reflects the post-symlink-referent state where that
    makes sense. A symlink whose target is a directory is classified
    as 'directory', because that is how it behaves when traversed.
    A symlink whose target does not exist is 'broken_link'.
    """

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"
    BROKEN_LINK = "broken_link"


@dataclass(frozen=True)
class ObjectInfo:
    """One filesystem object found during enumeration.

    - path: object's absolute filesystem path.
    - relative_path: path relative to the enumeration root, using
      os.sep. Always non-empty because the root itself is excluded.
    - kind: resolved ObjectKind.
    - size: st_size for files and directories (as reported by stat);
      -1 when the size cannot be determined (e.g. broken symlink).
    """

    path: str
    relative_path: str
    kind: ObjectKind
    size: int


def _kind_from_stat(st: os.stat_result, stat_succeeded: bool) -> ObjectKind:
    """Classify a stat result, falling back when the stat failed."""
    if not stat_succeeded:
        return ObjectKind.BROKEN_LINK
    mode = st.st_mode
    if stat.S_ISDIR(mode):
        return ObjectKind.DIRECTORY
    if stat.S_ISREG(mode):
        return ObjectKind.FILE
    if stat.S_ISLNK(mode):
        return ObjectKind.SYMLINK
    return ObjectKind.OTHER


def enumerate_filesystem(
    root: str | os.PathLike[str],
) -> list[ObjectInfo]:
    """Enumerate every filesystem object beneath ``root`` in one pass.

    The root itself is NOT included. Children are returned in
    depth-first, name-sorted order. Each object is stat-resolved:
    symlinks point at their referent's kind/size when the referent
    exists, otherwise the kind is BROKEN_LINK and size is -1.

    Returns a concrete list rather than a generator because callers
    typically need the full collection for sorting, deduplication, or
    serialization; a lazy iterator would be a worse fit here.
    """
    root_str = os.fspath(root)
    root_norm = os.path.abspath(root_str)
    if not os.path.isdir(root_norm):
        return []

    results: list[ObjectInfo] = []
    # Each queue entry is an absolute directory path we still need to
    # walk. Using a queue (pop from front) keeps the output strictly
    # ordered (children sorted by name at each level) and avoids
    # os.walk's dir-results mutation dance.
    queue: list[str] = [root_norm]

    while queue:
        current = queue.pop(0)
        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name)
        except OSError:
            # Directory became unreadable between discovery and now;
            # skip it rather than aborting the whole enumeration.
            continue

        # Walk entries in sorted order. Directories are appended to
        # the queue for traversal; non-directories are emitted
        # immediately.
        next_dirs: list[str] = []
        for entry in entries:
            entry_path = entry.path
            rel = os.path.relpath(entry_path, root_norm)

            stat_succeeded = True
            try:
                st = entry.stat(follow_symlinks=True)
            except OSError:
                st = None
                stat_succeeded = False

            kind = _kind_from_stat(st, stat_succeeded)
            size = st.st_size if (stat_succeeded and st is not None) else -1

            results.append(
                ObjectInfo(
                    path=entry_path,
                    relative_path=rel,
                    kind=kind,
                    size=size,
                )
            )

            if kind is ObjectKind.DIRECTORY:
                next_dirs.append(entry_path)

        for d in next_dirs:
            queue.append(d)

    return results


__all__ = ["enumerate_filesystem", "ObjectKind", "ObjectInfo", "PurePath"]
