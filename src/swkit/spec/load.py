# -*- coding: utf-8 -*-
"""spec 读取：project.yaml + params.yaml + members.csv + joints.yaml + rules.yaml。

所有尺寸 mm；坐标系约定 X 纵向、Y 横向、Z 向上（项目可覆盖，但几何代码按此写）。
"""
import csv
import os
import types

import yaml

from swkit.config import Project


class Member(dict):
    @property
    def name(self):
        return "%s_%s" % (self["half"], self["id"])

    @property
    def side(self):
        return -1 if self["half"] == "L" else 1


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = prefix + k if not prefix else prefix + "." + k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


class Spec(object):
    def __init__(self, project_dir):
        self.project = Project(project_dir)
        self.dir = self.project.dir
        sd = self.project.path("spec")
        with open(os.path.join(sd, "params.yaml"), encoding="utf-8") as f:
            self.params = yaml.safe_load(f)
        with open(os.path.join(sd, "joints.yaml"), encoding="utf-8") as f:
            self.joints = yaml.safe_load(f)["joints"]
        with open(os.path.join(sd, "rules.yaml"), encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)["rules"]
        self.members = []
        with open(os.path.join(sd, "members.csv"), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row["id"] or row["id"].startswith("#"):
                    continue
                m = Member(row)
                m["xc"] = float(row["xc"])
                m["xoff"] = float(row.get("xoff") or 0)
                self.members.append(m)
        self.flat = flatten(self.params)

    def joint(self, name=None):
        if name is None:
            name = next(iter(self.joints))
        return self.joints[name]

    def path(self, kind, *parts):
        return self.project.path(kind, *parts)

    def eval(self, expr):
        if isinstance(expr, (int, float)):
            return float(expr)

        def ns(d):
            if isinstance(d, dict):
                return types.SimpleNamespace(**{k: ns(v) for k, v in d.items()})
            return d
        scope = {k: ns(v) for k, v in self.params.items() if isinstance(v, dict)}
        return float(eval(expr, {"__builtins__": {}}, scope))
