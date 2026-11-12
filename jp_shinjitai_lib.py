#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日本新字体 ↔ 中文 的生成逻辑（F1 / F2 共用）。

数据来源：jp_shinjitai.json（由 build_jp_shinjitai.py 从 OpenCC 上游表派生）。
schema：{"chars":[{jp,trad,simp}], "words":[{jp,trad,simp}]}

F1 新字体→中文：head=新字体, target=中文（并入 zh_CN.dic）
F2 中文→新字体：head=中文(简+繁), target=新字体（写入 ja_JP.dic）

约定（与 generate_zh_dic.py 一致）：
  - 条目形态 `head st:target`；同一 head 多行加 /X 旗标（HOMONYM_FLAG）。
    未定义的 flag 被 hunspell 忽略，不影响 spell()。
  - target == head 一律跳过（如「国」的 simp 侧 == 国，只保留「國」侧）。
  - F1 字符段里「新字体 == 简体中文」的条目（国/体/对…）与 zh_CN.dic 既有的
    简繁通查条目重复，直接跳过，交由简繁表处理。
  - F2 的 head 同时给简体 / 繁体两侧，覆盖「简化字立目」与「繁体立目」辞典，
    以及不吃 OpenCC 的词悦。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(HERE, "jp_shinjitai.json")
EXTRA_JSON = os.path.join(HERE, "jp_words_extra.json")  # Case A：日1↔中多，并入 F1/F2
B_JSON = os.path.join(HERE, "jp_words_b.json")          # Case B：中1↔日多，仅并入 F2
HOMONYM_FLAG = "X"


def load_jp_data(path=DEFAULT_JSON):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # 并入词级扩充（expand_jp_words.py 生成）。Case A 字符不能做字符级 st:（会污染
    # 中文搜索），只能走词级，并入后 emit_f1/emit_f2 自动产出对应 F1/F2 行。Case B
    # 仅并入 F2（中文→日文），F1 跳过以免膨胀（单字级 F1 已能按字拼出日文词）。
    _merge(EXTRA_JSON, data)
    _merge(B_JSON, data)
    return data


def _merge(path, data):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        extra = json.load(f)
    words = data.setdefault("words", [])
    seen = {(e["jp"], e["trad"], e["simp"]) for e in words}
    for e in extra:
        k = (e["jp"], e["trad"], e["simp"])
        if k not in seen:
            words.append(e)
            seen.add(k)


def emit_f1(data):
    """新字体 head → 中文 target，返回行列表。"""
    lines = []
    for sec in ("chars", "words"):
        for e in data.get(sec, []):
            if e.get("kind") == "B":
                continue  # Case B 仅并入 F2，F1 由单字级按字拼出，避免膨胀
            jp, trad, simp = e["jp"], e["trad"], e["simp"]
            if sec == "chars" and jp == simp:
                continue  # 与中文简繁表重复，跳过
            targets = []
            if trad != jp:
                targets.append(trad)
            if simp != jp and simp != trad:
                targets.append(simp)
            if not targets:
                continue
            flag = f"/{HOMONYM_FLAG}" if len(targets) > 1 else ""
            for t in targets:
                lines.append(f"{jp}{flag} st:{t}")
    return lines


def emit_f2(data):
    """中文 head（简+繁）→ 新字体 target，返回按 head 去重的行列表。"""
    out = {}

    def add(head, target):
        if head == target:
            return
        out[f"{head} st:{target}"] = True

    for sec in ("chars", "words"):
        for e in data.get(sec, []):
            jp, trad, simp = e["jp"], e["trad"], e["simp"]
            add(trad, jp)
            add(simp, jp)
    return list(out.keys())


def norm_key(raw):
    """忽略 head 上的 /X 旗标，仅比较 head 与 st: 目标，用于去重。"""
    parts = raw.split()
    head = parts[0].split("/", 1)[0]
    sts = tuple(p for p in parts[1:] if p.startswith("st:"))
    return (head, sts)


def merge_f1(lines, data=None):
    """返回在 lines 基础上并入 F1 后的新列表（去重、跳过简繁重复项）。"""
    if data is None:
        data = load_jp_data()
    existing = {norm_key(r) for r in lines}
    out = list(lines)
    for ln in emit_f1(data):
        k = norm_key(ln)
        if k not in existing:
            out.append(ln)
            existing.add(k)
    return out


def write_ja(out_dir, data=None):
    """写出 ja_JP.txt（F2 转换表），返回其路径。

    ja_JP.txt 只是完整 ja_JP.dic 的「一部分」：真正的日文 hunspell 还含日文
    词形还原（走らない→走る），需并入对方项目（如 yx-wh/hunspell_ja_JP）的完整
    表；真正的 .aff 也由那边提供，故此处不写 .aff。
    """
    if data is None:
        data = load_jp_data()
    f2 = emit_f2(data)
    dic_path = os.path.join(out_dir, "ja_JP.txt")
    with open(dic_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{len(f2)}\n")
        if f2:
            f.write("\n".join(f2) + "\n")
    return dic_path
