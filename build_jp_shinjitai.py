#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OpenCC 上游表生成 jp_shinjitai.json（新字体 ↔ 中文）。

上游来源（已存为 opencc_JPShinjitai*.txt，Apache-2.0，ByVoid/OpenCC）：
  - opencc_JPShinjitaiCharacters.txt : 新字体单字 → 旧字体（kyūjitai）单字
  - opencc_JPShinjitaiPhrases.txt    : 新字体词   → 旧字体（kyūjitai）词

本脚本只做「派生」：用 OpenCC 的 t2s 把旧字体再折到简体中文，
从而每个条目同时带 trad（繁）与 simp（简）两侧。多对一的旧字体单字
（如 弁 → 辨/辯/瓣/辦）不进字符段，留给词级表按词处理（避免污染逐字查询）。

生成物 jp_shinjitai.json 的 schema：
  {
    "chars": [ {"jp": "...", "trad": "...", "simp": "..."}, ... ],
    "words": [ {"jp": "...", "trad": "...", "simp": "..."}, ... ]
  }
依赖：pip install opencc-python-reimplemented
"""
import json
import os
from opencc import OpenCC

HERE = os.path.dirname(os.path.abspath(__file__))
CHARS_SRC = os.path.join(HERE, "opencc_JPShinjitaiCharacters.txt")
PHRASES_SRC = os.path.join(HERE, "opencc_JPShinjitaiPhrases.txt")
OUT = os.path.join(HERE, "jp_shinjitai.json")


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            toks = line.split()
            rows.append((toks[0], toks[1:]))
    return rows


def main():
    cc_t2s = OpenCC("t2s")
    chars_src = load(CHARS_SRC)
    phrases_src = load(PHRASES_SRC)

    chars = []
    multi_chars = 0
    for jp, vals in chars_src:
        if len(vals) != 1:
            # 多对一（如 弁 → 辨/辯/瓣/辦）：不进字符段，交词级表按词处理。
            multi_chars += 1
            continue
        trad = vals[0]
        simp = cc_t2s.convert(trad)
        if jp == trad == simp:
            continue  # 完全自映射，无信息
        chars.append({"jp": jp, "trad": trad, "simp": simp})

    words = []
    for jp, vals in phrases_src:
        # 词级表取首个旧字体形作 trad；其余形罕见，暂不展开。
        trad = vals[0]
        simp = cc_t2s.convert(trad)
        if jp == trad == simp:
            continue
        words.append({"jp": jp, "trad": trad, "simp": simp})

    data = {"chars": chars, "words": words}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"chars: {len(chars)} (跳过 {multi_chars} 个多对一单字)")
    print(f"words: {len(words)}")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
