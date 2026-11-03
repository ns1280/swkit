# -*- coding: utf-8 -*-
"""按 plan.json 建子装配与总装：半内为焊接组（固定），半间按 joints.yaml 的 mates 建配合。

Windows 侧执行：python -m swkit asm <project>
"""
import json
import math
import os
import sys

from swkit.asm import swhelp as H


def base(path):
    return os.path.splitext(os.path.basename(path))[0]


def build_sub(sw, plan, sub):
    asm = sw.NewDocument(plan["asm_template"], 0, 0, 0)
    if asm is None:
        raise SystemExit("新建装配体失败")
    print("== 子装配", sub["group"], "（原点在铰轴）" if sub.get("origin_at_axis") else "")
    shift = sub.get("loc_shift", [0.0, 0.0, 0.0])
    for name in sub["parts"]:
        p = [x for x in plan["parts"] if x["name"] == name][0]
        c = [p["center"][i] + shift[i] for i in range(3)]
        comp = H.insert(sw, asm, p["out"], c)
        print("   插入", name, "->", comp.Name2)
    H.fix_all(asm)
    p = H.ptr(asm)
    # 原点在铰轴时，子装配局部坐标里铰轴就在 (0,0)
    if sub.get("origin_at_axis"):
        H.create_axis(p, 0.0, 0.0, "HINGE_AXIS")
    else:
        H.create_axis(p, plan["axis"]["y"], plan["axis"]["z"], "HINGE_AXIS")
    H.swraw.call(p, "EditRebuild3")
    centres = H.centres(asm)
    err = 0.0
    for name in sub["parts"]:
        spec_p = [x for x in plan["parts"] if x["name"] == name][0]
        cname = [k for k in centres if k.rsplit("-", 1)[0] == base(spec_p["out"])]
        if cname:
            c = centres[cname[0]][0]
            want = [spec_p["center"][i] + shift[i] for i in range(3)]
            e = max(abs(c[i] - want[i]) for i in range(3)) * 1000
            err = max(err, e)
            print("   位置核对 %-16s 误差 %.3f mm" % (name, e))
    print("   最大位置误差 %.3f mm" % err)
    if err > 0.5:
        raise SystemExit("插入位置超差，需按实测偏差二遍重插")
    asm.SaveAs3(sub["file"], 0, 0)
    print("   保存", sub["file"], os.path.exists(sub["file"]))
    sw.CloseDoc(asm.GetTitle)


def _plane_ref(md, which):
    """组件的三个基准面：front / top / right（按特征树顺序）。md 是原始指针。"""
    front, top, right = H.planes_of(md)
    return {"front": front, "top": top, "right": right}[which]


def select_ref(p, ext, plan, comps, suffix, ref, append):
    """选中一个配合引用。ref 形式：
       {"plane": "right"|"top"|"front", "group": "J1_L"}
       {"bore": "J1_L"}
    """
    if "plane" in ref:
        g = ref["group"]
        comp_name = comps[g]
        comp = _COMP_PTR[g]
        md_obj = comp.GetModelDoc2
        if md_obj is None:
            raise SystemExit("取不到组件文档：" + comp_name)
        md = H.ptr(md_obj)
        pl = _plane_ref(md, ref["plane"])
        nm = H.bstr(H.swraw.call(pl, "Name", prop=True))
        full = nm + "@" + comp_name + suffix
        r = H.swraw.call(ext, "SelectByID2", (full, "PLANE", 0.0, 0.0, 0.0, append, 0, None, 0))
        ok = r.vt == 11 and bytes(r.v)[0] != 0
        print("      选择面 %-44s %s" % (full, ok))
        return ok
    if "bore" in ref:
        g = ref["bore"]
        info = H.select_bore(p, plan["bores"][g], append=append)
        ok = info["ok"] and info.get("seltype") == 2
        print("      选择孔 %-8s %s r=%.3f（期望 %.3f）" %
              (g, ok, info.get("radius_mm", -1), info.get("expect_mm", -1)))
        return ok
    raise SystemExit("未知配合引用：" + repr(ref))


_COMP_PTR = {}


def comps_ptr(comps, g):
    return _COMP_PTR[g]


def create_mate(p, mtype, align, extra=None, name=None, count=2):
    md = H.swraw.var_ptr(H.swraw.call(p, "CreateMateData", (mtype,)))
    if not md:
        return {"created": False, "err": "CreateMateData 返回空"}
    sm = H.swraw.var_ptr(H.swraw.call(p, "SelectionManager", prop=True))
    ents = []
    for i in range(count):
        ptr = H.swraw.var_ptr(H.swraw.call(sm, "GetSelectedObject6", (i + 1, -1)))
        if not ptr:
            return {"created": False, "err": "取实体失败 #%d" % (i + 1)}
        ents.append(ptr)
    H.swraw.call(md, "EntitiesToMate", (H.swraw.make_dispatch_array(ents),), put=True)
    skipped = []
    for k, v in [("MateAlignment", align), ("LockRotation", False)] + list((extra or {}).items()):
        try:
            H.swraw.call(md, k, (v,), put=True)
        except OSError:
            skipped.append(k)
    try:
        m = H.swraw.call(p, "CreateMate", (H.swraw.RawPtr(md, H.swraw.VT_DISPATCH),))
    except OSError as exc:
        return {"created": False, "err": "CreateMate: %s" % exc}
    fp = H.swraw.var_ptr(m)
    info = {"created": bool(fp), "err": "" if fp else "CreateMate 返回空", "skipped": skipped}
    if fp:
        if name:
            try:
                H.swraw.call(fp, "Name", (name,), put=True)
            except OSError:
                pass
        info["name"] = H.bstr(H.swraw.call(fp, "Name", prop=True))
        info["type"] = H.bstr(H.swraw.call(fp, "GetTypeName2", prop=True))
    return info


def build_top(sw, plan):
    asm = sw.NewDocument(plan["asm_template"], 0, 0, 0)
    print("== 总装", plan["project"])
    comps = {}
    for sub in plan["subs"]:
        comp = H.insert(sw, asm, sub["file"], sub["center"])
        comps[sub["group"]] = comp.Name2
        _COMP_PTR[sub["group"]] = comp
        print("   插入", sub["group"], "->", comp.Name2)
    fixed_name = comps[plan["top"]["fixed"]]
    H.fix_all(asm, only=fixed_name.rsplit("-", 1)[0])
    p = H.ptr(asm)
    H.report(asm, "插入后/固定基准半")
    H.create_axis(p, plan["axis"]["y"], plan["axis"]["z"], "HINGE_AXIS")
    print("   活动文档：", H.activate(sw, asm.GetTitle))
    suffix = "@" + os.path.splitext(asm.GetTitle)[0]
    ext = H.extension(p)

    created = []
    for mate in plan["top"]["mates"]:
        mtype = H.MATE_TYPE[mate["type"]]
        align = H.ALIGN.get(mate.get("align", "closest"), 2)
        extra = {}
        if mate["type"] == "angle":
            extra["Angle"] = math.radians(mate.get("work_deg", 0))
        print("   配合 %-14s type=%s align=%s" % (mate["name"], mate["type"], mate.get("align")))
        H.swraw.call(p, "ClearSelection2", (True,))
        ok_a = select_ref(p, ext, plan, comps, suffix, mate["a"], False)
        ok_b = ok_a and select_ref(p, ext, plan, comps, suffix, mate["b"], True)
        if not (ok_a and ok_b):
            print("      !! 选择失败，跳过")
            continue
        r = create_mate(p, mtype, align, extra, name=mate["name"])
        print("      创建=%s name=%s type=%s %s" %
              (r["created"], r.get("name"), r.get("type"), r.get("err", "")))
        if r["created"]:
            created.append(mate["name"])
        H.swraw.call(p, "EditRebuild3")

    angle = plan["top"]["angle_name"]
    if angle in created:
        ok, msg = H.set_mate_angle(p, angle, math.radians(plan["top"]["work_deg"]))
        print("   工作角读数：", msg)
    else:
        print("   !! 角度配合未建立，折叠驱动不可用")

    with open(os.path.join(plan["dirs"]["jobs"], "asm_state.json"),
              "w", encoding="utf-8") as f:
        json.dump({"angle_mate": angle, "angle_created": angle in created}, f,
                  ensure_ascii=False, indent=1)

    H.swraw.call(p, "EditRebuild3")
    centres = H.centres(asm)
    for sub in plan["subs"]:
        cname = [k for k in centres if k.rsplit("-", 1)[0] == base(sub["file"])]
        if cname:
            c, b = centres[cname[0]]
            e = max(abs(c[i] - sub["center"][i]) for i in range(3)) * 1000
            print("   %-6s 中心误差 %.3f mm；bbox y[%.1f,%.1f] z[%.1f,%.1f]" %
                  (sub["group"], e, b[2] * 1000, b[3] * 1000, b[4] * 1000, b[5] * 1000))
    for sub in plan["subs"]:
        if not sub.get("origin_at_axis"):
            continue
        for c in H.swraw.array_items(H.swraw.call(p, "GetComponents", (False,))):
            nm = H.bstr(H.swraw.call(c, "Name2", prop=True))
            if "/" in nm or nm.rsplit("-", 1)[0] != base(sub["file"]):
                continue
            v = H.swraw.call(c, "Transform2", prop=True)
            ad = H.swraw.array_items(H.swraw.call(H.swraw.var_ptr(v), "ArrayData", prop=True))
            want = [0.0, plan["axis"]["y"], plan["axis"]["z"]]
            err = max(abs(ad[9 + i] - want[i]) for i in range(3)) * 1000
            print("   动半原点 (%s) 误差 %.3f mm（应为铰轴上）" %
                  (", ".join("%.1f" % (ad[9 + i] * 1000) for i in range(3)), err))
    try:
        n = H.swraw.call(H.extension(p), "GetWhatsWrongCount", prop=True)
        print("   GetWhatsWrongCount =", n.v[0] if hasattr(n, "v") else n)
    except Exception as exc:
        print("   GetWhatsWrongCount 读取失败", exc)
    H.shot_iso_zup(asm, os.path.join(plan["dirs"]["preview"], "01_轴测.bmp"))
    asm.SaveAs3(plan["top"]["file"], 0, 0)
    print("   保存", plan["top"]["file"], os.path.exists(plan["top"]["file"]))
    sw.CloseDoc(asm.GetTitle)


def main(plan_path=None):
    if plan_path is None:
        plan_path = sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    sw = H.connect(exe=plan.get("solidworks_exe"))
    print("SolidWorks", sw.RevisionNumber)
    stage = sys.argv[2] if len(sys.argv) > 2 else "all"
    if stage in ("all", "parts"):
        for part in plan["parts"]:
            n = H.color_part(sw, part["out"], part["color"])
            print("上色 %-16s 实体 %d" % (part["name"], n))
    if stage in ("all", "subs"):
        for sub in plan["subs"]:
            build_sub(sw, plan, sub)
    if stage in ("all", "top"):
        build_top(sw, plan)
    print("done")


if __name__ == "__main__":
    main()

