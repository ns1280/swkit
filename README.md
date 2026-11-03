# swkit

先写 spec，再生成 SolidWorks 零件与装配；规则、2D 图、增量重建、实测核对、与基准回归都在同一条链上。

## 安装

```powershell
D:\miniconda3\envs\data-analysis\python.exe -m pip install -e F:\swkit
```

Windows 侧依赖：`pyyaml`、`matplotlib`、`pillow`、`comtypes`（安装时自动带）。
Linux 侧只能用 `jobs / check / preview / new`；`build / asm / verify / regress / fold / shot` 需要
SolidWorks 2025 与本机 COM。

## 快速开始

```powershell
swkit new  F:\Group\me\PROJ          # 生成目录骨架
# 写 PROJ\spec\{params.yaml,members.csv,joints.yaml,rules.yaml}
swkit jobs    PROJ                   # spec → jobs/*.job + jobs/plan.json
swkit check   PROJ                   # 规则检查（不开 SolidWorks）
swkit preview PROJ                   # 2D 断面/折叠/立面
swkit build   PROJ                   # 建零件（增量：作业未变则跳过）
swkit asm     PROJ                   # 子装配 + 总装 + 配合
swkit verify  PROJ                   # 重开核对
swkit regress PROJ                   # 与 baseline 逐件比 bbox/体积
swkit fold    PROJ 90                # 折叠态 + 变换核对
swkit shot    PROJ                   # 轴测截图
```

## 项目配置 `project.yaml`

几何只在 `spec/`；`project.yaml` 只放工具链设置：

```yaml
schema: 1
paths: {spec: spec, parts: parts, asm: asm, preview: preview, report: report, jobs: jobs}
solidworks:
  exe: 'D:\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe'
  part_template: '...gb_part.prtdot'
  asm_template: '...gb_assembly.asmdot'
baseline:                 # 可选；缺省时 regress 跳过
  dir: '...\LJQ_FLOOR_V07'
  parts: {L: F-L.SLDPRT, R: F-R.SLDPRT}
  bbox_tol_mm: 1.0
  volume_tol_pct: 1.0
options:
  origin_at_axis: true    # 动半装配原点放在铰轴上
```

## 配合怎么写（`joints.yaml`）

```yaml
mates:
  - {name: CONCENTRIC, type: concentric, a: {bore: J1_L}, b: {bore: J1_R}, align: closest}
  - {name: RIGHT,      type: coincident, a: {plane: right, group: J1_L}, b: {plane: right, group: J1_R}, align: aligned}
  - {name: FOLD_ANGLE, type: angle,      a: {plane: top, group: J1_L},   b: {plane: top, group: J1_R},
     work_deg: 0, fold_deg: 90, dimension: D1@FOLD_ANGLE}
```

- `{bore: 组名}`：该组耳板孔内圆柱面，射线由 spec 的孔径/孔位算出，不写死坐标。
- `{plane: right|top|front, group: 组名}`：该组子装配的基准面。
- 同心必须 `align: closest`；`anti` 会得到翻转解。

## 已知边界

- `plan.json` 里是 Windows 绝对路径；换机需把项目放回同一路径（或改 `project.yaml` 后重跑 `jobs`）。
- 作业文件与 `.vbs` 走 ANSI/ASCII；项目路径请保持 ASCII，避免中文路径在 cscript 侧解析异常。
- 2D 检查是 Y-Z 断面 + X 区间过滤；圆弧按 2° 弦角离散，不替代 3D 干涉。
- 承载、焊缝、公差、制造可行性不在本工具范围。
