#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 GoldenDict 词典目录生成 words.txt（供 generate_zh_dic.py 使用）。

流程：
  1. 扫描目录下的 .mdx / .dsl / .dsl.dz，导出词头（.mdx 走 `mdict -k`，DSL 直接读文本）；
  2. 过滤：必须含至少一个汉字；排除 HTML 片段、@@@LINK、控制字符；
     排除首尾标点、括号不配对、连续空格的条目；长度上限 64；
  3. 对词头做 s2t（繁化），但含 CHAR_FIX 里的类推简化字时保留原形——
     OpenCC 把「锺」当「鍾」的简体，一转就丢，CHAR_FIX 随之失效；
  4. 去重后写出，一行一个词头。

排除词典（默认按文件名含 oald / 反查 判定）：
  例句反查类词典的词条是整句（如「神经脆弱的人」），不是词头，
  对简繁通查没有意义，且会把全量表撑大一倍。需要时用 --exclude 追加。

用法：
    python3 build_words.py [词典目录] [输出文件]
    python3 build_words.py --exclude 成语 --exclude 谚语 <目录> <输出>

依赖：mdict-utils（处理 .mdx）、opencc-python-reimplemented。
"""

import gzip
import os
import re
import sys
import subprocess
import collections

from opencc import OpenCC

import generate_zh_dic

# 默认词典目录：命令行第一个参数优先，其次环境变量，都没有则要求显式传入。
DEFAULT_DICT_DIR = os.environ.get("GOLDENDICT_DICTS", "")
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "words.txt")

# 例句反查类词典：词条是句子，不是词。
DEFAULT_EXCLUDES = ("oald", "反查")

MAX_LEN = 64

S2T = OpenCC("s2t")
CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003ffff]")
CTRL = re.compile("[\x00-\x1f\x7f]")
BAD_END = set("。，、；：！？）]」』”\"")
BAD_START = set("…（[「『“\"")

# CHAR_FIX 的 key 不能被 s2t 转走，否则 generate 阶段折不回来。
PROTECT = set(generate_zh_dic.CHAR_FIX)


def shape_ok(w):
    if w[0] in BAD_START or w[-1] in BAD_END:
        return False
    if w.count("（") != w.count("）") or w.count("(") != w.count(")"):
        return False
    if "  " in w:
        return False
    return True


def iter_mdx_words(path):
    """调用 mdict -k 导出词头；失败时返回空。"""
    try:
        out = subprocess.run(
            ["mdict", "-k", path],
            capture_output=True, text=True, errors="replace", timeout=300,
        )
    except FileNotFoundError:
        raise SystemExit("找不到 mdict 命令，请先 pip install mdict-utils")
    except subprocess.TimeoutExpired:
        print(f"  超时：{path}", file=sys.stderr)
        return
    for line in out.stdout.splitlines():
        w = line.strip()
        if w:
            yield w


def iter_dsl_words(path):
    """流式读取 DSL/DSL.dz，取顶格且非 # 开头的行作为词头。"""
    opener = gzip.open if path.lower().endswith(".dz") else open
    with opener(path, "rb") as fh:
        head = fh.read(4)
    enc = "utf-16" if head[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    with opener(path, "rt", encoding=enc, errors="replace") as fh:
        for line in fh:
            s = line.rstrip("\r\n")
            if not s or s[0] in "#\t ":
                continue
            yield s.strip()


def iter_dict_files(root, excludes):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            low = name.lower()
            if not (low.endswith(".mdx") or low.endswith(".dsl") or low.endswith(".dsl.dz")):
                continue
            if any(p.lower() in low for p in excludes):
                print(f"  跳过：{name}")
                continue
            yield os.path.join(dirpath, name)


def maybe_s2t(w):
    if any(ch in PROTECT for ch in w):
        return w
    return S2T.convert(w)


def main():
    args = [a for a in sys.argv[1:]]
    excludes = list(DEFAULT_EXCLUDES)
    while args and args[0].startswith("--exclude"):
        if args[0] == "--exclude":
            excludes.append(args[1])
            args = args[2:]
        else:  # --exclude=xxx
            excludes.append(args[0].split("=", 1)[1])
            args = args[1:]

    root = args[0] if len(args) > 0 else DEFAULT_DICT_DIR
    out_path = args[1] if len(args) > 1 else DEFAULT_OUTPUT

    if not root:
        raise SystemExit("用法: python3 build_words.py <词典目录> [输出文件]")
    if not os.path.isdir(root):
        raise SystemExit(f"词典目录不存在：{root}")

    seen = set()
    out = []
    stat = collections.Counter()
    files = list(iter_dict_files(root, excludes))
    print(f"扫描 {len(files)} 本词典 ...")

    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        words = iter_dsl_words(path) if ".dsl" in path.lower() else iter_mdx_words(path)
        before = len(out)
        for w in words:
            if len(w) > MAX_LEN:
                stat["too_long"] += 1
                continue
            if "@@@LINK" in w or "<" in w or ">" in w:
                stat["html"] += 1
                continue
            if CTRL.search(w):
                stat["ctrl"] += 1
                continue
            if not CJK.search(w):
                stat["no_cjk"] += 1
                continue
            if not shape_ok(w):
                stat["shape"] += 1
                continue
            t = maybe_s2t(w)
            if not t or t in seen:
                continue
            if not CJK.search(t):
                stat["s2t_no_cjk"] += 1
                continue
            if len(t) > MAX_LEN:
                stat["s2t_long"] += 1
                continue
            seen.add(t)
            out.append(t)
        print(f"  [{i:02d}/{len(files)}] {name}: +{len(out) - before}")

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")

    print(f"写出 {out_path}：{len(out)} 条")
    print("丢弃统计：", dict(stat))


if __name__ == "__main__":
    main()
