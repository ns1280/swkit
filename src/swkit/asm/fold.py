# -*- coding: utf-8 -*-
"""由角度配合驱动折叠态：改角度尺寸 → 重建 → 实测核对 → 另存折叠副本。

原总装保持工作态（另存后不再改动原文件）。
用法：python -m swkit fold <project> [角度]
"""
import json
import math
import os
import sys

from swkit.asm import swhelp as H


def main(plan_path=None):
    if plan_path is None:
        plan_path = sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    deg = float(sys.argv[2]) if len(sys.argv) > 2 else plan["top"]["fold_deg"]
    sw = H.connect(exe=plan.get("solidworks_exe"))
    doc = sw.OpenDoc(plan["top"]["file"], 2)
    if doc is None:
        raise SystemExit("总装打不开")
    p = H.ptr(doc)
    state_path = os.path.join(plan["dirs"]["jobs"], "asm_state.json")
    dim_name = plan["top"]["angle_name"]
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            dim_name = json.load(f).get("angle_mate", dim_name)
    ok_dim, msg = H.set_mate_angle(p, dim_name, math.radians(deg))
    print("角度驱动 %s -> %.1f°：%s" % (dim_name, deg, msg))
    if not ok_dim:
        raise SystemExit("角度尺寸不可用，折叠未执行")

    exp = plan["top"]["fold_expect"]
    dumped = None
    for c in H.swraw.array_items(H.swraw.call(p, "GetComponents", (False,))):
        nm = H.bstr(H.swraw.call(c, "Name2", prop=True))
        if "/" in nm or not nm.startswith(exp["group"]):
            continue
        v = H.swraw.call(c, "Transform2", prop=True)
        ad = H.swraw.array_items(H.swraw.call(H.swraw.var_ptr(v), "ArrayData", prop=True))
        dumped = {"component": nm, "deg": deg, "transform": list(ad)}
    if not dumped:
        raise SystemExit("找不到动组组件 " + exp["group"])
    out_json = os.path.join(plan["dirs"]["jobs"], "fold_transform.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=1)
    print("动组变换已导出：", out_json)
    H.screenshots(doc, os.path.join(plan["dirs"]["preview"], "%s_FOLD%g" % (plan["project"], deg)))
    doc.SaveAs3(plan["top"]["fold_file"], 0, 0)
    print("折叠副本已保存：", plan["top"]["fold_file"], os.path.exists(plan["top"]["fold_file"]))
    sw.CloseDoc(plan["top"]["file"])
    print("原总装保持工作态：", plan["top"]["file"])


if __name__ == "__main__":
    main()
