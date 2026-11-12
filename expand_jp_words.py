#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用实际中日词典扩充日本新字体的词级表（Case A 中文侧 + Case B 日文侧）。

背景：OpenCC 的词级表太薄（连 弁証法 都没收），且两类「多对一」歧义不能走字符级 st:，
只能走词级：
  - Case A（日1↔中多，如 弁→辩/辨/瓣/办）：会污染中文搜索（中文本来也有「弁」），
    按词处理；查的是在日文文本里看到的词，所以日文形式必须真在日文词典里。
  - Case B（中1↔日多，如 历→歴/暦）：看到日文词不会念、用中文输入法去拼，所以中文
    形式不必在中文辞典里，只要是日文词典里一个纯汉字词即可；单字 st: 已给到两条路径，
    这里再补含该字的整词（如 暦法/歴法 → 历法），帮不吃 OpenCC 的辞典软件拿到备用路径。

本脚本分两趟：
  1. Case A（中文侧）：扫 words.txt 中文词头 → s2t→t2jp，仅留 jp 真在日文词典里，
     产出 jp_words_extra.json（并入 F1/F2）。
  2. Case B（日文侧）：扫日文词头 J 中纯汉字、且含「中1↔日多」字符的词 → jp2t→t2s，
     不要求中文词头在中文辞典，产出 jp_words_b.json（仅并入 F2）。

用法：
    python3 expand_jp_words.py
    python3 expand_jp_words.py --exclude 日本国語大辞典
依赖：mdict-utils、opencc-python-reimplemented、已生成的 words.txt
"""
import json
import os
import re
import subprocess
import sys
from opencc import OpenCC

HERE = os.path.dirname(os.path.abspath(__file__))
JAP_DIR = "/home/yx/GoldenDict/日本語"
CHARS_SRC = os.path.join(HERE, "opencc_JPShinjitaiCharacters.txt")
WORDS_TXT = os.path.join(HERE, "words.txt")
EXTRA_OUT = os.path.join(HERE, "jp_words_extra.json")
B_OUT = os.path.join(HERE, "jp_words_b.json")

MAX_LEN = 64
CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA = re.compile("[\u3040-\u30ff]")  # 平/片假名：含假名的词无法用中文输入法拼，非 Case B
HEAD = re.compile(r"【([^】]+)】")  # mdict -k 输出形如 よみ【よみ】/あいのこべんとう【合いの子弁当】


def multi_chars():
    """OpenCC chars 表里同一新字体对应多个旧字体 → 这些字符不能做字符级 st:。"""
    s = set()
    with open(CHARS_SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            toks = line.split()
            if len(toks) >= 3:  # jp + 多个 trad
                s.add(toks[0])
    return s


def amb_chars():
    """中1↔日多：一个简体中文对应多个日本新字体（如 历→歴/暦）。从 jp_shinjitai.json
    的 chars（已含 1-to-1 的 simp）反查 simp→{jp}，简体对应多个新字体的即 Case B。
    这些字符在 F2（中→日）里一个中文拼写有多条日文路径，词级可补出含该字的整词。"""
    d = json.load(open(os.path.join(HERE, "jp_shinjitai.json"), encoding="utf-8"))
    simp2jp = {}
    for e in d.get("chars", []):
        if e["jp"] == e["simp"]:
            continue  # 自映射（如 国→国）无信息
        simp2jp.setdefault(e["simp"], set()).add(e["jp"])
    amb = set()
    for simp, jps in simp2jp.items():
        if len(jps) > 1:
            amb |= jps
    return amb


def jp_headwords(excludes):
    out = set()
    for dp, _, fs in os.walk(JAP_DIR):
        for n in sorted(fs):
            if not n.lower().endswith(".mdx"):
                continue
            if any(p in n for p in excludes):
                print(f"  跳过：{n}")
                continue
            path = os.path.join(dp, n)
            try:
                r = subprocess.run(
                    ["mdict", "-k", path],
                    capture_output=True, text=True, errors="replace", timeout=600,
                )
            except Exception as e:
                print(f"  跳过（{e}）：{n}", file=sys.stderr)
                continue
            cnt = 0
            for line in r.stdout.splitlines():
                m = HEAD.search(line)
                if m:
                    inner = m.group(1)
                    w = inner if CJK.search(inner) else line[:m.start()].strip()
                else:
                    w = line.strip()
                w = w.strip()
                if not w or len(w) > MAX_LEN or not CJK.search(w):
                    continue
                out.add(w)
                cnt += 1
            print(f"  +{cnt}  {n}")
    return out


def main():
    args = sys.argv[1:]
    excludes = []
    while args and args[0].startswith("--exclude"):
        if args[0] == "--exclude":
            excludes.append(args[1]); args = args[2:]
        else:
            excludes.append(args[0].split("=", 1)[1]); args = args[1:]

    multi = multi_chars()
    print(f"多对一字符: {len(multi)} 个")

    if not os.path.exists(WORDS_TXT):
        raise SystemExit(f"找不到 {WORDS_TXT}，请先 build_words.py 生成中文词头")
    C = set()
    with open(WORDS_TXT, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                C.add(w)
    print(f"中文词头: {len(C)} 条")

    print("抽取日文词典词头 ...")
    J = jp_headwords(excludes)
    print(f"日文词头: {len(J)} 条")

    s2t = OpenCC("s2t")
    t2jp = OpenCC("t2jp")
    t2s = OpenCC("t2s")

    base = json.load(open(os.path.join(HERE, "jp_shinjitai.json"), encoding="utf-8"))
    seen = {(e["jp"], e["trad"], e["simp"]) for e in base.get("words", [])}
    extra = []
    stat = {"diff": 0, "multi_scope": 0, "kept": 0}
    for w in C:
        if not CJK.search(w) or len(w) > MAX_LEN:
            continue
        tr = s2t.convert(w)
        jp = t2jp.convert(tr)
        if jp == w:
            continue
        stat["diff"] += 1
        if not any(ch in multi for ch in jp):
            continue  # 1-to-1 字符级已覆盖，跳过以免膨胀
        stat["multi_scope"] += 1
        if jp not in J:
            continue  # 日文形式不在日文词典里，丢弃（如 办法→弁法）
        simp = t2s.convert(tr)
        key = (jp, tr, simp)
        if key in seen:
            continue
        seen.add(key)
        extra.append({"jp": jp, "trad": tr, "simp": simp})
        stat["kept"] += 1

    with open(EXTRA_OUT, "w", encoding="utf-8") as f:
        json.dump(extra, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"中文词产生不同日文形式: {stat['diff']}；其中多对一范围: {stat['multi_scope']}；"
          f"校验通过并新增: {stat['kept']}")
    print(f"写出 {EXTRA_OUT}")

    # Case B（日文侧）：纯汉字日文词 + 含「中1↔日多」字符 → F2 词级。
    # 不要求中文词头在中文辞典（用户是用中文输入法去拼日文词），只要是 J 里的纯汉字词。
    b_extra = []
    amb = amb_chars()
    bstat = {"scope": 0, "kept": 0}
    jp2t = OpenCC("jp2t")
    for j in J:
        if not CJK.search(j) or len(j) > MAX_LEN:
            continue
        if KANA.search(j):
            continue  # 含假名，无法用中文输入法拼，非 Case B 场景
        if not any(ch in amb for ch in j):
            continue
        if any(ch in multi for ch in j):
            continue  # 含多对一字符（Case A），由词级表另处理，避免 jp2t 翻错
        bstat["scope"] += 1
        tr = jp2t.convert(j)
        si = t2s.convert(tr)
        if si == j or tr == j:
            continue
        key = (j, tr, si)
        if key in seen:
            continue
        seen.add(key)
        b_extra.append({"jp": j, "trad": tr, "simp": si, "kind": "B"})
        bstat["kept"] += 1

    with open(B_OUT, "w", encoding="utf-8") as f:
        json.dump(b_extra, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Case B 纯汉字日文词落入中多范围: {bstat['scope']}；校验通过并新增: {bstat['kept']}")
    print(f"写出 {B_OUT}")


if __name__ == "__main__":
    main()
