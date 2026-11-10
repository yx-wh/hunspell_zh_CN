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

# 在 OpenCC t2s 之後逐字折疊到規範形的人工白名單。
# 每加一條，所有含該字的詞頭都會被歸進同一組，因此只收
# 「確認是同一字的另一種寫法」的字，寧缺勿濫。
#
# 審定方法（離線，不進執行期依賴）：
#   1. Unihan_Variants.txt 的 kTraditionalVariant 反向聚合，取候選字 c 的繁體 T；
#   2. 用「單字」OpenCC t2s(T) 求規範形 S（必須單字：詞組規則會把
#      「錢鍾書」轉成「钱锺书」而不合併）；
#   3. 只收 2013《通用規範漢字表》為姓氏人名／地名類推簡化、
#      且檢索上確需互通者，並以該字表攔住過度合併；
#   4. 再按本機辭典組的實際立目情況取捨：註釋裡的本數／條數即為
#      48 本 MDX + 1 本 DSL 中該字的詞級用量，0 條者不收。
#   5. 切勿整表灌入 kSemanticVariant 或通用異體字表：那會連
#      「乾→干」「了→瞭」「借→藉」這類跨語義的字也折進來。
CHAR_FIX = {
    # 一簡對多繁：OpenCC t2s 漏掉的異體
    "懽": "欢",
    "歓": "欢",
    "歡": "欢",
    # 2013 類推簡化字：OpenCC 刻意保留為獨立規範字，但檢索上須互通
    "锺": "钟",   # 繁體 鍾；本機 12 本 / 29 條
    "缐": "线",   # 繁體 線；14 本 / 14 條
    "钜": "巨",   # 繁體 鉅；單字 0 本，但詞級 20 本 / 139 條
    # 擴展區類推簡化字：本機辭典確實用它立目，不折則查不到
    "𢧐": "战",   # 繁體 戰；4 本 / 4 條
    "𫫇": "恶",   # 繁體 噁；10 本 / 15 條
    "𬞟": "苹",   # 繁體 蘋；12 本 / 20 條
    "𧹒": "买",   # 繁體 買；3 本 / 3 條
    "𫔭": "开",   # 繁體 開；2 本 / 2 條
    "𫖸": "愿",   # 繁體 願；2 本 / 2 條
    "𫗯": "糇",   # 繁體 餱；3 本 / 3 條
    "㳽": "弥",   # 繁體 瀰；6 本 / 6 條
    "䙓": "摆",   # 繁體 襬；3 本 / 3 條
    "𧹔": "账",   # 繁體 賬；1 本 / 1 條
    "𪠽": "当",   # 繁體 噹；1 本 / 1 條
    "𫍿": "谫",   # 繁體 譾；1 本 / 1 條
    "𲈛": "钟",   # 繁體 鍾；Unihan 無記錄，詞級僅 1 條，留作兜底
    # 異體字組（取自 ToyMDict 的 variants.json）：只收擴展區／兼容區 →
    # BMP 常用字、兩端都不在現有白名單的 131 對。這些字 OpenCC 不認，
    # 不折則 generate 會把它們和正體當成兩個不同的字。
    "𨢄": "丑",
    "𠄞": "贰",
    "𲁗": "亲",
    "𲅗": "侦",
    "𬞕": "兰",
    "𬮦": "关",
    "𠕁": "册",
    "𪷤": "凛",
    "𱁶": "千",
    "𰛮": "卤",
    "𨤲": "厘",
    "𢊍": "厨",
    "𰵞": "咏",
    "𳐝": "咸",
    "𬮢": "哄",
    "𲂊": "哗",
    "𬤨": "噪",
    "𬮻": "坞",
    "𡬶": "寻",
    "𱜇": "岭",
    "𰎫": "岳",
    "𰎏": "岽",
    "𰎔": "峣",
    "𡸵": "峥",
    "𰬈": "弦",
    "𰵧": "志",
    "𰑧": "惭",
    "𰌙": "懒",
    "𢩾": "执",
    "𬨈": "挽",
    "𰙎": "敛",
    "𬮴": "暗",
    "𣏂": "杀",
    "𬬰": "枪",
    "𣰯": "氇",
    "𬣣": "注",
    "𧳯": "猪",
    "𤨏": "琐",
    "𬪨": "盏",
    "𥤚": "秋",
    "𬮭": "窥",
    "𰠛": "笺",
    "𥳑": "简",
    "𫗫": "糊",
    "𦂳": "紧",
    "𦃂": "紧",
    "𱺧": "练",
    "𰺷": "绕",
    "𰬩": "绣",
    "𱹼": "缁",
    "𮉞": "缡",
    "𰢤": "罂",
    "𬳁": "肴",
    "𦢫": "胧",
    "𰬫": "致",
    "𮶙": "舰",
    "𦍋": "芈",
    "𫊱": "茧",
    "𱲒": "荡",
    "𫷮": "荫",
    "𱽚": "药",
    "𧉕": "蚕",
    "𰻡": "许",
    "𰵑": "讹",
    "𬢪": "诪",
    "𧩽": "谆",
    "𫍝": "谏",
    "𰷭": "赃",
    "𰷧": "赆",
    "𧿛": "踪",
    "𮷛": "轰",
    "𰿾": "辟",
    "𲃫": "迹",
    "𰾗": "针",
    "𰽭": "钩",
    "𰿆": "钻",
    "𮸛": "铠",
    "𬭨": "锤",
    "𰾹": "镌",
    "𲉄": "闿",
    "𨷺": "阄",
    "𨵽": "阍",
    "𨽻": "隶",
    "𮥼": "隽",
    "𱂐": "韵",
    "𳌥": "须",
    "𮸹": "顾",
    "𱂥": "额",
    "𱂽": "飐",
    "𱂿": "飑",
    "𩗗": "飓",
    "𱃉": "飕",
    "𮸼": "飚",
    "𬲦": "饲",
    "𳋮": "馈",
    "𱅐": "驳",
    "𳌘": "骡",
    "𱈘": "鲿",
    "𩾛": "鸠",
    "𩾢": "鸢",
    "𱉨": "鸦",
    "𮬮": "鸩",
    "𩿵": "鸪",
    "𪂝": "鸫",
    "𪈒": "鸬",
    "𨾦": "鸱",
    "𪀊": "鸲",
    "𪆓": "鸶",
    "𬷮": "鸷",
    "𪈳": "鹂",
    "𪁴": "鹆",
    "𪁩": "鹈",
    "𪃞": "鹋",
    "𪂳": "鹍",
    "𪂃": "鹎",
    "𪂙": "鹏",
    "𪂎": "鹑",
    "𪂧": "鹓",
    "𪂭": "鹓",
    "𪆭": "鹔",
    "𪄥": "鹘",
    "𪃩": "鹙",
    "𪈤": "鹦",
    "𪅡": "鹨",
    "𪆄": "鹪",
    "𪆩": "鹫",
    "𪆽": "鹭",
    "𪆬": "鹭",
    "𪇡": "鹱",
    "𪈩": "鹳",
    "𬂮": "榝",
    # 明確不收（雖在同組、且本機也有條目）：
    #   迳→径、飏→扬、镕、闫：2013 字表特意分出的獨立規範字；
    #   复→覆（2381 條）、馀→余（71 條）、渖→沈（11 條）、
    #   镟→旋（5 條）：同為簡化字但語義不同，或已由 OpenCC 詞組
    #   規則區分，逐字硬折會把「復習」帶成「覆習」、「餘勇」帶成
    #   「余勇」，引入跨語義候選。
}


# 同一個 head 多行時加在 head 後的 flag。標準 hunspell 的 hashmgr 會把
# 「無 affix flag」的同形詞當重複詞去重，只留第一行（1.7.6 實測：发 st:發
# / 发 st:髮 只剩 發）；帶 flag 則走 next_homonym 分支，兩行都保留。
# 這個 flag 不必在 .aff 裡定義——未定義 flag 被忽略，不影響 spell()。
HOMONYM_FLAG = "X"


def validate_char_fix(fix):
    """白名單必須是單字對單字、無自映射、無鏈式摺疊。"""
    for src, dst in fix.items():
        if len(src) != 1 or len(dst) != 1:
            raise ValueError(f"CHAR_FIX 必須是單字對單字: {src!r} -> {dst!r}")
        if src == dst:
            raise ValueError(f"CHAR_FIX 自映射: {src!r}")
        if dst in fix:
            raise ValueError(f"CHAR_FIX 鏈式摺疊（單遍替換不會生效）: {src!r} -> {dst!r}")


def make_normalizer(cc):
    validate_char_fix(CHAR_FIX)

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

        # 標準形→多個變體是「同一個 head、多行」，標準 hunspell 會去重，
        # 因此多於一個變體時給 head 加 flag（見 HOMONYM_FLAG 註釋）。
        homonym = f"/{HOMONYM_FLAG}" if len(others) > 1 else ""
        for v in others:
            lines.append(f"{v} st:{std}")
        for v in others:
            lines.append(f"{std}{homonym} st:{v}")

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

