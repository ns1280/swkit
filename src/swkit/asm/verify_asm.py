# -*- coding: utf-8 -*-
"""重开总装做只读核对：组件数、配合错误、变换矩阵（不保存）。

工作态期望：两半旋转 = 单位阵；固定半平移 = 0；动半平移 = (0, ay, az)（原点在铰轴）。
用法：python -m swkit verify <project>
"""
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
    if doc is None:
        raise SystemExit("总装打不开")
    p = H.ptr(doc)
    ext = H.extension(p)
    H.swraw.call(p, "EditRebuild3")
    print("重开：", doc.GetTitle)

    n = H.swraw.call(ext, "GetWhatsWrongCount", prop=True)
    wrong = n.v[0] if hasattr(n, "v") else n
    print("GetWhatsWrongCount =", wrong)

    print("特征树中的配合与参考几何：")
    f = H.swraw.call(p, "FirstFeature")
    mates = []
    while f.vt in (9, 13):
        fp = H.swraw.var_ptr(f)
        if not fp:
            break
        tn = H.bstr(H.swraw.call(fp, "GetTypeName2", prop=True))
        nm = H.bstr(H.swraw.call(fp, "Name", prop=True))
        if "Mate" in tn or tn in ("RefAxis", "RefPlane"):
            print("   %-24s %s" % (nm, tn))
            if "Mate" in tn and tn != "MateGroup":
                mates.append(nm)
        f = H.swraw.call(fp, "GetNextFeature")

    subs = {os.path.splitext(os.path.basename(s["file"]))[0]: s for s in plan["subs"]}
    ok = wrong == 0
    found = 0
    for c in H.swraw.array_items(H.swraw.call(p, "GetComponents", (False,))):
        nm = H.bstr(H.swraw.call(c, "Name2", prop=True))
        if "/" in nm:
            continue
        name = nm.rsplit("-", 1)[0]
        sub = subs.get(name)
        if sub is None:
            continue
        found += 1
        v = H.swraw.call(c, "Transform2", prop=True)
        ad = H.swraw.array_items(H.swraw.call(H.swraw.var_ptr(v), "ArrayData", prop=True))
        rot_err = max(abs(ad[i] - (1.0 if i in (0, 4, 8) else 0.0))
                      for i in (0, 1, 2, 3, 4, 5, 6, 7, 8))
        want = [0.0, plan["axis"]["y"], plan["axis"]["z"]] if sub.get("origin_at_axis") else [0.0, 0.0, 0.0]
        t_err = max(abs(ad[9 + i] - want[i]) for i in range(3)) * 1000
        good = rot_err < 1e-9 and t_err < 0.5
        ok = ok and good
        print("   %-12s 旋转偏差 %.2e  平移 (%7.3f, %7.3f, %7.3f) mm  误差 %.3f mm  %s" %
              (sub["group"], rot_err, ad[9] * 1000, ad[10] * 1000, ad[11] * 1000,
               t_err, "OK" if good else "FAIL"))
    print("组件数 =", found, "（应为 %d）" % len(plan["subs"]))
    ok = ok and found == len(plan["subs"])
    print("配合特征：", mates if mates else "（配合在 MateGroup 内，无法用 API 逐个读取）")
    print("工作态核对：", "PASS" if ok else "FAIL")
    sw.CloseDoc(doc.GetTitle)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
