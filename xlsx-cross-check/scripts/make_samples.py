#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 xlsx-cross-check 的样例源表（可复现）。"""
import os
from openpyxl import Workbook

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sheet(name, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    for r in rows:
        ws.append(r)
    out = os.path.join(SKILL_DIR, "samples", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    wb.save(out)
    print("样例写出：%s" % out)


if __name__ == "__main__":
    # 两批学科团队“论文数”统计，键=团队，值=论文数
    sheet("t1.xlsx", [
        ["团队", "论文数"],
        ["团队A", 5],
        ["团队B", 3],
        ["团队C", 8],
    ])
    sheet("t2.xlsx", [
        ["团队", "论文数"],
        ["团队A", 2],
        ["团队B", 4],
        ["团队D", 6],
    ])
