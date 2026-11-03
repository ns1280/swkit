# -*- coding: utf-8 -*-
"""折叠结果核对：动半实际变换 vs "绕铰轴旋转"。

两种装配方案都支持：
  origin_at_axis: true  → R = R_x(θ)，t = 轴点
  origin_at_axis: false → R = R_x(θ)，t = p − R·p（p = 轴点）
"""
import json
import math
import os

from swkit.geom import profiles


def run(spec):
    path = spec.path("jobs", "fold_transform.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ad = data["transform"]
    R = [ad[0:3], ad[3:6], ad[6:9]]
    t = ad[9:12]
    deg = data["deg"]
    ax = spec.params["axis"]
    p = [0.0, ax["y"] / 1000.0, ax["z"] / 1000.0]
    origin_at_axis = spec.project.options.get("origin_at_axis", True)

    print("动组 %s，角度 %.1f°" % (data["component"], deg))
    print("实测旋转：", [["%.4f" % v for v in row] for row in R],
          " 平移(mm)：[" + ", ".join("%.3f" % (v * 1000) for v in t) + "]")
    best = None
    for sign in (1, -1):
        th = math.radians(sign * deg)
        c, s = math.cos(th), math.sin(th)
        Rt = [[1, 0, 0], [0, c, -s], [0, s, c]]
        if origin_at_axis:
            want_t = p
        else:
            want_t = [p[i] - sum(Rt[i][j] * p[j] for j in range(3)) for i in range(3)]
        erm = max(max(abs(R[i][j] - Rt[i][j]) for j in range(3)) for i in range(3))
        et = max(abs(t[i] - want_t[i]) for i in range(3)) * 1000
        print("   理论 %+g°：矩阵差 %.2e，轴点偏差 %.4f mm" % (sign * deg, erm, et))
        if best is None or (et + erm * 1000) < (best[0] + best[2] * 1000):
            best = (et, sign, erm)
    et, sign, erm = best
    ok = et < 0.01 and erm < 1e-6
    print("折叠驱动核对：%s（实际绕铰轴 %+g° 旋转）" % ("PASS" if ok else "FAIL", sign * deg))

    ys, zs = [], []
    joint = spec.joint()
    cy, cz = ax["y"], ax["z"]
    ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    for m in spec.members:
        if m["group"] != joint["moving_group"]:
            continue
        polys, _ = profiles.section_of(spec.params, m)
        for outer, _holes in polys:
            for y, z in outer:
                ys.append(cy + (y - cy) * ca - (z - cz) * sa)
                zs.append(cz + (y - cy) * sa + (z - cz) * ca)
    print("   折叠后动组包围盒：y[%.1f, %.1f] z[%.1f, %.1f]（按同一 R 计算）" %
          (min(ys), max(ys), min(zs), max(zs)))
    with open(spec.path("report", "fold_check.json"), "w", encoding="utf-8") as f:
        json.dump({"deg": deg, "ok": ok, "R": R, "t": t,
                   "bbox_y": [min(ys), max(ys)], "bbox_z": [min(zs), max(zs)]}, f, indent=1)
    return 0 if ok else 1
