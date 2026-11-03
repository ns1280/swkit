# -*- coding: utf-8 -*-
"""构件类型库：kind + params + 实例 → 拉伸特征（Y-Z 草图，沿 X 拉伸）。

形状逻辑在这里，尺寸全部来自 spec。新增构件类型 = 在这里加一个函数 + members.csv 加一行。
坐标与 V07 一致：草图在右视面（Y-Z），u=-z、v=y，拉伸沿 X。
"""
import math


def line(y1, z1, y2, z2):
    return ("line", (y1, z1, y2, z2))


def arc(cy, cz, sy, sz, ey, ez, direction):
    return ("arc", (cy, cz, sy, sz, ey, ez, direction))


def circle(cy, cz, r):
    return ("circle", (cy, cz, r))


def poly(points):
    """闭合多边形 → 线段序列。"""
    return [line(points[i][0], points[i][1],
                 points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1])
            for i in range(len(points))]


def rect(y0, y1, z0, z1):
    return poly([(y0, z0), (y1, z0), (y1, z1), (y0, z1)])


def feat(name, entities, depth, start, merge=False):
    return {"name": name, "entities": entities,
            "depth": depth, "start": start, "merge": merge}


# ---------------------------------------------------------------- 构件类型

def beam(p, m):
    b = p["beam"]
    s = m.side
    xc = m["xc"]
    yw, yc = s * b["y_wall"], s * b["y_seam"]
    zt = b["top"]
    ztf = zt - b["tf"]                    # 顶翼缘底
    bs, bw = b["bot_seam"], b["bot_wall"]
    ty = s * b["taper_y"]
    w = b["width"]
    return [
        feat("TOP_FLANGE", rect(yc, yw, zt, ztf), w, xc - w / 2, True),
        feat("BOT_FLANGE", poly([(yw, bw), (ty, bs), (yc, bs),
                                 (yc, bs + b["tf"]), (ty, bs + b["tf"]), (yw, bw + b["tf"])]),
             w, xc - w / 2, True),
        feat("WEB", poly([(yw, ztf), (yc, ztf), (yc, bs + b["tf"]),
                          (ty, bs + b["tf"]), (yw, bw + b["tf"])]),
             b["tw"], xc - b["tw"] / 2, True),
    ]


def seam_plate(p, m):
    sp = p["seam_plate"]
    s = m.side
    w = p["beam"]["width"]
    return [feat("SEAMPLATE", rect(s * sp["t"], 0, sp["z0"], sp["z1"]),
                 w, m["xc"] - w / 2)]


def pad(p, m):
    pd = p["pad"]
    s = m.side
    return [feat("PAD", rect(s * pd["y0"], s * pd["y1"], pd["z0"], pd["z1"]),
                 pd["x"], m["xc"] - pd["x"] / 2)]


def lug(p, m):
    lg = p["lug"]
    s = m.side
    ax = p["axis"]
    r = lg["eye_r"]
    y_out, y_in = s * lg["y_out"], s * lg["y_in"]
    z_base = p["pad"]["z1"]
    z_top = lg["z_top"]
    z_r = ax["z"] - math.sqrt(r * r - y_in * y_in)        # 眼环与脚底内边交点
    y_t = s * math.sqrt(r * r - (z_top - ax["z"]) ** 2)   # 眼环与脚顶交点
    ent = [
        line(y_out, z_base, y_in, z_base),
        line(y_in, z_base, y_in, z_r),
        arc(0, ax["z"], y_in, z_r, y_t, z_top, -s),
        line(y_t, z_top, y_out, z_top),
        line(y_out, z_top, y_out, z_base),
    ]
    if lg.get("bore", 0) > 0:
        ent.append(circle(0, ax["z"], lg["bore"] / 2.0))
    return [feat("LUG", ent, lg["t"], m["xc"] + m["xoff"] - lg["t"] / 2)]


def pin(p, m):
    return [feat("PIN", [circle(p["axis"]["y"], p["axis"]["z"], p["pin"]["d"] / 2.0)],
                 p["pin"]["len"], m["xc"] - p["pin"]["len"] / 2)]


BUILDERS = {
    "beam": beam,
    "seam_plate": seam_plate,
    "pad": pad,
    "lug": lug,
    "pin": pin,
}


def features_of(params, member):
    try:
        return BUILDERS[member["kind"]](params, member)
    except KeyError:
        raise SystemExit("未知构件类型 kind=%s（在 toolkit/geom/profiles.py 注册）" % member["kind"])


# ---------------------------------------------------------------- 2D 断面

def tessellate(entities, chord_deg=2.0):
    """返回 (外轮廓点列, [孔轮廓点列])。圆弧按弦角离散，仅用于 2D 检查与出图。"""
    outer = []
    holes = []
    for kind, a in entities:
        if kind == "line":
            outer.append((a[0], a[1]))
        elif kind == "arc":
            cy, cz, sy, sz, ey, ez, d = a
            r = math.hypot(sy - cy, sz - cz)
            a0 = math.atan2(sz - cz, sy - cy)
            a1 = math.atan2(ez - cz, ey - cy)
            if d > 0:
                while a1 <= a0:
                    a1 += 2 * math.pi
            else:
                while a1 >= a0:
                    a1 -= 2 * math.pi
            n = max(8, int(abs(a1 - a0) / math.radians(chord_deg)))
            for i in range(n):
                t = a0 + (a1 - a0) * i / n
                outer.append((cy + r * math.cos(t), cz + r * math.sin(t)))
        elif kind == "circle":
            cy, cz, r = a
            pts = [(cy + r * math.cos(2 * math.pi * i / 96),
                    cz + r * math.sin(2 * math.pi * i / 96)) for i in range(96)]
            if outer:
                holes.append(pts)
            else:
                outer.extend(pts)
    return outer, holes


def section_of(params, member):
    """构件的 Y-Z 断面：[(外轮廓, [孔])]，以及 X 区间。"""
    feats = features_of(params, member)
    x0 = min(f["start"] for f in feats)
    x1 = max(f["start"] + f["depth"] for f in feats)
    polys = [tessellate(f["entities"]) for f in feats]
    return polys, (x0, x1)


def bbox_of(params, member):
    polys, (x0, x1) = section_of(params, member)
    ys = [pt[0] for outer, holes in polys for pt in outer]
    zs = [pt[1] for outer, holes in polys for pt in outer]
    return (x0, min(ys), min(zs), x1, max(ys), max(zs))
