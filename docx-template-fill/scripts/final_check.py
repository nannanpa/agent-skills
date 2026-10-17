#!/usr/bin/env python3
"""docx-template-fill 终验脚本（第 7 步必跑）

用法：
  python3 final_check.py --target 填报版.docx --must "关键新句" --banned "禁用词" [--gone "被删旧句"] [--must "另一条必须存在的内容"]

规则：
  - --must 可重复：每一条都必须在正文里
  - --gone 可重复：每一条都必须清零
  - --banned 可重复：等价于 --gone（术语合规）
  - 任一不过即非零退出，✗ 项即为问题所在，勿交付
"""
import argparse, re, sys, zipfile

ap = argparse.ArgumentParser(description='docx 填报终验：解包检查新内容在、旧内容清零、术语合规')
ap.add_argument('--target', required=True, help='填报版 docx 路径（mv 覆盖后的 F）')
ap.add_argument('--must', action='append', default=[], help='必须存在的内容（可重复）')
ap.add_argument('--gone', action='append', default=[], help='必须清零的内容（可重复）')
ap.add_argument('--banned', action='append', default=[], help='禁用词（等价 --gone，可重复）')
a = ap.parse_args()

try:
    with zipfile.ZipFile(a.target) as z:
        xml = z.read('word/document.xml').decode('utf-8')
except zipfile.BadZipFile:
    sys.exit('终验未通过：文件不是合法 docx（zip）——多半是保存环节写坏（如 CDFV2 加密），按 FAQ「文件写坏」处置')
except FileNotFoundError:
    sys.exit(f'终验未通过：找不到 {a.target}——mv 是否成功？按 FAQ「覆盖环节」处置')

text = re.sub(r'<[^>]+>', '', xml)
checks = [('新内容在：' + m, m in text) for m in a.must]
checks += [('已清零：' + m, text.count(m) == 0) for m in (a.gone + a.banned)]

for name, ok in checks:
    print(('✓' if ok else '✗'), name)
failed = [name for name, ok in checks if not ok]
if failed:
    sys.exit('终验未通过：' + '；'.join(failed) + ' —— ✗ 项即为问题所在，勿交付')
print('终验通过')
