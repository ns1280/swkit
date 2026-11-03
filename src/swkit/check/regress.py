# -*- coding: utf-8 -*-
"""与基准模型逐件对比：包围盒、体积。只读打开基准文件，不保存。

基准在 project.yaml 的 baseline 段配置：

    baseline:
      dir: F:\\...\\LJQ_FLOOR_V07
      parts: {L: F-L.SLDPRT, R: F-R.SLDPRT}
      node_x: 1500
      bbox_tol_mm: 1.0
      volume_tol_pct: 1.0

耳板按"基准体积 − 孔径圆柱体积"作为期望值：本流程唯一有意的几何变更是开孔。
"""
import json
import math
import os
import sys

from swkit.asm import swhelp as H

PREFIX = {"beam": "BEAM", "seam_plate": "SEAMPLATE", "pad": "PAD", "lug": "LUG", "pin": "PIN"}
NEAR = 120.0          # 判定"属于该节点"的 X 容差（mm）


def bodies_of(sw, part_path):
    doc = sw.OpenDoc(part_path, 1)
    if doc is None:
        raise SystemExit("打不开 " + part_path)
    p = H.ptr(doc)
    out = []
    for bp in H.swraw.array_items(H.swraw.call(p, "GetBodies2", (-1, True))):
        nm = H.bstr(H.swraw.call(bp, "Name", prop=True))
        box = [v * 1000.0 for v in H.swraw.array_items(H.swraw.call(bp, "GetBodyBox"))]
        mp = H.swraw.array_items(H.swraw.call(bp, "GetMassProperties", (1000.0,)))
        out.append({"name": nm, "box": box, "volume": mp[3] if len(mp) > 3 else None})
    sw.CloseDoc(doc.GetTitle)
    return out


def pick(bodies, prefix, cx):
    cand = [b for b in bodies if b["name"].startswith(prefix)
            and abs((b["box"][0] + b["box"][3]) / 2 - cx) < NEAR]
    if not cand:
        return None
    return min(cand, key=lambda b: abs((b["box"][0] + b["box"][3]) / 2 - cx))


def main(plan_path=None):
    if plan_path is None:
        plan_path = sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    if not plan.get("baseline"):
        print("未配置 baseline，跳过回归")
        return 0
    cfg = plan["baseline"]
    bbox_tol = float(cfg.get("bbox_tol_mm", 1.0))
    vol_tol = float(cfg.get("volume_tol_pct", 1.0))
    prefixes = dict(PREFIX)
    prefixes.update(cfg.get("prefixes") or {})

    sw = H.connect(exe=plan.get("solidworks_exe"))
    cache = {}
    rows = []
    for part in plan["parts"]:
        half = part["half"]
        ref_file = (cfg.get("parts") or {}).get(half)
        if not ref_file:
            rows.append({"part": part["name"], "ok": False, "note": "baseline 未配置 %s 半" % half})
            continue
        if ref_file not in cache:
            cache[ref_file] = bodies_of(sw, os.path.join(cfg["dir"], ref_file))
            print("%s：%d 个实体" % (ref_file, len(cache[ref_file])))
        cx = (part["bbox"][0] + part["bbox"][3]) / 2
        ref = pick(cache[ref_file], prefixes.get(part["kind"], part["kind"].upper()), cx)
        new = bodies_of(sw, part["out"])
        if ref is None or len(new) != 1:
            rows.append({"part": part["name"], "ok": False, "note": "未匹配到基准实体或新件实体数≠1"})
            print("  %-14s 未匹配" % part["name"])
            continue
        dbox = [new[0]["box"][i] - ref["box"][i] for i in range(6)]
        dmax = max(abs(v) for v in dbox)
        dvol = new[0]["volume"] - ref["volume"]
        if part["kind"] == "lug" and plan.get("lug_bore", 0) > 0:
            bore = math.pi * (plan["lug_bore"] / 2.0) ** 2 * plan["lug_t"] / 1e9
            vol_ok = abs(dvol + bore) < abs(bore) * 0.02
            note = "扣孔径圆柱 %.2e m³" % -bore
        else:
            vol_ok = abs(dvol) <= max(abs(ref["volume"]) * vol_tol / 100.0, 1e-9)
            note = ""
        ok = dmax < bbox_tol and vol_ok
        rows.append({"part": part["name"], "ref": ref["name"], "v07_box": ref["box"],
                     "new_box": new[0]["box"], "dbox_max_mm": dmax,
                     "v07_volume": ref["volume"], "new_volume": new[0]["volume"], "dvolume": dvol,
                     "ok": ok, "note": note})
        print("  %-14s vs %-16s bbox 差 %7.3f mm  体积差 %+.3e m³  %s %s" %
              (part["name"], ref["name"], dmax, dvol, "PASS" if ok else "FAIL", note))

    n_fail = sum(1 for r in rows if not r["ok"])
    report = plan["dirs"]["report"]
    os.makedirs(report, exist_ok=True)
    with open(os.path.join(report, "regress.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    lines = ["# 与基准模型的回归对比", "",
             "基准：`%s`，节点 X=%g。" % (cfg["dir"], cfg.get("node_x", 0)),
             "判定：包围盒每向差 < %g mm；体积差 <= %g%%（耳板按开孔扣除体积后比）。" % (bbox_tol, vol_tol), "",
             "| 新零件 | 基准实体 | bbox 最大差 (mm) | 体积差 (m³) | 结果 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        if "ref" not in r:
            lines.append("| %s | — | — | — | **FAIL** %s |" % (r["part"], r.get("note", "")))
        else:
            lines.append("| %s | %s | %.3f | %+.3e | %s |" %
                         (r["part"], r["ref"], r["dbox_max_mm"], r["dvolume"],
                          "PASS" if r["ok"] else "**FAIL**"))
    with open(os.path.join(report, "regress.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("回归：%d 项，%d 项未通过 → report/regress.md" % (len(rows), n_fail))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
