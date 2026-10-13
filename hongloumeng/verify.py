#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""红楼梦技能 · 语料回归测试
用法: python3 verify.py   （在本技能目录或任意位置运行均可）

任何人修改 references/ 下的语料后，跑一遍即可知道有没有改坏。
检查项：
  1. 文件完整性      程高本简/繁各 120 回 + 脂评本 81 文件，非空
  2. 缺字占位 □     程高本两版必须为 0；脂评本对照基线（泐损保留）
  3. mojibake 残片   汉字夹星号 / 汉字夹 ASCII 字母 / 私用区字符
  4. ASCII 引号      程高本不得残留反引号与单引号作引文
  5. 关键引文点      18 处修复点抽检（全部必须命中）
  6. 简繁结构一致    每回去除空白后字符数两版必须相等
  7. ch055 错简修复  长度正常且含章尾语（防误接 120 回文字复发）
  8. (可选)逐字对照  若装有 opencc，简体版转回繁体与繁体版逐字比对，
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

results = []  # (级别, 组名, 消息)


def check(level, group, msg):
    results.append((level, group, msg))


def read(p):
    return p.read_text(encoding='utf-8')


# ---------- 1. 文件完整性 ----------
missing = []
for d in (S, T):
    for i in range(1, 121):
        f = d / f'ch{i:03d}.txt'
        if not f.exists() or f.stat().st_size == 0:
            missing.append(str(f))
for i in range(81):
    pat = list(Z.glob(f'ch{i:03d}*.txt'))
    if not pat or pat[0].stat().st_size == 0:
        missing.append(str(Z / f'ch{i:03d}*.txt'))
check('FAIL' if missing else 'PASS', '完整性',
      f'程高本简/繁各 120 回 + 脂评本 81 文件' +
      ('' if not missing else f'；缺失 {len(missing)} 个: {missing[:5]}'))

# ---------- 2-4. 程高本扫描 ----------
texts_s, texts_t = {}, {}
for d, store in ((S, texts_s), (T, texts_t)):
    for i in range(1, 121):
        store[i] = read(d / f'ch{i:03d}.txt')

box_bad = [i for i, t in texts_s.items() if '□' in t]
box_bad += [i for i, t in texts_t.items() if '□' in t]
check('FAIL' if box_bad else 'PASS', '缺字占位',
      f'程高本简/繁 □ = 0' if not box_bad else f'发现 □ 的回: {sorted(set(box_bad))}')

MOJI = [
    (r'[一-鿿]\*', '汉字夹星号'),
    (r'[一-鿿][A-Za-z]|[A-Za-z][一-鿿]', '汉字夹字母'),
    (r'[\ue000-\uf8ff]', '私用区字符'),
]
moji_bad = []
for i, t in list(texts_s.items()) + list(texts_t.items()):
    for pat, label in MOJI:
        if re.search(pat, t):
            moji_bad.append((i, label))
check('FAIL' if moji_bad else 'PASS', 'mojibake 残片',
      f'两版 240 文件无 mojibake' if not moji_bad else f'残片: {moji_bad[:10]}')

quote_bad = [i for i, t in texts_s.items() if '`' in t] + \
            [i for i, t in texts_t.items() if '`' in t]
check('FAIL' if quote_bad else 'PASS', 'ASCII 引号',
      '反引号 = 0（内层引文已归一）' if not quote_bad
      else f'残留反引号的回: {sorted(set(quote_bad))}')

# ---------- 5. 关键引文点 ----------
miss = [(ch, kw) for ch, kw in SPOTS if kw not in texts_s[int(ch[2:])]]
check('FAIL' if miss else 'PASS', '关键引文点',
      f'{len(SPOTS) - len(miss)}/{len(SPOTS)} 命中'
      if not miss else f'未命中: {miss}')

# ---------- 6. 简繁结构一致 ----------
uneq = [i for i in texts_s
        if len(re.sub(r'\s', '', texts_s[i])) != len(re.sub(r'\s', '', texts_t[i]))]
check('FAIL' if uneq else 'PASS', '简繁结构一致',
      '120 回去空白后字符数逐回相等' if not uneq else f'长度不等的回: {uneq}')

# ---------- 7. ch055 错简修复 ----------
t55 = texts_s[55]
ok55 = 4000 < len(t55) < 12000 and '且听下回分解' in t55[-200:]
check('PASS' if ok55 else 'FAIL', 'ch055 错简修复',
      f'长度 {len(t55)} 字、章尾语完好' if ok55 else 'ch055 异常（疑似截断/误接复发）')

# ---------- 2b. 脂评本 □ 基线 ----------
zhi_texts = {f.name: read(f) for f in sorted(Z.glob('ch*.txt'))}
zhi_boxes = sum(t.count('□') for t in zhi_texts.values())
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
        t2s = cc.convert(texts_t[i])
        n = sum(1 for a, b in zip(t2s, texts_s[i]) if a != b) + abs(len(t2s) - len(texts_s[i]))
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
