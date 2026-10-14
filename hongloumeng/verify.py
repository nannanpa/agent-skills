#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""红楼梦技能 · 语料回归测试（v1.1.0 合卷版）
用法: python3 verify.py   （在本技能目录或任意位置运行均可）

任何人修改 references/ 下的语料后，跑一遍即可知道有没有改坏。
语料结构（1.1.0 起，为满足 SkillHub 单包 ≤200 文件限制）：
  - 程高本简体 120 回：保持单回 ch001-ch120.txt
  - 程高本繁体 120 回：合并为 6 卷（每卷 20 回），卷内以回目行"第N回"分章
  - 脂评本 80 回+凡例序：合并为 8 卷（每卷 10 回）
检查项：
  1. 文件完整性      简体 120 单回 + 繁体 6 卷 + 脂评本 8 卷，非空，
                     且繁/脂各卷回号按序连续（顺序校验解析）
  2. 缺字占位 □     程高本两版必须为 0；脂评本对照基线（泐损保留）
  3. mojibake 残片   汉字夹星号 / 汉字夹 ASCII 字母 / 私用区字符
  4. ASCII 引号      程高本不得残留反引号与单引号作引文
  5. 关键引文点      18 处修复点抽检（全部必须命中）
  6. 简繁结构一致    逐回去除空白后字符数两版必须相等
                     （同时验证合卷未丢字：繁体按卷拆回后与简体逐回比对）
  7. ch055 错简修复  长度正常且含章尾语（防误接 120 回文字复发）
  8. (可选)逐字对照  若装有 opencc，简体版转回繁体与繁体版逐回比对，
                     允许三回共 4 处已知转换器粒度差（见 KNOWN_SPOT_DIFFS）

退出码: 0 = 全部通过；1 = 存在 FAIL。
"""

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / 'references'
S = BASE / '程高本120回_简体'
T = BASE / '程高本120回_繁体'
Z = BASE / '脂评本80回_含脂批'

# ---- 基线（如确有新的校勘动作，请同步更新此处并在校勘记中备案） ----
ZHI_BOX_BASELINE = 56          # 脂评本泐损 □ 数（保留项）
KNOWN_SPOT_DIFFS = {           # opencc t2s 逐字对照的已知差异上限（回号: 处数）
    41: 2,   # 䀉 ↔ OpenCC 转 𥁢（点犀䀉，生僻器皿字）
    45: 1,   # 爇 ↔ OpenCC 转 𦶟（泪烛摇摇爇短檠）
    120: 1,  # 毗陵 ↔ OpenCC 保留 毘陵（异体）
}

SPOTS = [  # 18 个关键引文点（五批校勘的修复位置）
    ('ch001', '玉在椟中求善价，钗于奁内待时飞'),
    ('ch001', '此亦静极思动，无中生有之数也'),
    ('ch003', '即瞋视而有情．项上金螭璎珞'),
    ('ch005', '再休提绣帐鸳衾'),
    ('ch008', '累丝嵌宝紫金冠'),
    ('ch041', '把皮签了'),
    ('ch041', '妙玉便斟了一斝，递与宝钗'),
    ('ch041', '点犀䀉'),
    ('ch045', '泪烛摇摇爇短檠'),
    ('ch055', '方往探春处来。只见院中寂静'),
    ('ch063', '随意命人'),
    ('ch076', '赑屭朝光透，罘罳晓露屯'),
    ('ch077', '在院门瞭哨'),
    ('ch079', '蹧扰了人家三四日'),
    ('ch098', '何故至此？"宝玉道'),
    ('ch102', '病灾祲　大观园'),
    ('ch114', '结褵已经三载'),
    ('ch120', '行到毗陵驿地方'),
]

CN = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
      '八': 8, '九': 9}
HEAD = re.compile(r'(?m)^第([一二三四五六七八九十百零]{1,8})回')

results = []  # (级别, 组名, 消息)


def check(level, group, msg):
    results.append((level, group, msg))


def read(p):
    return p.read_text(encoding='utf-8')


def cn2int(s: str) -> int:
    """中文回号 → 整数（1-120）。'百'/'十'传统式；否则数字位式（一零零=100、一一三=113）。"""
    if '百' not in s and '十' not in s:
        return int(''.join(str(CN[c]) for c in s))
    total, cur = 0, 0
    for ch in s:
        if ch == '十':
            total += (cur or 1) * 10
            cur = 0
        elif ch == '百':
            total += (cur or 1) * 100
            cur = 0
        elif ch != '零':
            cur = cur + CN[ch]
    return total + cur


def parse_volume(text: str, start: int):
    """顺序校验拆卷 → ({回号: 回文本}, 接受的回号序列)。

    回目头 = 行首"第N回"（后可跟回目）；仅当解析出的回号等于预期下一回时
    才接受为章首。段终点 = 下一个**被接受**的回目头（被拒绝的匹配——如正文
    行首承接语"第四回中既將…"、源语料 ch045 的重复回目头——全部归入上一章
    正文，保证与简体单回文件逐字对应）。
    """
    ms = list(HEAD.finditer(text))
    accepted_idx = []
    expected = start
    for i, m in enumerate(ms):
        if cn2int(m.group(1)) == expected:
            accepted_idx.append(i)
            expected += 1
    segs = {}
    for k, i in enumerate(accepted_idx):
        m = ms[i]
        end = ms[accepted_idx[k + 1]].start() if k + 1 < len(accepted_idx) else len(text)
        segs[cn2int(m.group(1))] = text[m.start():end]
    return segs, [cn2int(ms[i].group(1)) for i in accepted_idx]


def vol_range(name: str):
    m = re.search(r'第(\d+)-(\d+)回', name)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# ---------- 1. 文件完整性 ----------
problems = []
for i in range(1, 121):
    f = S / f'ch{i:03d}.txt'
    if not f.exists() or f.stat().st_size == 0:
        problems.append(str(f))

t_chapters = {}   # 回号 -> 繁体回文本（自回目头起）
t_vols = sorted(T.glob('卷*.txt'))
if len(t_vols) != 6:
    problems.append(f'繁体卷数 {len(t_vols)} ≠ 6')
for vf in t_vols:
    lo, hi = vol_range(vf.name)
    if lo is None:
        problems.append(f'繁体卷文件名缺回号范围: {vf.name}')
        continue
    segs, accepted = parse_volume(read(vf), lo)
    if accepted != list(range(lo, hi + 1)):
        problems.append(f'{vf.name} 回号序列异常')
    for n, body in segs.items():
        if n in t_chapters:
            problems.append(f'繁体回 {n} 重复')
        t_chapters[n] = body

z_vols = sorted(Z.glob('卷*.txt'))
if len(z_vols) != 8:
    problems.append(f'脂评本卷数 {len(z_vols)} ≠ 8')
z_texts = {}
for vf in z_vols:
    lo, hi = vol_range(vf.name)
    if lo is None:
        problems.append(f'脂评本卷文件名缺回号范围: {vf.name}')
        continue
    txt = read(vf)
    segs, accepted = parse_volume(txt, lo)
    if accepted != list(range(lo, hi + 1)):
        problems.append(f'{vf.name} 回号序列异常')
    z_texts[vf.name] = txt
if z_vols and '凡例' not in read(z_vols[0]) and '戚蓼生' not in read(z_vols[0]):
    problems.append('脂评本卷01 缺凡例/序')

check('FAIL' if problems else 'PASS', '完整性',
      '简体 120 单回 + 繁体 6 卷(20回/卷) + 脂评本 8 卷(10回/卷)，回号连续'
      if not problems else f'问题 {len(problems)} 处: {problems[:5]}')

# ---------- 简体全文本 ----------
texts_s = {i: read(S / f'ch{i:03d}.txt') for i in range(1, 121)
           if (S / f'ch{i:03d}.txt').exists()}

# ---------- 2. 缺字占位 ----------
box_bad = [i for i, t in texts_s.items() if '□' in t]
box_bad += [i for i, t in t_chapters.items() if '□' in t]
check('FAIL' if box_bad else 'PASS', '缺字占位',
      '程高本简/繁 □ = 0' if not box_bad else f'发现 □ 的回: {sorted(set(box_bad))}')

# ---------- 3. mojibake 残片 ----------
MOJI = [
    (r'[一-鿿]\*', '汉字夹星号'),
    (r'[一-鿿][A-Za-z]|[A-Za-z][一-鿿]', '汉字夹字母'),
    (r'[\ue000-\uf8ff]', '私用区字符'),
]
moji_bad = []
for t in list(texts_s.values()) + list(t_chapters.values()):
    for pat, label in MOJI:
        if re.search(pat, t):
            moji_bad.append(label)
check('FAIL' if moji_bad else 'PASS', 'mojibake 残片',
      '两版 240 回无 mojibake' if not moji_bad else f'残片: {moji_bad[:10]}')

# ---------- 4. ASCII 引号 ----------
quote_bad = [i for i, t in texts_s.items() if '`' in t] + \
            [i for i, t in t_chapters.items() if '`' in t]
check('FAIL' if quote_bad else 'PASS', 'ASCII 引号',
      '反引号 = 0（内层引文已归一）' if not quote_bad
      else f'残留反引号的回: {sorted(set(quote_bad))}')

# ---------- 5. 关键引文点 ----------
miss = [(ch, kw) for ch, kw in SPOTS
        if int(ch[2:]) in texts_s and kw not in texts_s[int(ch[2:])]]
check('FAIL' if miss else 'PASS', '关键引文点',
      f'{len(SPOTS) - len(miss)}/{len(SPOTS)} 命中'
      if not miss else f'未命中: {miss}')

# ---------- 6. 简繁结构一致（逐回，兼验合卷无丢字） ----------
uneq = [i for i in texts_s
        if i in t_chapters and
        len(re.sub(r'\s', '', texts_s[i])) != len(re.sub(r'\s', '', t_chapters[i]))]
absent = [i for i in texts_s if i not in t_chapters]
check('FAIL' if uneq or absent else 'PASS', '简繁结构一致',
      '120 回去空白后字符数逐回相等（含合卷完整性）'
      if not uneq and not absent else f'长度不等的回: {uneq}; 繁体缺回: {absent}')

# ---------- 7. ch055 错简修复 ----------
t55 = texts_s.get(55, '')
ok55 = 4000 < len(t55) < 12000 and '且听下回分解' in t55[-200:]
check('PASS' if ok55 else 'FAIL', 'ch055 错简修复',
      f'长度 {len(t55)} 字、章尾语完好' if ok55 else 'ch055 异常（疑似截断/误接复发）')

# ---------- 2b. 脂评本 □ 基线 ----------
zhi_boxes = sum(t.count('□') for t in z_texts.values())
if zhi_boxes == ZHI_BOX_BASELINE:
    check('PASS', '脂评本 □ 基线', f'{zhi_boxes} 处泐损保留（与基线一致）')
else:
    check('WARN', '脂评本 □ 基线',
          f'当前 {zhi_boxes} ≠ 基线 {ZHI_BOX_BASELINE}'
          f'（如有新校勘请更新 verify.py 中的 ZHI_BOX_BASELINE 并在校勘记备案）')

# ---------- 8. 可选：opencc 逐字对照 ----------
try:
    from opencc import OpenCC
    cc = OpenCC('t2s')
    diff_total = {}
    for i in range(1, 121):
        if i not in t_chapters:
            continue
        t2s = cc.convert(t_chapters[i])
        n = sum(1 for a, b in zip(t2s, texts_s.get(i, ''))
                if a != b) + abs(len(t2s) - len(texts_s.get(i, '')))
        if n:
            diff_total[i] = n
    bad = {k: v for k, v in diff_total.items()
           if v > KNOWN_SPOT_DIFFS.get(k, 0)}
    if bad:
        check('FAIL', '逐字对照', f'超出已知异体差: {bad}')
    else:
        extra = {k: v for k, v in diff_total.items() if k in KNOWN_SPOT_DIFFS}
        check('PASS', '逐字对照',
              '简繁逐字 0 差异' if not diff_total
              else f'仅已知转换器粒度差: {extra}（䀉/𥁢、爇/𦶟、毗/毘）')
except ImportError:
    check('SKIP', '逐字对照', '未安装 opencc，跳过（pip install opencc 后可启用）')

# ---------- 汇总 ----------
n_fail = sum(1 for lv, _, _ in results if lv == 'FAIL')
n_warn = sum(1 for lv, _, _ in results if lv == 'WARN')
ICON = {'PASS': '✓', 'FAIL': '✗', 'WARN': '!', 'SKIP': '–'}
print('红楼梦语料 · 回归测试')
print('=' * 56)
for lv, group, msg in results:
    print(f'{ICON[lv]} [{lv:4}] {group:10} {msg}')
print('=' * 56)
print(f'结果: {len(results) - n_fail - n_warn} 通过 / {n_warn} 警告 / {n_fail} 失败'
      + ('　→ 语料被改坏，请查校勘记并复跑修复脚本' if n_fail else '　→ 语料完好'))
sys.exit(1 if n_fail else 0)
