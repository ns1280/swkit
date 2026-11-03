# -*- coding: utf-8 -*-
"""2D 断面几何：旋转、相交、最小距离。无第三方依赖。

断面 = (外轮廓, [孔轮廓])，点为 (y, z)，单位 mm。
只统计"严格穿越"：共线贴合、端点接触不算干涉（对接面因此不会被误报）。
"""
import math

EPS = 1e-7


def rotate(poly, deg, center=(0.0, 0.0)):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    cy, cz = center
    return [(cy + (y - cy) * c - (z - cz) * s,
             cz + (y - cy) * s + (z - cz) * c) for y, z in poly]


def rotate_section(sec, deg, center):
    outer, holes = sec
    return (rotate(outer, deg, center), [rotate(h, deg, center) for h in holes])


def bbox(poly):
    ys = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    return min(ys), min(zs), max(ys), max(zs)


def bbox_overlap(a, b, tol=0.0):
    return not (a[2] < b[0] - tol or b[2] < a[0] - tol or
                a[3] < b[1] - tol or b[3] < a[1] - tol)


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def seg_cross(a, b, c, d):
    """严格相交（不含接触/共线）。"""
    o1, o2 = _orient(a, b, c), _orient(a, b, d)
    o3, o4 = _orient(c, d, a), _orient(c, d, b)
    return (o1 * o2 < -EPS) and (o3 * o4 < -EPS)


def edges(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def point_in_poly(pt, poly):
    """1 内 / 0 边界 / -1 外。"""
    y, z = pt
    for a, b in edges(poly):
        if abs(_orient(a, b, pt)) < 1e-6:
            if min(a[0], b[0]) - 1e-9 <= y <= max(a[0], b[0]) + 1e-9 and \
               min(a[1], b[1]) - 1e-9 <= z <= max(a[1], b[1]) + 1e-9:
                return 0
    inside = False
    for a, b in edges(poly):
        if (a[1] > z) != (b[1] > z):
            yc = a[0] + (z - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if yc > y:
                inside = not inside
    return 1 if inside else -1


def _contours(sec):
    outer, holes = sec
    return [outer] + list(holes)


def intersects(a, b):
    """两个断面（含孔）是否有材料重叠。"""
    if not bbox_overlap(bbox(a[0]), bbox(b[0])):
        return False
    for pa in _contours(a):
        for pb in _contours(b):
            if not bbox_overlap(bbox(pa), bbox(pb)):
                continue
            for a1, a2 in edges(pa):
                for b1, b2 in edges(pb):
                    if seg_cross(a1, a2, b1, b2):
                        return True
    # 无边界穿越：只可能相离或包含。孔内不算材料。
    for pt in a[0]:
        r = point_in_poly(pt, b[0])
        if r == 1 and all(point_in_poly(pt, h) != 1 for h in b[1]):
            return True
    for pt in b[0]:
        r = point_in_poly(pt, a[0])
        if r == 1 and all(point_in_poly(pt, h) != 1 for h in a[1]):
            return True
    return False


def _seg_dist(a, b, c, d):
    if seg_cross(a, b, c, d):
        return 0.0

    def pt_seg(p, u, v):
        vx, vz = v[0] - u[0], v[1] - u[1]
        L2 = vx * vx + vz * vz
        if L2 < 1e-18:
            return math.hypot(p[0] - u[0], p[1] - u[1])
        t = max(0.0, min(1.0, ((p[0] - u[0]) * vx + (p[1] - u[1]) * vz) / L2))
        return math.hypot(p[0] - u[0] - t * vx, p[1] - u[1] - t * vz)
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def min_distance(a, b):
    """断面间最小距离（仅在外轮廓之间度量，供间隙报告用）。"""
    best = float("inf")
    for a1, a2 in edges(a[0]):
        for b1, b2 in edges(b[0]):
            best = min(best, _seg_dist(a1, a2, b1, b2))
            if best <= 0:
                return 0.0
    return best
