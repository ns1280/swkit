# -*- coding: utf-8 -*-
"""swkit 命令入口。

  swkit <command> <项目目录> [参数]

  jobs       spec → 作业文件 + plan.json（不需要 SolidWorks）
  check      规则检查（不需要 SolidWorks）
  preview    2D 出图（不需要 SolidWorks）
  build [构件]  建零件（需要 SolidWorks / cscript）
  asm [parts|subs|top]  子装配 + 总装 + 配合（需要 SolidWorks）
  verify     重开总装核对（需要 SolidWorks）
  regress    与基准模型对比（需要 SolidWorks + baseline 配置）
  fold [角度] 折叠态（需要 SolidWorks）
  shot       截图（需要 SolidWorks）
  docs [list|close]  列出/关闭本项目文档
  all        jobs → build → check → asm → verify
  new <目录>  新建项目骨架
"""
import json
import os
import subprocess
import sys

from swkit import __version__
from swkit.config import Project
from swkit.spec.load import Spec

try:                                   # Windows 控制台默认 GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

IS_WINDOWS = os.name == "nt"


def need_windows(cmd):
    if not IS_WINDOWS:
        raise SystemExit("`swkit %s` 只能在 Windows 侧运行（需要 SolidWorks COM）。" % cmd)


def plan_of(spec):
    p = spec.path("jobs", "plan.json")
    if not os.path.exists(p):
        raise SystemExit("找不到 %s；先跑 swkit jobs" % p)
    with open(p, encoding="utf-8") as f:
        return p, json.load(f)


def run_cscript(args):
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "cscript.exe")
    return subprocess.run([exe, "//nologo"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def cmd_jobs(spec):
    from swkit.geom import jobgen
    pp, plan = jobgen.make_plan(spec)
    print("作业文件 %d 个 → %s" % (len(plan["parts"]), pp))
    for p in plan["parts"]:
        print("   %-16s %-10s bbox y[%7.1f,%7.1f] z[%7.1f,%7.1f]" %
              (p["name"], p["kind"], p["bbox"][1], p["bbox"][4], p["bbox"][2], p["bbox"][5]))


def cmd_check(spec):
    from swkit.check import rules
    return rules.run(spec)


def cmd_preview(spec):
    from swkit.draw import preview
    preview.render_all(spec)


def cmd_build(spec, only=None):
    need_windows("build")
    pp, plan = plan_of(spec)
    state_path = os.path.join(plan["dirs"]["jobs"], "built.json")
    state = {}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    import hashlib
    from swkit.geom import jobgen

    vbs = os.path.join(os.path.dirname(jobgen.__file__), "data", "build_part.vbs")
    for p in plan["parts"]:
        if only and p["name"] != only:
            continue
        with open(p["job"], "rb") as f:
            h = hashlib.sha1(f.read()).hexdigest()
        if os.path.exists(p["out"]) and state.get(p["name"]) == h:
            print("跳过（未变化）", p["name"])
            continue
        r = run_cscript([vbs, p["job"], plan["part_template"]])
        out = (r.stdout or "").strip()
        print("   ", out or (r.stderr or "").strip())
        if r.returncode != 0 or not os.path.exists(p["out"]):
            raise SystemExit("零件生成失败：%s" % p["name"])
        state[p["name"]] = h
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
    print("零件目录：", plan["dirs"]["parts"])


def cmd_asm(spec, stage="all"):
    need_windows("asm")
    pp, plan = plan_of(spec)
    from swkit.asm import build_asm
    saved = sys.argv
    try:
        sys.argv = [saved[0], pp, stage]
        build_asm.main(pp)
    finally:
        sys.argv = saved


def cmd_verify(spec):
    need_windows("verify")
    pp, plan = plan_of(spec)
    from swkit.asm import verify_asm
    saved = sys.argv
    try:
        sys.argv = [saved[0], pp]
        return verify_asm.main(pp)
    finally:
        sys.argv = saved


def cmd_regress(spec):
    need_windows("regress")
    pp, plan = plan_of(spec)
    from swkit.check import regress
    return regress.main(pp)


def cmd_fold(spec, deg=None):
    need_windows("fold")
    pp, plan = plan_of(spec)
    from swkit.asm import fold
    from swkit.check import foldcheck
    saved = sys.argv
    try:
        sys.argv = [saved[0], pp] + ([str(deg)] if deg else [])
        fold.main(pp)
    finally:
        sys.argv = saved
    return foldcheck.run(spec)


def cmd_shot(spec):
    need_windows("shot")
    pp, plan = plan_of(spec)
    from swkit.asm import shot
    saved = sys.argv
    try:
        sys.argv = [saved[0], pp]
        shot.main(pp)
    finally:
        sys.argv = saved
    bmp = os.path.join(plan["dirs"]["preview"], "01_轴测.bmp")
    if os.path.exists(bmp):
        from PIL import Image
        png = bmp.replace(".bmp", ".png")
        Image.open(bmp).save(png)
        print("转换：", png)


def cmd_docs(spec, mode="list"):
    need_windows("docs")
    pp, plan = plan_of(spec)
    from swkit.asm import docs
    docs.main(mode, pp)


def cmd_new(target):
    root = os.path.abspath(target)
    for d in ("spec", "parts", "asm", "preview", "report", "jobs"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    cfg = os.path.join(root, "project.yaml")
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("# swkit 项目配置（几何尺寸放 spec/，这里只放工具链设置）\n"
                    "schema: 1\n"
                    "paths: {spec: spec, parts: parts, asm: asm, preview: preview, report: report, jobs: jobs}\n"
                    "solidworks:\n"
                    "  exe: 'D:\\SOLIDWORKS Corp\\SOLIDWORKS\\SLDWORKS.exe'\n"
                    "  part_template: 'C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2025\\templates\\gb_part.prtdot'\n"
                    "  asm_template: 'C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2025\\templates\\gb_assembly.asmdot'\n"
                    "options:\n"
                    "  origin_at_axis: true\n")
    print("已创建项目骨架：", root)
    print("下一步：写 spec/params.yaml、members.csv、joints.yaml、rules.yaml，然后 swkit jobs")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] in ("-V", "--version"):
        print("swkit", __version__)
        return 0
    cmd = argv[0]
    if cmd == "new":
        if len(argv) < 2:
            raise SystemExit("用法：swkit new <目录>")
        cmd_new(argv[1])
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 1
    spec = Spec(argv[1])
    arg = argv[2] if len(argv) > 2 else None

    if cmd == "jobs":
        cmd_jobs(spec)
    elif cmd == "check":
        return cmd_check(spec)
    elif cmd == "preview":
        cmd_preview(spec)
    elif cmd == "build":
        cmd_build(spec, arg)
    elif cmd == "asm":
        cmd_asm(spec, arg or "all")
    elif cmd == "verify":
        return cmd_verify(spec)
    elif cmd == "regress":
        return cmd_regress(spec)
    elif cmd == "fold":
        return cmd_fold(spec, arg)
    elif cmd == "shot":
        cmd_shot(spec)
    elif cmd == "docs":
        cmd_docs(spec, arg or "list")
    elif cmd == "all":
        cmd_jobs(spec)
        cmd_build(spec)
        rc = cmd_check(spec)
        if rc:
            print("规则检查未全部通过，继续装配（详见报告）")
        cmd_asm(spec)
        return cmd_verify(spec)
    else:
        print("未知命令", cmd)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
