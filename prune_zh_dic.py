#!/usr/bin/env python3
"""Prunes a generated zh_CN.dic down to the lines a reader cannot derive.

Two consumers read the same file, and they derive candidates differently:

* Ciyue looks each *character* of a query up and combines the results, so a
  word-level line is redundant whenever the word can be rebuilt character by
  character from the single-character lines.
* GoldenDict-ng passes the whole word to Hunspell and leaves the one-to-one
  conversion to OpenCC, which only ever produces one answer. A word-level line
  is redundant there only when OpenCC already produces exactly that spelling.

A word-level line is kept when **either** consumer cannot derive it:

    keep = not char_composable or not opencc_covered

Single-character lines are always kept: they are the table Ciyue composes from,
and GoldenDict-ng cannot use them at all, since it never composes characters.

Usage:
    python3 prune_zh_dic.py [source.dic] [output_stem]

Defaults to zh_CN.dic next to this script and writes zh_CN_pruned.dic/.aff.
Requires opencc-python-reimplemented for the OpenCC check; without it, every
word-level line is kept and only the character composition is applied.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def parse(path: str) -> list[tuple[str, list[str], str]]:
    """Reads a .dic into (headword, [st: targets], raw line), order preserved."""
    entries: list[tuple[str, list[str], str]] = []
    with io.open(path, encoding="utf-8", errors="ignore") as handle:
        handle.readline()  # the declared count; rewritten on output
        for line in handle:
            raw = line.rstrip("\r\n")
            if not raw.strip() or raw.startswith("#"):
                continue
            parts = raw.split()
            targets = [part[3:] for part in parts[1:] if part.startswith("st:")]
            if targets:
                entries.append((parts[0], targets, raw))
    return entries


def variant_table(entries: list[tuple[str, list[str], str]]) -> dict[str, set[str]]:
    """`standard -> characters written for it`, from the single-character rows."""
    variants: dict[str, set[str]] = defaultdict(set)
    for head, targets, _ in entries:
        if len(head) != 1:
            continue
        for target in targets:
            variants[target].add(head)
    return variants


def char_composable(head: str, target: str, variants: dict[str, set[str]]) -> bool:
    """Whether [target] can be rebuilt from [head] one character at a time."""
    if len(head) != len(target):
        return False
    for source, wanted in zip(head, target):
        if source != wanted and source not in variants.get(wanted, ()):
            return False
    return True


class Converter:
    """OpenCC applied in whichever direction changes the word, memoised."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        try:
            import opencc  # noqa: PLC0415

            self._s2t = opencc.OpenCC("s2t")
            self._t2s = opencc.OpenCC("t2s")
        except Exception as error:  # optional dependency
            print(f"opencc unavailable ({error}); keeping every word-level line")
            self._s2t = None
            self._t2s = None

    def __call__(self, word: str) -> str | None:
        if self._s2t is None:
            return None
        cached = self._cache.get(word)
        if cached is not None:
            return cached
        result = self._s2t.convert(word)
        if result == word:
            result = self._t2s.convert(word)
        self._cache[word] = result
        return result


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "zh_CN.dic")
    stem = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "zh_CN_pruned")

    entries = parse(source)
    variants = variant_table(entries)
    convert = Converter()

    kept: list[str] = []
    single = kept_chars = dropped = 0
    kept_composition = kept_opencc = 0

    for head, targets, raw in entries:
        if len(head) == 1:
            kept.append(raw)
            single += 1
            continue

        reason = None  # why the line cannot be dropped
        for target in targets:
            if not char_composable(head, target, variants):
                reason = "composition"
                break
        if reason is None:
            for target in targets:
                if convert(head) != target:
                    reason = "opencc"
                    break

        if reason is None:
            dropped += 1
            continue
        kept.append(raw)
        kept_chars += 1
        if reason == "composition":
            kept_composition += 1
        else:
            kept_opencc += 1

    dic_path = stem + ".dic"
    aff_path = stem + ".aff"
    with io.open(dic_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{len(kept)}\n")
        handle.write("\n".join(kept))
        handle.write("\n")
    shutil.copyfile(os.path.splitext(source)[0] + ".aff", aff_path)

    # Verification: re-read the written file and re-check every decision on the
    # written data, so a parsing or formatting slip cannot pass silently.
    written = {raw for _, _, raw in parse(dic_path)}
    missing = [raw for raw in kept if raw not in written]
    if missing:
        print(f"FAIL: {len(missing)} kept lines did not survive the round trip")
        return 1

    reachable = 0
    for head, targets, raw in entries:
        if raw in written:
            reachable += 1
            continue
        if all(char_composable(head, t, variants) for t in targets):
            if all(convert(head) == t for t in targets):
                reachable += 1
    if reachable != len(entries):
        print(f"FAIL: {len(entries) - reachable} entries are no longer derivable")
        return 1

    size_in = os.path.getsize(source) / 1e6
    size_out = os.path.getsize(dic_path) / 1e6
    print(f"source      : {source} ({len(entries):,} entries, {size_in:.1f} MB)")
    print(f"output      : {dic_path} ({len(kept):,} entries, {size_out:.2f} MB)")
    print(f"  single-char kept : {single:,}")
    print(f"  word lines kept  : {kept_chars:,}")
    print(f"    for composition: {kept_composition:,}")
    print(f"    for OpenCC     : {kept_opencc:,}")
    print(f"  dropped          : {dropped:,}")
    print("verified    : every source entry still derivable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
