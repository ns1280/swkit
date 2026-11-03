# -*- coding: utf-8 -*-
"""列出 / 关闭本项目打开的 SolidWorks 文档。

  python -m swkit docs list  <project>
  python -m swkit docs close <project>
"""
import json
import os
import sys

from swkit.asm import swhelp as H

NEW_PREFIX = ("装配体", "Assem", "零件", "Part")


def main(mode="list", plan_path=None):
    if plan_path is None:
        plan_path = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    root = os.path.normcase(plan["project_dir"])
    sw = H.connect(exe=plan.get("solidworks_exe"))
    app = H.ptr(sw)
    v = H.swraw.call(app, "GetDocuments", prop=True)
    if not (v.vt & H.swraw.VT_ARRAY):
        print("没有打开的文档")
        return
    docs = H.swraw.array_items(v)
    if not docs:
        print("没有打开的文档")
        return
    for d in docs:
        title = H.bstr(H.swraw.call(d, "GetTitle", prop=True))
        path = H.bstr(H.swraw.call(d, "GetPathName", prop=True))
        mine = os.path.normcase(path).startswith(root) if path else title.startswith(NEW_PREFIX)
        print("%s %-28s %s" % ("本项目" if mine else "保留", title, path or "(未保存的新文档)"))
        if mode == "close" and mine:
            # 按完整路径关闭：两个项目可能有同名零件，按标题关会关错/关不掉
            sw.CloseDoc(path if path else title)
            print("   已关闭", title)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "list")
