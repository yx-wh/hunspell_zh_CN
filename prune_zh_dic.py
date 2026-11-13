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

Pruning can leave a head with a single line behind, or with several lines of which
only some carry the ``/Xx`` homonym flag. The flag is normalised before writing:
one line per head goes without it, several lines all carry it, otherwise Hunspell
still merges the flagless ones.

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

# 与 generate_zh_dic.HOMONYM_FLAG 保持一致（那边顶层 import opencc，不宜从此处导入）。
# 必须是两字符：zh_CN.aff 是 FLAG long。
HOMONYM_FLAG = "Xx"
HOMONYM_SUFFIX = "/" + HOMONYM_FLAG

# generate_zh_dic.HEAD_SLASH：詞頭裡的「/」在 .dic 中以私用區字元存放（.aff 的
# ICONV/OCONV 負責換回），做字級比較前要先還原成真正的「/」。
HEAD_SLASH = "\ue000"


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
            # head 可能帶 /Xx homonym flag（見 generate_zh_dic.py），判斷
            # 單字/多字與字級組合時必須剝掉，否則「发/Xx」會被當多字詞；
            # 詞頭裡的 HEAD_SLASH 也要還原成「/」再比較。
            head = parts[0].split("/", 1)[0].replace(HEAD_SLASH, "/")
            targets = [part[3:] for part in parts[1:] if part.startswith("st:")]
            if targets:
                entries.append((head, targets, raw))
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


def split_head(raw: str) -> tuple[str, bool] | None:
    """Returns ``(bare head, already flagged)``, or ``None`` for lines left alone.

    A ``/`` inside the head itself (``F/A-22“猛禽”…``) cannot be told apart from a
    flag separator, so such lines are neither counted nor rewritten.
    """
    token = raw.split(" ", 1)[0]
    if token.endswith(HOMONYM_SUFFIX):
        return token[: -len(HOMONYM_SUFFIX)], True
    if "/" in token:
        return None
    return token, False


def normalize_homonym_flags(lines: list[str]) -> tuple[list[str], int, int]:
    """Keeps at most one line per head unflagged, and flags every line otherwise.

    Hunspell only drops a homonym when *both* entries are flagless, so a head with
    three lines where just one carries the flag still loses one of the other two;
    conversely pruning often leaves a single line whose flag no longer does
    anything. Returns the rewritten lines plus (flags added, flags removed).
    """
    counts: dict[str, int] = defaultdict(int)
    parsed = [split_head(raw) for raw in lines]
    # A slash-word (``F/A-22…``) parses as the same bare head Hunspell would see,
    # so the group's real size is unknown: leave those heads exactly as they are.
    unsafe: set[str] = set()
    for raw, item in zip(lines, parsed):
        if item is None:
            unsafe.add(raw.split(" ", 1)[0].split("/", 1)[0])
        else:
            counts[item[0]] += 1

    out = list(lines)
    added = removed = 0
    for index, (raw, item) in enumerate(zip(lines, parsed)):
        if item is None or item[0] in unsafe:
            continue
        head, flagged = item
        rest = raw[len(head):]
        want = counts[head] > 1
        if want and not flagged:
            out[index] = head + HOMONYM_SUFFIX + rest
            added += 1
        elif flagged and not want:
            out[index] = head + rest[len(HOMONYM_SUFFIX):]
            removed += 1
    return out, added, removed


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "zh_CN.dic")
    stem = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "zh_CN_pruned")

    entries = parse(source)
    variants = variant_table(entries)
    convert = Converter()

    kept: list[str] = []
    single = kept_chars = dropped = 0
    kept_composition = kept_opencc = kept_slash = 0

    for head, targets, raw in entries:
        if len(head) == 1:
            kept.append(raw)
            single += 1
            continue

        if HEAD_SLASH in raw.split(" ", 1)[0]:
            # 詞頭含「/」的行一律保留：Hunspell 不做字級合成，整詞只能靠這一條
            # 詞頭（配合 .aff 的 ICONV/OCONV）命中；按「兩個讀取器都能推出來」
            # 的標準刪掉的話，重建一次這批詞就從 Hunspell 側徹底消失。
            kept.append(raw)
            kept_slash += 1
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

    # 去重是按「同 head 且双方都无 flag」判定的，所以多行 head 必须每行都带
    # 旗标；反过来，prune 删掉兄弟行后剩下的独行不再需要旗标。
    kept_before = kept
    kept, flags_added, flags_removed = normalize_homonym_flags(kept_before)
    rewritten = dict(zip(kept_before, kept))

    ext = os.path.splitext(source)[1] or ".dic"
    dic_path = stem + ext
    with io.open(dic_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{len(kept)}\n")
        handle.write("\n".join(kept))
        handle.write("\n")
    # 仅当源 .aff 存在时才复制（zh_CN 有配套 .aff；ja_JP 的 .aff 由对方项目
    # 提供，此处不写，故跳过）。
    src_aff = os.path.splitext(source)[0] + ".aff"
    if os.path.exists(src_aff):
        shutil.copyfile(src_aff, stem + ".aff")

    # Verification: re-read the written file and re-check every decision on the
    # written data, so a parsing or formatting slip cannot pass silently.
    written = {raw for _, _, raw in parse(dic_path)}
    missing = [raw for raw in kept if raw not in written]
    if missing:
        print(f"FAIL: {len(missing)} kept lines did not survive the round trip")
        return 1

    reachable = 0
    for head, targets, raw in entries:
        if rewritten.get(raw, raw) in written:
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
    print(f"  slash-head kept  : {kept_slash:,}")
    print(f"  word lines kept  : {kept_chars:,}")
    print(f"    for composition: {kept_composition:,}")
    print(f"    for OpenCC     : {kept_opencc:,}")
    print(f"  dropped          : {dropped:,}")
    print(f"  homonym flags    : +{flags_added:,} / -{flags_removed:,}")
    print("verified    : every source entry still derivable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
