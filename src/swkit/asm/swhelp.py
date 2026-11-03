# -*- coding: utf-8 -*-
"""SolidWorks 装配通用操作（Windows Python + comtypes + swraw）。

只依赖标准库与本包 sw/；不读 spec，全部输入来自 plan.json。
插入位置：AddComponent5 的 X/Y/Z 按"包围盒中心"解释，因此直接传 spec 算出的中心，
插完再实测核对；误差超限时按实测偏差二遍重插（沿用 V07 总装的可靠做法）。
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swraw                                    # noqa: E402
from swattach import attach                     # noqa: E402

MATE_TYPE = {"coincident": 0, "concentric": 1, "angle": 6}
ALIGN = {"aligned": 0, "anti": 1, "closest": 2, "closest_aligned": 2}


SLDWORKS_EXE = r"D:\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe"


def connect(timeout=240, exe=None):
    """连上 SolidWorks；没运行就启动它并等待 COM 可用。"""
    import subprocess
    import time

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    started = False
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            sw = attach()
            sw.Visible = True
            if started:
                print("SolidWorks 启动完成（%.0f s）" % (time.time() - t0))
            return sw
        except Exception as exc:
            if not started:
                print("连接失败（%s），启动 SolidWorks…" % exc)
                try:
                    subprocess.Popen([exe or SLDWORKS_EXE])
                except Exception as exc2:
                    raise SystemExit("无法启动 SolidWorks：%s" % exc2)
                started = True
            time.sleep(5)
    raise SystemExit("SolidWorks 在 %d s 内没有就绪" % timeout)


def activate(sw, title):
    """激活指定文档，返回活动文档标题。逐个试不同签名，避免 comtypes 重载解析问题。"""
    app = ptr(sw)
    for name, args in (("ActivateDoc3", (title, True, 0, 0)),
                       ("ActivateDoc2", (title, False, 0)),
                       ("ActivateDoc", (title,))):
        try:
            swraw.call(app, name, args)
            break
        except OSError:
            continue
    doc = swraw.var_ptr(swraw.call(app, "ActiveDoc", prop=True))
    return bstr(swraw.call(doc, "GetTitle", prop=True)) if doc else ""


def ptr(obj):
    return swraw.ptr_of(obj._comobj)


def bstr(v):
    return swraw.var_bstr(v)


def planes_of(p):
    out = []
    f = swraw.call(p, "FirstFeature")
    while f.vt in (9, 13):
        fp = swraw.var_ptr(f)
        if not fp:
            break
        if bstr(swraw.call(fp, "GetTypeName2", prop=True)) == "RefPlane":
            out.append(fp)
            if len(out) == 3:
                break
        f = swraw.call(fp, "GetNextFeature")
    return out                                   # front, top, right


def find_feature(p, type_name):
    out = []
    f = swraw.call(p, "FirstFeature")
    while f.vt in (9, 13):
        fp = swraw.var_ptr(f)
        if not fp:
            break
        if bstr(swraw.call(fp, "GetTypeName2", prop=True)) == type_name:
            out.append(fp)
        f = swraw.call(fp, "GetNextFeature")
    return out


def create_axis(p, y, z, name="HINGE_AXIS"):
    """在零件/装配体内建参考轴：Y=y（Front 偏移）与 Z=z（Top 偏移）两平面的交线。"""
    front, top, _ = planes_of(p)
    fm = ptr_of_feature_manager(p)
    swraw.call(p, "ClearSelection2", (True,))
    swraw.call(top, "Select2", (False, 0))
    zp = swraw.var_ptr(swraw.call(fm, "InsertRefPlane", (8, z, 0, 0.0, 0, 0.0)))
    if not zp:
        raise SystemExit("Z 参考面失败")
    swraw.call(p, "ClearSelection2", (True,))
    if abs(y) > 1e-12:
        swraw.call(front, "Select2", (False, 0))
        yp = swraw.var_ptr(swraw.call(fm, "InsertRefPlane", (8, y, 0, 0.0, 0, 0.0)))
        front = yp
    swraw.call(front, "Select2", (False, 0))
    swraw.call(zp, "Select2", (True, 0))
    swraw.call(p, "InsertAxis2", (True,))
    axes = find_feature(p, "RefAxis")
    if not axes:
        raise SystemExit("参考轴创建失败")
    swraw.call(axes[-1], "Name", (name,), put=True)
    return axes[-1]


def ptr_of_feature_manager(p):
    return swraw.var_ptr(swraw.call(p, "FeatureManager", prop=True))


def extension(p):
    return swraw.var_ptr(swraw.call(p, "Extension", prop=True))


def insert(sw, asm, path, center):
    kind = 2 if path.upper().endswith(".SLDASM") else 1
    if sw.OpenDoc(path, kind) is None:
        raise SystemExit("预加载失败 " + path)
    comp = asm.AddComponent5(path, 0, "", False, "", center[0], center[1], center[2])
    if comp is None:
        raise SystemExit("插入失败 " + path)
    return comp


def comp_box(c, base=(0.0, 0.0, 0.0)):
    """c 为 GetComponents 枚举出的原始组件指针。"""
    cp = c
    v = swraw.call(cp, "Transform2", prop=True)
    ad = swraw.array_items(swraw.call(swraw.var_ptr(v), "ArrayData", prop=True))
    tx, ty, tz = ad[9] + base[0], ad[10] + base[1], ad[11] + base[2]
    md = swraw.var_ptr(swraw.call(cp, "GetModelDoc2", prop=True))
    title = bstr(swraw.call(md, "GetTitle", prop=True)).upper()
    if title.endswith(".SLDASM"):
        xs, ys, zs = [], [], []
        for s in swraw.array_items(swraw.call(md, "GetComponents", (False,))):
            if "/" in bstr(swraw.call(s, "Name2", prop=True)):
                continue
            b = comp_box(s, (tx, ty, tz))
            xs += [b[0], b[1]]       # comp_box 返回 (xmin,xmax,ymin,ymax,zmin,zmax)
            ys += [b[2], b[3]]
            zs += [b[4], b[5]]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    xs, ys, zs = [], [], []
    for bp in swraw.array_items(swraw.call(md, "GetBodies2", (-1, True))):
        b = swraw.array_items(swraw.call(bp, "GetBodyBox"))
        xs += [b[0], b[3]]
        ys += [b[1], b[4]]
        zs += [b[2], b[5]]
    return (min(xs) + tx, max(xs) + tx, min(ys) + ty, max(ys) + ty, min(zs) + tz, max(zs) + tz)


def centres(asm):
    """顶层组件：{组件名: (包围盒中心, 包围盒)}，单位米。"""
    p = ptr(asm)
    out = {}
    for c in swraw.array_items(swraw.call(p, "GetComponents", (False,))):
        nm = bstr(swraw.call(c, "Name2", prop=True))
        if "/" in nm:
            continue
        b = comp_box(c)
        out[nm] = (((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2), b)
    return out


def fix_all(asm, only=None):
    p = ptr(asm)
    for c in swraw.array_items(swraw.call(p, "GetComponents", (False,))):
        nm = bstr(swraw.call(c, "Name2", prop=True))
        if "/" in nm:
            continue
        if only and only not in nm:
            continue
        cp = c
        asm.ClearSelection2(True)
        swraw.call(cp, "Select4", (False, None, False))
        asm.FixComponent()


def report(asm, label):
    p = ptr(asm)
    print("   [%s]" % label)
    for c in swraw.array_items(swraw.call(p, "GetComponents", (False,))):
        nm = bstr(swraw.call(c, "Name2", prop=True))
        if "/" in nm:
            continue
        fixed = swraw.call(c, "IsFixed")
        b = comp_box(c)
        print("     %-14s fixed=%s bbox x[%.0f,%.0f] y[%.0f,%.0f] z[%.0f,%.0f]" %
              (nm, fixed.v[0] if hasattr(fixed, "v") else fixed,
               b[0] * 1000, b[1] * 1000, b[2] * 1000, b[3] * 1000,
               b[4] * 1000, b[5] * 1000))


def mate(asm, mtype, a1, t1, a2, t2, angle=0.0):
    p = ptr(asm)
    ext = extension(p)
    errbuf = ctypes.c_long(0)
    errptr = ctypes.cast(ctypes.byref(errbuf), ctypes.c_void_p).value
    swraw.call(p, "ClearSelection2", (True,))
    r1 = swraw.call(ext, "SelectByID2", (a1, t1, 0.0, 0.0, 0.0, False, 0, None, 0))
    r2 = swraw.call(ext, "SelectByID2", (a2, t2, 0.0, 0.0, 0.0, True, 0, None, 0))
    h1 = bytes(r1.v)[0] != 0 if r1.vt == 11 else False
    h2 = bytes(r2.v)[0] != 0 if r2.vt == 11 else False
    if not (h1 and h2):
        return {"mate": mtype, "a": a1, "b": a2, "sel": (h1, h2), "object": None,
                "created": False, "err": "选择失败"}
    m = swraw.call(p, "AddMate5", (MATE_TYPE[mtype], ALIGN_CLOSEST, False,
                                   0.0, 0.0, 0.0, 1.0, 1.0,
                                   angle, 0.0, 0.0, False, False, 0,
                                   swraw.RawPtr(errptr, 0x4003)))
    fp = swraw.var_ptr(m)
    return {"mate": mtype, "a": a1, "b": a2, "sel": (h1, h2), "object": m,
            "created": bool(fp), "err": errbuf.value}


# 视角预设：模板默认"Y 向上"，本结构 Z 向上，从默认轴测绕 Z 转 90° 即得 Z 向上。
# 每次 ViewRotate* 约 15°，6 次 = 90°（与录制宏 ViewRotateplusx/minusy 同一类调用）。
VIEW_ISO_Z_UP = ["ViewRotateminusz"] * 6


def shot_iso_zup(doc, out_bmp, calls=None):
    p = ptr(doc)
    swraw.call(p, "ShowNamedView2", ("", 7))
    for c in (calls or VIEW_ISO_Z_UP):
        swraw.call(p, c)
    swraw.call(p, "ViewZoomtofit2")
    swraw.call(p, "ViewDisplayShaded")
    swraw.call(p, "SaveBMP", (out_bmp, 1600, 1000))


def screenshots(asm, prefix, views=((7, "iso"), (4, "yz"), (1, "xy"))):
    p = ptr(asm)
    for view, tag in views:
        swraw.call(p, "ShowNamedView2", ("", view))
        swraw.call(p, "ViewZoomtofit2")
        swraw.call(p, "ViewDisplayShaded")
        swraw.call(p, "SaveBMP", (prefix + "_" + tag + ".bmp", 1600, 1100))


def mate_v2(p, mtype, names, extra=None, name=None, align=1):
    """按 SW 2025 新 API 建配合：CreateMateData → EntitiesToMate → CreateMate。

    names: [(实体名, 选择类型)]，组件内实体必须带 @组件-1@装配体名。
    extra: 额外 MateData 属性，如 {"Distance": 0.0} / {"Angle": 0.0}。
    """
    ext = extension(p)
    swraw.call(p, "ClearSelection2", (True,))
    for i, (nm, tp) in enumerate(names):
        r = swraw.call(ext, "SelectByID2", (nm, tp, 0.0, 0.0, 0.0, i > 0, 0, None, 0))
        if not (r.vt == 11 and bytes(r.v)[0] != 0):
            return {"created": False, "err": "选择失败: " + nm, "object": None}
    return _create_mate(p, mtype, extra, name, count=len(names), align=align)


def mate_v2_ray(p, mtype, rays, extra=None, name=None, align=1):
    """射线选面后建配合。rays: [(点(x,y,z), 方向(dx,dy,dz)), ...]，单位米。"""
    ext = extension(p)
    swraw.call(p, "ClearSelection2", (True,))
    for i, (pt, dv) in enumerate(rays):
        r = swraw.call(ext, "SelectByRay", (pt[0], pt[1], pt[2], dv[0], dv[1], dv[2],
                                            0.0006, 2, i > 0, 0, 0))
        if not (r.vt == 11 and bytes(r.v)[0] != 0):
            return {"created": False, "err": "射线未选中 #%d" % (i + 1), "object": None}
    return _create_mate(p, mtype, extra, name, count=len(rays), align=align)


def _create_mate(p, mtype, extra, name, count=2, align=1):
    sm = swraw.var_ptr(swraw.call(p, "SelectionManager", prop=True))
    ents = []
    for i in range(count):
        ptr = swraw.var_ptr(swraw.call(sm, "GetSelectedObject6", (i + 1, -1)))
        if not ptr:
            return {"created": False, "err": "取实体失败 #%d" % (i + 1), "object": None}
        ents.append(ptr)
    md = swraw.var_ptr(swraw.call(p, "CreateMateData", (mtype,)))
    if not md:
        return {"created": False, "err": "CreateMateData 返回空（可能需 QI 到 IAssemblyDoc）", "object": None}
    try:
        swraw.call(md, "EntitiesToMate", (make_array(ents),), put=True)
    except OSError as exc:
        return {"created": False, "err": "EntitiesToMate: %s" % exc, "object": None}
    # 不同配合类型的 MateData 暴露的属性不同，逐个尝试，缺哪个就跳过
    skipped = []
    for k, v in [("MateAlignment", align), ("LockRotation", False)] + list((extra or {}).items()):
        try:
            swraw.call(md, k, (v,), put=True)
        except OSError:
            skipped.append(k)
    try:
        m = swraw.call(p, "CreateMate", (swraw.RawPtr(md, swraw.VT_DISPATCH),))
    except OSError as exc:
        return {"created": False, "err": "CreateMate: %s" % exc, "object": None}
    fp = swraw.var_ptr(m)
    if fp and name:
        try:
            swraw.call(fp, "Name", (name,), put=True)
        except OSError:
            pass
    return {"created": bool(fp), "err": "" if fp else "CreateMate 返回空",
            "object": m, "skipped": skipped}


def make_array(ents):
    """对象数组：SW 的 MateData 接受 VT_ARRAY|VT_DISPATCH。"""
    return swraw.make_dispatch_array(ents)


def mate_dimension(p, name):
    """角度/距离配合的尺寸指针：先试 D1@名称，再走 FeatureByName + 显示尺寸。"""
    dim = swraw.var_ptr(swraw.call(p, "Parameter", ("D1@" + name,)))
    if dim:
        return dim, "D1@" + name
    f = swraw.var_ptr(swraw.call(p, "FeatureByName", (name,)))
    if not f:
        return 0, "配合特征未找到"
    dds = swraw.array_items(swraw.call(f, "GetDisplayDimensions"))
    if not dds:
        return 0, "无显示尺寸"
    d = swraw.var_ptr(swraw.call(dds[0], "GetDimension"))
    return d, "DisplayDimension"


def set_mate_angle(p, name, radians):
    dim, how = mate_dimension(p, name)
    if not dim:
        return False, how
    swraw.call(dim, "SystemValue", (radians,), put=True)
    swraw.call(p, "EditRebuild3")
    back = swraw.call(dim, "SystemValue", prop=True)
    return True, "%s：目标 %.6f rad，读回 %.6f rad" % (how, radians, swraw.var_double(back))


def color_part(sw, path, rgb):
    doc = sw.OpenDoc(path, 1)
    if doc is None:
        raise SystemExit("上色时打不开 " + path)
    p = ptr(doc)
    bodies = swraw.array_items(swraw.call(p, "GetBodies2", (-1, True)))
    for bp in bodies:
        swraw.call(bp, "MaterialPropertyValues2",
                   (swraw.make_r8_array([rgb[0], rgb[1], rgb[2], 0.55, 0.72, 0.35, 0.55, 0.0, 0.0]),),
                   put=True)
    swraw.call(p, "EditRebuild3")
    swraw.call(p, "Save")
    sw.CloseDoc(path)
    return len(bodies)

def select_bore(p, bore, append=False):
    """射线选中孔内圆柱面：起点在孔壁外的材料内（半径 r+10mm），朝轴心打。

    bore: {"x","y","z","r"}，米。返回 {"ok", "seltype", "radius_mm", "expect_mm"}。
    """
    ext = extension(p)
    x, y, z, r = bore["x"], bore["y"], bore["z"], bore["r"]
    sx, sy, sz = x, y, z + r + 0.010
    rr = swraw.call(ext, "SelectByRay", (sx, sy, sz, 0.0, 0.0, -1.0,
                                         0.0002, 2, append, 0, 0))
    ok = rr.vt == 11 and bytes(rr.v)[0] != 0
    info = {"ok": ok, "ray": (sx, sy, sz), "expect_mm": round(r * 1000, 3)}
    if ok:
        sm = swraw.var_ptr(swraw.call(p, "SelectionManager", prop=True))
        ot = swraw.call(sm, "GetSelectedObjectType3", (1, -1))
        o = swraw.var_ptr(swraw.call(sm, "GetSelectedObject6", (1, -1)))
        info["seltype"] = ot.v[0] if hasattr(ot, "v") else ot
        surf = swraw.var_ptr(swraw.call(o, "GetSurface", prop=True)) if info["seltype"] == 2 else 0
        if surf:
            prm = swraw.array_items(swraw.call(surf, "CylinderParams", prop=True))
            info["radius_mm"] = round(prm[6] * 1000, 3)
    return info

