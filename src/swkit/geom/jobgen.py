# -*- coding: utf-8 -*-
"""由 spec 生成 SolidWorks 作业文件（.job，米制）和执行计划 plan.json。

分工：spec/check/preview 不需要 SolidWorks；build/asm 只读 plan.json，不再解释 spec。
plan.json 里的路径一律是 Windows 形式，方便 cscript / COM 直接使用。
"""
import json
import math
import os

from swkit.geom import profiles

COLORS = {
    "beam": (0.90, 0.42, 0.10),
    "seam_plate": (0.33, 0.40, 0.50),
    "pad": (0.79, 0.70, 0.54),
    "lug": (0.30, 0.60, 0.35),
    "pin": (0.78, 0.16, 0.16),
}


def win(path):
    """WSL 路径 → Windows 路径（只处理 /mnt/<盘>，不依赖外部命令）。"""
    path = os.path.abspath(path)
    if path.startswith("/mnt/") and len(path) > 6:
        drive = path[5].upper()
        return drive + ":" + path[6:].replace("/", "\\")
    return path


def job_text(spec, member):
    feats = profiles.features_of(spec.params, member)
    out = spec.path("parts", member.name + ".SLDPRT")
    lines = ["TEMPLATE\t" + win(spec.project.sw["part_template"]),
             "OUT\t" + win(out),
             "PREVIEW\t" + win(spec.path("preview", member.name + ".bmp"))]
    for f in feats:
        lines.append("FEAT\t" + f["name"])
        for kind, a in f["entities"]:
            if kind == "line":
                lines.append("LINE\t" + "\t".join("%.9f" % (v / 1000.0) for v in a))
            elif kind == "arc":
                lines.append("ARC\t" + "\t".join("%.9f" % (v / 1000.0) for v in a[:6])
                             + "\t%d" % a[6])
            elif kind == "circle":
                lines.append("CIRCLE\t" + "\t".join("%.9f" % (v / 1000.0) for v in a))
        lines.append("EXTRUDE\t%.9f\t%.9f\t%d" % (f["depth"] / 1000.0,
                                                 f["start"] / 1000.0, 1 if f["merge"] else 0))
    return "\n".join(lines) + "\n"


def bores_of(spec, joint):
    """每个需要同心配合的半，取一个带孔的耳板，给出选面用的射线数据（米）。"""
    groups = set()
    for mate in joint.get("mates", []):
        for side in ("a", "b"):
            ref = mate.get(side) or {}
            if "bore" in ref:
                groups.add(ref["bore"])
    out = {}
    axis_y = spec.params["axis"]["y"]
    axis_z = spec.params["axis"]["z"]
    for g in groups:
        cand = [m for m in spec.members
                if m["group"] == g and m["kind"] == "lug"
                and spec.params["lug"].get("bore", 0) > 0]
        if not cand:
            continue
        m = cand[0]
        out[g] = {"x": (m["xc"] + m["xoff"]) / 1000.0,
                  "y": axis_y / 1000.0,
                  "z": axis_z / 1000.0,
                  "r": spec.params["lug"]["bore"] / 2000.0,
                  "part": m.name}
    return out


def make_plan(spec):
    spec.project.ensure_dirs()
    parts = []
    for m in spec.members:
        jp = spec.path("jobs", m.name + ".job")
        with open(jp, "w", encoding="utf-8") as f:
            f.write(job_text(spec, m))
        box = profiles.bbox_of(spec.params, m)
        parts.append({
            "name": m.name, "kind": m["kind"], "half": m["half"], "group": m["group"],
            "job": win(jp), "out": win(spec.path("parts", m.name + ".SLDPRT")),
            "bbox": box, "center": [(box[0] + box[3]) / 2000.0, (box[1] + box[4]) / 2000.0,
                                    (box[2] + box[5]) / 2000.0],
            "color": COLORS.get(m["kind"], (0.7, 0.7, 0.7)),
        })
    joint = spec.joint()
    project = spec.params.get("project", "ASM")
    axis_pt = [0.0, spec.params["axis"]["y"] / 1000.0, spec.params["axis"]["z"] / 1000.0]
    origin_at_axis = spec.project.options.get("origin_at_axis", True)

    subs = []
    for gname, info in joint["subassemblies"].items():
        ps = [p for p in parts if p["group"] == gname]
        box = [min(p["bbox"][0] for p in ps), min(p["bbox"][1] for p in ps),
               min(p["bbox"][2] for p in ps), max(p["bbox"][3] for p in ps),
               max(p["bbox"][4] for p in ps), max(p["bbox"][5] for p in ps)]
        center = [(box[0] + box[3]) / 2000.0, (box[1] + box[4]) / 2000.0,
                  (box[2] + box[5]) / 2000.0]
        at_axis = origin_at_axis and gname == joint["moving_group"]
        shift = [-axis_pt[0], -axis_pt[1], -axis_pt[2]] if at_axis else [0.0, 0.0, 0.0]
        subs.append({"group": gname, "file": win(spec.path("asm", info["file"])),
                     "parts": [p["name"] for p in ps],
                     "bbox": box, "center": center,
                     "origin_at_axis": at_axis, "loc_shift": shift})

    # 折叠后动组的理论包围盒（Windows 侧实测核对用）：X 不变，Y-Z 绕轴旋转
    angle_mate = [m for m in joint["mates"] if m["type"] == "angle"][-1]
    fold_deg = angle_mate.get("fold_deg", 90)
    ca, sa = math.cos(math.radians(fold_deg)), math.sin(math.radians(fold_deg))
    ay, az = spec.params["axis"]["y"], spec.params["axis"]["z"]
    ys, zs = [], []
    for p in parts:
        if p["group"] != joint["moving_group"]:
            continue
        m = [x for x in spec.members if x.name == p["name"]][0]
        polys, _ = profiles.section_of(spec.params, m)
        for outer, _holes in polys:
            for y, z in outer:
                ys.append(ay + (y - ay) * ca - (z - az) * sa)
                zs.append(az + (y - ay) * sa + (z - az) * ca)
    fold_expect = {"deg": fold_deg, "group": joint["moving_group"],
                   "y": [min(ys) / 1000.0, max(ys) / 1000.0],
                   "z": [min(zs) / 1000.0, max(zs) / 1000.0],
                   "origin": axis_pt}

    plan = {
        "project": project,
        "project_dir": win(spec.dir),
        "part_template": win(spec.project.sw["part_template"]),
        "asm_template": win(spec.project.sw["asm_template"]),
        "solidworks_exe": win(spec.project.sw["exe"]),
        "axis": {"y": spec.params["axis"]["y"] / 1000.0,
                 "z": spec.params["axis"]["z"] / 1000.0},
        "parts": parts, "subs": subs,
        "dirs": {k: win(spec.path(k)) for k in ("jobs", "preview", "asm", "report", "parts")},
        "bores": bores_of(spec, joint),
        "baseline": spec.project.baseline,
        "lug_bore": spec.params.get("lug", {}).get("bore", 0),
        "lug_t": spec.params.get("lug", {}).get("t", 0),
        "top": {"file": win(spec.path("asm", project + "_ASM.SLDASM")),
                "fold_file": win(spec.path("asm", "%s_ASM_FOLD%g.SLDASM" % (project, fold_deg))),
                "fixed": joint["fixed_group"], "moving": joint["moving_group"],
                "mates": joint["mates"],
                "angle_name": angle_mate.get("name", "FOLD_ANGLE"),
                "angle_dimension": angle_mate.get("dimension", "D1@FOLD_ANGLE"),
                "work_deg": angle_mate.get("work_deg", 0),
                "fold_deg": fold_deg,
                "fold_expect": fold_expect},
    }
    pp = spec.path("jobs", "plan.json")
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    return pp, plan
