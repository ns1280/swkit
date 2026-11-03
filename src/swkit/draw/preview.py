# -*- coding: utf-8 -*-
"""由 spec 直接出 2D 图（不启动 SolidWorks）：工作态断面、折叠姿态、X 向立面。

图与模型共用同一份 spec，避免"示意图一套数、模型另一套数"。
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon, Circle

from swkit.check import geom2d
from swkit.geom import profiles

FONT = r"C:\Windows\Fonts\simhei.ttf" if os.name == "nt" else "/mnt/c/Windows/Fonts/simhei.ttf"
if os.path.exists(FONT):
    font_manager.fontManager.addfont(FONT)
    plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COLORS = {"beam": "#e68a2e", "seam_plate": "#54687d", "pad": "#c9b28a",
          "lug": "#4d9959", "pin": "#c72929"}
LABEL = {"beam": "横梁", "seam_plate": "缝处端板", "pad": "垫板", "lug": "耳板", "pin": "销轴"}


def style(ax, title):
    ax.set_aspect("equal")
    ax.set_xlabel("Y (mm)", fontsize=8)
    ax.set_ylabel("Z (mm)", fontsize=8)
    ax.set_title(title, fontsize=11)
    ax.tick_params(labelsize=7)
    ax.grid(True, lw=0.3, alpha=0.4)


def draw_member(ax, spec, m, deg=0.0, alpha=1.0, center=(0, 0)):
    polys, _ = profiles.section_of(spec.params, m)
    for outer, holes in polys:
        if deg:
            outer = geom2d.rotate(outer, deg, center)
            holes = [geom2d.rotate(h, deg, center) for h in holes]
        ax.add_patch(Polygon(outer, closed=True, facecolor=COLORS[m["kind"]],
                             edgecolor="#222222", lw=0.6, alpha=alpha, zorder=3))
        for h in holes:
            ax.add_patch(Polygon(h, closed=True, facecolor="white",
                                 edgecolor="#222222", lw=0.5, zorder=4))


def dim_h(ax, y0, y1, z, text):
    ax.annotate("", xy=(y0, z), xytext=(y1, z), arrowprops=dict(arrowstyle="<->", lw=0.7))
    ax.text((y0 + y1) / 2, z, text, fontsize=7.5, ha="center", va="bottom")


def section(spec):
    proj = spec.params.get("project", "ASM")
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for m in spec.members:
        draw_member(ax, spec, m)
    ax.plot(0, spec.params["axis"]["z"], "+", color="red", ms=14, mew=1.6, zorder=6)
    ax.text(60, spec.params["axis"]["z"] + 40, "%s 轴 (Y=0, Z=%g)" % (proj, spec.params["axis"]["z"]),
            color="red", fontsize=8)
    zt = spec.params["beam"]["top"]
    ax.axhline(zt, color="#888888", lw=0.6, ls="--")
    ax.text(-680, zt + 25, "梁顶 / 压型板顶 Z=%g（接口，未建压型板）" % zt, fontsize=7.5, color="#555555")
    dim_h(ax, 0, spec.params["lug"]["y_out"], -230, "垫板/耳板脚 %g…%g" %
          (spec.params["pad"]["y0"], spec.params["pad"]["y1"]))
    ax.text(-680, -520, "缝处端板 %g 厚，Z %g…%g" % (spec.params["seam_plate"]["t"],
            spec.params["seam_plate"]["z1"], spec.params["seam_plate"]["z0"]), fontsize=8)
    ax.text(-680, -700, "梁全长 %g（图只显示缝侧 ±700）" % spec.params["beam"]["y_wall"], fontsize=8)
    ax.text(-680, 120, "耳板 R%g，孔 φ%g / 销 φ%g" % (spec.params["lug"]["eye_r"],
            spec.params["lug"]["bore"], spec.params["pin"]["d"]), fontsize=8)
    style(ax, "%s 中央折叠铰 · 工作态断面（X=%g 处，由 spec 直接生成）" % (proj, spec.params["beam"]["xc"]))
    xlim = spec.project.options.get("preview_xlim", [-700, 700])
    ylim = spec.project.options.get("preview_ylim", [-780, 220])
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    fig.tight_layout()
    out = spec.path("preview", "02_%s_断面.png" % proj)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def fold_poses(spec):
    joint = spec.joint()
    center = (joint["axis"]["y"], joint["axis"]["z"])
    angles = [0, 30, 60, 90]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, ang in zip(axes.ravel(), angles):
        for m in spec.members:
            if m["group"] == joint["fixed_group"]:
                draw_member(ax, spec, m, alpha=0.85)
            else:
                draw_member(ax, spec, m, deg=ang, center=center, alpha=0.85)
        ax.plot(*center, "+", color="red", ms=12, mew=1.4)
        style(ax, "折叠 %d°（左半固定，右半绕轴）" % ang)
        ax.set_xlim(-800, 900)
        ax.set_ylim(-800, 1000 if ang else 300)
    fig.tight_layout()
    out = spec.path("preview", "_optional", "折叠姿态_参考.png")
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def elevation(spec):
    """X-Z 立面：看耳板/销轴沿 X 的叠层与净距。"""
    fig, ax = plt.subplots(figsize=(10, 5))
    for m in spec.members:
        box = profiles.bbox_of(spec.params, m)
        x0, x1 = box[0], box[3]
        z0, z1 = box[2], box[5]
        ax.add_patch(Polygon([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], closed=True,
                             facecolor=COLORS[m["kind"]], edgecolor="#222222",
                             lw=0.7, alpha=0.55 if m["half"] == "R" else 0.9))
        ax.text((x0 + x1) / 2, z1 + 12, m.name, fontsize=7, ha="center", rotation=25)
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title("%s 节点 X-Z 立面（L 深色 / R 浅色，耳板与销轴的 X 向叠层）" %
                 spec.params.get("project", "ASM"), fontsize=11)
    ax.grid(True, lw=0.3, alpha=0.4)
    ax.set_xlim(spec.params["beam"]["xc"] - 200, spec.params["beam"]["xc"] + 200)
    ax.set_ylim(-220, 120)
    fig.tight_layout()
    out = spec.path("preview", "03_%s_立面.png" % spec.params.get("project", "ASM"))
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def render_all(spec):
    os.makedirs(spec.path("preview"), exist_ok=True)
    os.makedirs(spec.path("preview", "_optional"), exist_ok=True)
    for fn in (section, fold_poses, elevation):
        out = fn(spec)
        print("出图：", out)
