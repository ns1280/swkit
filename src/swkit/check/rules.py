# -*- coding: utf-8 -*-
"""规则检查：表达式规则 + 2D 几何规则。输出 report/rules.json 与 rules.md。

2D 检查的方法边界：所有构件都是"Y-Z 断面沿 X 拉伸"，所以断面检查对该节点是精确的；
X 向是否可能接触用 X 区间重叠过滤。圆弧按 2° 弦角离散（见 geom/profiles.tessellate）。
"""
import json
import math
import os

from swkit.check import geom2d
from swkit.geom import profiles


def sections(spec):
    out = {}
    for m in spec.members:
        out[m.name] = profiles.section_of(spec.params, m)
    return out


def x_overlap(a, b):
    return not (a[1] < b[0] or b[1] < a[0])


def pairs(spec, secs):
    joint = spec.joint()
    allow = set()
    for a, b in joint.get("allow_contact", []):
        allow.add((a, b))
        allow.add((b, a))
    left = [m.name for m in spec.members if m["group"] == joint["fixed_group"]]
    right = [m.name for m in spec.members if m["group"] == joint["moving_group"]]
    out = []
    for a in left:
        for b in right:
            if not x_overlap(secs[a][1], secs[b][1]):
                continue
            out.append((a, b, (a, b) in allow))
    return out


def solids_at(secs, name, deg=0.0, center=(0.0, 0.0)):
    polys, _ = secs[name]
    if deg:
        return [geom2d.rotate_section(s, deg, center) for s in polys]
    return list(polys)


def scan(spec, secs, deg=0.0):
    """返回 (干涉对, 最小间隙及对应构件对)。"""
    joint = spec.joint()
    center = (joint["axis"]["y"], joint["axis"]["z"])
    hits, contacts = [], []
    best = (float("inf"), None)
    for a, b, allowed in pairs(spec, secs):
        sa = solids_at(secs, a)
        sb = solids_at(secs, b, deg, center)
        hit = False
        dist = float("inf")
        for pa in sa:
            for pb in sb:
                if not geom2d.bbox_overlap(geom2d.bbox(pa[0]), geom2d.bbox(pb[0])):
                    continue
                if geom2d.intersects(pa, pb):
                    hit = True
                    break
                dist = min(dist, geom2d.min_distance(pa, pb))
            if hit:
                break
        if hit:
            (contacts if allowed else hits).append((a, b))
        elif not allowed and dist < best[0]:
            best = (dist, (a, b))
    return hits, contacts, best


def run(spec):
    secs = sections(spec)
    results = []

    def add(rid, ok, detail, note=""):
        results.append({"id": rid, "ok": bool(ok), "detail": detail, "note": note})
        print("  %-22s %s  %s" % (rid, "PASS" if ok else "FAIL", detail))

    for r in spec.rules:
        t = r["type"]
        if t in ("eq", "gte"):
            got = spec.eval(r["expr"])
            want = spec.eval(r["expect"])
            ok = abs(got - want) <= r.get("tol", 1e-6) if t == "eq" else got >= want
            add(r["id"], ok, "%s = %.4g，要求 %s %.4g" %
                (r["expr"], got, "==" if t == "eq" else ">=", want), r.get("note", ""))
        elif t == "lug_x_gap":
            lugs = [m for m in spec.members if m["kind"] == "lug"]
            th = spec.params["lug"]["t"]
            spans = sorted(((m["xc"] + m["xoff"] - th / 2, m["xc"] + m["xoff"] + th / 2,
                             m["half"]) for m in lugs))
            gaps = [spans[i + 1][0] - spans[i][1] for i in range(len(spans) - 1)]
            g = min(gaps)
            add(r["id"], g >= r["expect"], "相邻耳板最小净距 %.1f mm（要求 >= %.1f）" % (g, r["expect"]),
                r.get("note", ""))
        elif t == "pin_coverage":
            pin = [m for m in spec.members if m["kind"] == "pin"][0]
            pl = spec.params["pin"]["len"]
            px0, px1 = pin["xc"] - pl / 2, pin["xc"] + pl / 2
            th = spec.params["lug"]["t"]
            xs = [(m["xc"] + m["xoff"] - th / 2, m["xc"] + m["xoff"] + th / 2)
                  for m in spec.members if m["kind"] == "lug"]
            margin = min(min(x[0] for x in xs) - px0, px1 - max(x[1] for x in xs))
            add(r["id"], margin >= r["expect"], "销轴端部余量 %.1f mm（要求 >= %.1f）" % (margin, r["expect"]),
                r.get("note", ""))
        elif t == "clearance2d":
            hits, contacts, best = scan(spec, secs, 0.0)
            add(r["id"], not hits,
                "干涉 %d 对；声明接触 %d 对；最小间隙 %.2f mm %s" %
                (len(hits), len(contacts), best[0], best[1]),
                ("穿透：" + "; ".join("%s×%s" % h for h in hits)) if hits else r.get("note", ""))
        elif t == "fold_scan":
            joint = spec.joint()
            f = joint["fold"]
            angles = []
            a = f["from_deg"]
            while a <= f["to_deg"] + 1e-9:
                angles.append(a)
                a += f["step_deg"]
            collisions = {}
            for ang in angles:
                hits, _, _ = scan(spec, secs, ang)
                for h in hits:
                    collisions.setdefault(h, []).append(ang)
            detail = "扫描 %d 个姿态（%g→%g°，步长 %g°）" % (len(angles), f["from_deg"], f["to_deg"], f["step_deg"])
            if collisions:
                first = min(min(v) for v in collisions.values())
                detail += "；%d 对构件在折叠中穿透，最早 %.1f°" % (len(collisions), first)
            else:
                detail += "；未发现干涉"
            add(r["id"], not collisions, detail, r.get("note", ""))
            for (a, b), angs in sorted(collisions.items()):
                print("      穿透 %s × %s：角度 %s" % (a, b, ", ".join("%g" % x for x in angs)))
        else:
            add(r["id"], False, "未知规则类型 " + t)

    os.makedirs(spec.path("report"), exist_ok=True)
    with open(spec.path("report", "rules.json"), "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=1)
    lines = ["# 规则检查报告", "", "项目：%s；几何来源：%s" % (spec.params["project"], spec.params.get("source")),
             "", "| 规则 | 结果 | 实测 | 说明 |", "| --- | --- | --- | --- |"]
    for r in results:
        lines.append("| %s | %s | %s | %s |" % (r["id"], "PASS" if r["ok"] else "**FAIL**",
                                                r["detail"], r["note"]))
    lines += ["", "方法边界：2D 断面检查（Y-Z，X 区间过滤）；圆弧按 2° 弦角离散；",
              "折叠为离散姿态扫描，不证明连续全程无碰撞。", ""]
    with open(spec.path("report", "rules.md"), "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    n_fail = sum(1 for r in results if not r["ok"])
    print("规则检查：%d 项，%d 项未通过 → report/rules.md" % (len(results), n_fail))
    return 1 if n_fail else 0
