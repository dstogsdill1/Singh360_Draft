#!/usr/bin/env python3
"""Deterministic, newline-safe unified-diff applicator for Singh360 V32.2.

The script deliberately does not depend on ``git apply``. It parses standard
text unified diffs, normalizes CRLF/LF only while matching, applies each hunk by
unique scoped context, and restores the original target file's newline style.
All patches are simulated in memory before any file is written.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

HUNK_RE = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+"
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@(?:\s.*)?$"
)


class PatchError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    body: tuple[str, ...]

    @property
    def old_lines(self) -> list[str]:
        return [line[1:] for line in self.body if line and line[0] in " -"]

    @property
    def new_lines(self) -> list[str]:
        return [line[1:] for line in self.body if line and line[0] in " +"]


@dataclasses.dataclass(frozen=True)
class FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: tuple[Hunk, ...]
    patch_name: str

    @property
    def target_path(self) -> str:
        path = self.new_path if self.new_path is not None else self.old_path
        if not path:
            raise PatchError(f"{self.patch_name}: file patch has no target path")
        return path

    @property
    def is_new(self) -> bool:
        return self.old_path is None

    @property
    def is_delete(self) -> bool:
        return self.new_path is None


@dataclasses.dataclass
class VirtualFile:
    path: Path
    existed: bool
    newline: str
    bom: bool
    trailing_newline: bool
    lines: list[str]
    delete: bool = False
    changed: bool = False

    @classmethod
    def load(cls, path: Path) -> "VirtualFile":
        if not path.exists():
            return cls(path=path, existed=False, newline="\n", bom=False, trailing_newline=True, lines=[])
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        payload = raw[3:] if bom else raw
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PatchError(f"{path}: target is not UTF-8 text: {exc}") from exc
        crlf = text.count("\r\n")
        bare_lf = text.count("\n") - crlf
        newline = "\r\n" if crlf > bare_lf else "\n"
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        trailing = normalized.endswith("\n")
        lines = normalized.split("\n")
        if trailing:
            lines.pop()
        return cls(path=path, existed=True, newline=newline, bom=bom, trailing_newline=trailing, lines=lines)

    def encoded_bytes(self) -> bytes:
        text = "\n".join(self.lines)
        if self.trailing_newline:
            text += "\n"
        if self.newline != "\n":
            text = text.replace("\n", self.newline)
        raw = text.encode("utf-8")
        return (b"\xef\xbb\xbf" + raw) if self.bom else raw


def _strip_diff_path(raw: str) -> str | None:
    value = raw.split("\t", 1)[0].strip()
    if value == "/dev/null":
        return None
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise PatchError(f"Unsafe patch path: {raw!r}")
    return posix.as_posix()


def parse_patch(text: str, patch_name: str) -> list[FilePatch]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    result: list[FilePatch] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("diff --git "):
            i += 1
            continue
        i += 1
        while i < len(lines) and not lines[i].startswith("--- "):
            if lines[i].startswith("diff --git "):
                raise PatchError(f"{patch_name}: missing ---/+++ file headers")
            i += 1
        if i >= len(lines):
            raise PatchError(f"{patch_name}: incomplete file header")
        old_path = _strip_diff_path(lines[i][4:])
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            raise PatchError(f"{patch_name}: missing +++ file header")
        new_path = _strip_diff_path(lines[i][4:])
        i += 1
        hunks: list[Hunk] = []
        while i < len(lines) and not lines[i].startswith("diff --git "):
            if not lines[i].startswith("@@"):
                i += 1
                continue
            match = HUNK_RE.match(lines[i])
            if not match:
                raise PatchError(f"{patch_name}: invalid hunk header: {lines[i]!r}")
            old_start = int(match.group("old_start"))
            old_count = int(match.group("old_count") or "1")
            new_start = int(match.group("new_start"))
            new_count = int(match.group("new_count") or "1")
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git "):
                line = lines[i]
                if line == r"\ No newline at end of file":
                    i += 1
                    continue
                if not line or line[0] not in " +-":
                    raise PatchError(f"{patch_name}: invalid hunk body line: {line!r}")
                body.append(line)
                i += 1
            actual_old = sum(1 for line in body if line[0] in " -")
            actual_new = sum(1 for line in body if line[0] in " +")
            if actual_old != old_count or actual_new != new_count:
                raise PatchError(
                    f"{patch_name}: hunk count mismatch at -{old_start}/+{new_start}; "
                    f"header {old_count}/{new_count}, body {actual_old}/{actual_new}"
                )
            hunks.append(Hunk(old_start, old_count, new_start, new_count, tuple(body)))
        if not hunks:
            raise PatchError(f"{patch_name}: no text hunks found for {new_path or old_path}")
        result.append(FilePatch(old_path, new_path, tuple(hunks), patch_name))
    if not result:
        raise PatchError(f"{patch_name}: no file patches found")
    return result


def _find_all(haystack: Sequence[str], needle: Sequence[str]) -> list[int]:
    if not needle:
        return list(range(len(haystack) + 1))
    width = len(needle)
    return [i for i in range(0, len(haystack) - width + 1) if list(haystack[i:i + width]) == list(needle)]


def _choose_location(lines: Sequence[str], chunk: Sequence[str], expected: int, *, patch_name: str, target: str, state_name: str) -> int | None:
    if expected >= 0 and expected + len(chunk) <= len(lines) and list(lines[expected:expected + len(chunk)]) == list(chunk):
        return expected
    matches = _find_all(lines, chunk)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    nearby = [position for position in matches if abs(position - expected) <= 12]
    if len(nearby) == 1:
        return nearby[0]
    raise PatchError(f"{patch_name}: ambiguous {state_name} hunk for {target}; {len(matches)} matching locations")


def apply_file_patch(vfile: VirtualFile, file_patch: FilePatch) -> str:
    target = file_patch.target_path
    if not file_patch.is_new and not vfile.existed:
        raise PatchError(f"{file_patch.patch_name}: expected existing target is missing: {target}")
    offset = 0
    changed_hunks = 0
    for hunk in file_patch.hunks:
        old_lines = hunk.old_lines
        new_lines = hunk.new_lines
        expected_old = max(0, hunk.old_start - 1 + offset)
        expected_new = max(0, hunk.new_start - 1 + offset)
        has_additions = any(line.startswith("+") for line in hunk.body)

        # Additions and replacements check the post-patch state first. An
        # append-only hunk leaves its original context intact, so old-first
        # matching would duplicate the added block on the second run.
        if has_additions:
            new_pos = _choose_location(
                vfile.lines, new_lines, expected_new,
                patch_name=file_patch.patch_name, target=target, state_name="post-patch",
            )
            if new_pos is not None:
                offset += len(new_lines) - len(old_lines)
                continue

        old_pos = _choose_location(
            vfile.lines, old_lines, expected_old,
            patch_name=file_patch.patch_name, target=target, state_name="pre-patch",
        )
        if old_pos is not None:
            vfile.lines[old_pos:old_pos + len(old_lines)] = new_lines
            offset += len(new_lines) - len(old_lines)
            changed_hunks += 1
            continue

        # Pure deletions cannot use new-first matching because their post-patch
        # chunk can be only generic context that also exists before deletion.
        if not has_additions:
            new_pos = _choose_location(
                vfile.lines, new_lines, expected_new,
                patch_name=file_patch.patch_name, target=target, state_name="post-patch",
            )
            if new_pos is not None:
                offset += len(new_lines) - len(old_lines)
                continue

        preview = "\n".join(old_lines[:4])
        raise PatchError(
            f"{file_patch.patch_name}: target {target} is neither clean pre-patch nor post-patch "
            f"for hunk -{hunk.old_start},+{hunk.new_start}. Context begins:\n{preview}"
        )
    if file_patch.is_delete:
        vfile.delete = True
        vfile.changed = vfile.existed
    elif changed_hunks:
        vfile.changed = True
        if file_patch.is_new:
            vfile.existed = True
    return "pending" if changed_hunks else "already-installed"


def load_patch_list(path: Path) -> list[Path]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise PatchError(f"{path}: patch list must be a JSON array of paths")
    return [Path(item) for item in raw]


def plan(repo: Path, patch_paths: Iterable[Path]) -> tuple[dict[Path, VirtualFile], list[dict[str, str]]]:
    repo = repo.resolve()
    virtual: dict[Path, VirtualFile] = {}
    report: list[dict[str, str]] = []
    for patch_path in patch_paths:
        patch_path = patch_path.resolve()
        file_patches = parse_patch(patch_path.read_text(encoding="utf-8-sig"), patch_path.name)
        states: list[str] = []
        for file_patch in file_patches:
            target = (repo / Path(*PurePosixPath(file_patch.target_path).parts)).resolve()
            try:
                target.relative_to(repo)
            except ValueError as exc:
                raise PatchError(f"{patch_path.name}: path escapes repository: {target}") from exc
            vfile = virtual.setdefault(target, VirtualFile.load(target))
            states.append(apply_file_patch(vfile, file_patch))
        report.append({"patch": patch_path.name, "state": "pending" if "pending" in states else "already-installed"})
    return virtual, report


def atomic_write(vfile: VirtualFile) -> None:
    if vfile.delete:
        if vfile.path.exists():
            vfile.path.unlink()
        return
    if not vfile.changed:
        return
    vfile.path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=vfile.path.name + ".", suffix=".tmp", dir=str(vfile.path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(vfile.encoded_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, vfile.path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patch-list", type=Path)
    group.add_argument("--patch", action="append", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    patch_paths = load_patch_list(args.patch_list) if args.patch_list else list(args.patch or [])
    if not patch_paths:
        raise PatchError("No patches supplied")
    virtual, report = plan(args.repo, patch_paths)
    if args.apply:
        for vfile in virtual.values():
            atomic_write(vfile)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in report:
        print(f"{item['patch']} : {item['state']}")
    mode = "applied" if args.apply else "validated"
    print(f"Deterministic patch plan {mode}: {len(report)} patches, {sum(v.changed for v in virtual.values())} changed files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"PATCH ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
