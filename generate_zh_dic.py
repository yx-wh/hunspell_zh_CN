#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_zh_dic.py

讀取一行一個詞的詞彙表，生成 Hunspell .dic，用於 Goldendict 簡繁通查。

依賴：
    pip install opencc-python-reimplemented

用法：
    python3 gen_zh_dic.py words.txt zh_CN.dic
"""

import sys
import os
from collections import OrderedDict, defaultdict
from opencc import OpenCC

# OpenCC t2s 漏掉的一簡對多繁異體字，逐字手動補齊。
CHAR_FIX = {
    "懽": "欢",
    "歓": "欢",
    "歡": "欢",
    #"讙": "欢",
}


def make_normalizer(cc):
    def normalize(word: str) -> str:
        s = cc.convert(word).strip()
        if not s:
            return s
        return "".join(CHAR_FIX.get(ch, ch) for ch in s)
    return normalize


def main():
    if len(sys.argv) != 3:
        print("用法: python3 gen_zh_dic.py 詞彙表.txt 輸出.dic")
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2]

    # 繁體 -> 簡體，作為規範形式
    cc = OpenCC("t2s")
    normalize = make_normalizer(cc)

    words = []
    seen = set()

    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if not w or w.startswith("#"):
                continue
            if w not in seen:
                seen.add(w)
                words.append(w)

    std_of = OrderedDict()        # 原詞 -> 規範形式
    variants = defaultdict(list)  # 規範形式 -> [原詞, ...]

    for w in words:
        #std = cc.convert(w).strip()
        std = normalize(w)
        if not std:
            continue
        std_of[w] = std
        if w not in variants[std]:
            variants[std].append(w)

    lines = []
    emitted_std = set()

    for w in words:
        std = std_of.get(w)
        if std is None or std in emitted_std:
            continue
        emitted_std.add(std)

        others = [v for v in variants[std] if v != std]
        if not others:
            # 繁簡相同、無變體，對 Goldendict 詞幹還原無用，跳過
            continue

        for v in others:
            lines.append(f"{v} st:{std}")
        for v in others:
            lines.append(f"{std} st:{v}")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(str(len(lines)) + "\n")
        if lines:
            f.write("\n".join(lines) + "\n")

    # 順便生成空殼 .aff；如果不想自動生成，可刪掉下面這段
    aff_path = os.path.splitext(out_path)[0] + ".aff"
    with open(aff_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("SET UTF-8\n")
        f.write("LANG zh\n")
        f.write("FLAG long\n")

    print(f"已生成: {out_path}")
    print(f"已生成: {aff_path}")


if __name__ == "__main__":
    main()

