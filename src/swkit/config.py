# -*- coding: utf-8 -*-
"""项目配置：读取 <project>/project.yaml，提供路径与 SolidWorks 设置。

设计原则：几何尺寸只在 spec/ 里；project.yaml 只放"工具链怎么跑"的东西
（目录、SolidWorks 路径、回归基准、配合选项）。
"""
import os

import yaml

SCHEMA = 1

DEFAULT_PATHS = {
    "spec": "spec",
    "parts": "parts",
    "asm": "asm",
    "preview": "preview",
    "report": "report",
    "jobs": "jobs",
}

DEFAULT_SW = {
    "exe": r"D:\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
    "part_template": r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_part.prtdot",
    "asm_template": r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_assembly.asmdot",
}


class ConfigError(SystemExit):
    pass


class Project(object):
    def __init__(self, root):
        self.dir = os.path.abspath(root)
        cfg_path = os.path.join(self.dir, "project.yaml")
        self.cfg = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f) or {}
        schema = self.cfg.get("schema", SCHEMA)
        if schema != SCHEMA:
            raise ConfigError("project.yaml schema=%s，本工具只支持 %s" % (schema, SCHEMA))
        self.paths = dict(DEFAULT_PATHS)
        self.paths.update(self.cfg.get("paths") or {})
        self.sw = dict(DEFAULT_SW)
        self.sw.update(self.cfg.get("solidworks") or {})
        self.baseline = self.cfg.get("baseline") or None
        self.options = self.cfg.get("options") or {}

    def path(self, kind, *parts):
        return os.path.join(self.dir, self.paths[kind], *parts)

    def ensure_dirs(self):
        for kind in self.paths:
            os.makedirs(self.path(kind), exist_ok=True)
