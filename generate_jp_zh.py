#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 F1/F2 增量并入/写出（不重跑整表生成时使用）。

  F1 新字体→中文 : 并入 zh_CN.dic（head=新字体, target=中文）
  F2 中文→新字体 : 写入 ja_JP.txt（head=中文, target=新字体；.aff 由对方项目提供）

若想用 words.txt 从头重建 zh_CN.dic 并自动带上 F1/F2，请改用
generate_zh_dic.py（已内置 F1 并入与 ja_JP 生成）。本脚本用于在不重跑
整表生成的情况下，把 F1 增量并入 zh_CN.dic、并（重新）写出 ja_JP.*。

与 generate_zh_dic.py 共用 jp_shinjitai_lib，保证两者产物一致。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jp_shinjitai_lib import merge_f1, write_ja  # noqa: E402

ZH_DIC = os.path.join(HERE, "zh_CN.dic")


def parse_lines(path):
    """返回除计数行外的所有原始行列表。"""
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", errors="ignore") as f:
        f.readline()
        return [ln.rstrip("\r\n") for ln in f
                if ln.strip() and not ln.startswith("#")]


def main():
    cur = parse_lines(ZH_DIC)
    merged = merge_f1(cur)
    added = len(merged) - len(cur)
    with io.open(ZH_DIC, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{len(merged)}\n")
        if merged:
            f.write("\n".join(merged) + "\n")
    print(f"zh_CN.dic: +{added} 行 F1（现共 {len(merged):,} 行）")

    ja_dic = write_ja(HERE)
    print(f"ja_JP.txt : {ja_dic}")


if __name__ == "__main__":
    main()
