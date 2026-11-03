# -*- coding: utf-8 -*-
"""截唯一一张 Z 向上轴测图（不改模型，不保存）。用法：python -m swkit shot <project>"""
import json
import os
import sys

from swkit.asm import swhelp as H


def main(plan_path=None):
    if plan_path is None:
        plan_path = sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    sw = H.connect(exe=plan.get("solidworks_exe"))
    doc = sw.OpenDoc(plan["top"]["file"], 2)
    out = os.path.join(plan["dirs"]["preview"], "01_轴测.bmp")
    H.shot_iso_zup(doc, out)
    print("截图：", out, "调用序列：", H.VIEW_ISO_Z_UP)
    sw.CloseDoc(plan["top"]["file"])


if __name__ == "__main__":
    main()
