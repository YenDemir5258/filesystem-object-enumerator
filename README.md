# filesystem-object-enumerator

Enumerates all filesystem objects beneath a root path in a single pass, returning each one's absolute path, path relative to the root, resolved kind, and size.

```python
from filesystem_object_enumerator import enumerate_filesystem, ObjectKind, ObjectInfo

infos: list[ObjectInfo] = enumerate_filesystem("/some/root")
for i in infos:
    print(i.relative_path, i.kind, i.size)
```

## Why this exists

Tools that need to report "everything under here" tend to either call `os.walk` and then re-`stat` every entry, or call `os.scandir` without controlling the order of results. Both work, but they do more system calls than necessary and produce non-deterministic ordering. This library walks the tree with an explicit stack so that output is deterministic (children sorted by name within each directory) and each object is stat-resolved exactly once.

The trade-off: the result is a concrete `list`, not a lazy iterator. If your tree is huge and you want streaming behaviour, you want a different library. The list suits the common case of sorting, deduplicating, or serializing the full collection.

## Edge cases worth knowing

- The root itself is **not** included in the output. If the root is not a directory (file, missing path), you get `[]`.
- Symlinks are stat-resolved (`follow_symlinks=True`): a link to a directory reports as `directory`, a link to a file as `file` with the referent's size. A broken link reports as `broken_link` with `size == -1`.
- Directories report their own `st_size` as reported by the OS (commonly 0 or a small block size on Unix, varies by filesystem). Don't use directory sizes to mean "sum of contents" — that's a different operation.
- If a directory becomes unreadable between discovery and traversal, it is skipped rather than raising. The enumeration never aborts mid-tree.
