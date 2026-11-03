# -*- coding: utf-8 -*-
"""不依赖 SolidWorks 的回归测试：spec → 作业文件 → 规则检查。

    python -m unittest discover -s tests
"""
import json
import os
import shutil
import tempfile
import unittest

from swkit.check import rules
from swkit.geom import jobgen
from swkit.spec.load import Spec

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "examples", "J1")


class J1PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swkit_")
        self.proj = os.path.join(self.tmp, "J1")
        shutil.copytree(EXAMPLE, self.proj)
        self.spec = Spec(self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spec_load(self):
        self.assertEqual(self.spec.params["project"], "J1")
        self.assertEqual(len(self.spec.members), 10)
        self.assertEqual(self.spec.params["axis"]["z"], -75)

    def test_jobs_and_plan(self):
        pp, plan = jobgen.make_plan(self.spec)
        self.assertTrue(os.path.exists(pp))
        self.assertEqual(len(plan["parts"]), 10)
        self.assertEqual(set(plan["bores"]), {"J1_L", "J1_R"})
        self.assertAlmostEqual(plan["bores"]["J1_L"]["r"], 0.0205, places=6)
        self.assertAlmostEqual(plan["bores"]["J1_R"]["x"], 1.465, places=6)
        self.assertAlmostEqual(plan["top"]["fold_expect"]["z"][1], 2.413, places=3)
        mates = [m["type"] for m in plan["top"]["mates"]]
        self.assertEqual(mates, ["concentric", "coincident", "angle"])

    def test_job_text_is_metric(self):
        m = [x for x in self.spec.members if x.name == "L_PIN-2"][0]
        text = jobgen.job_text(self.spec, m)
        self.assertIn("CIRCLE\t0.000000000\t-0.075000000\t0.020000000", text)
        self.assertIn("EXTRUDE\t0.150000000\t1.425000000", text)

    def test_rules_all_pass(self):
        pp, _plan = jobgen.make_plan(self.spec)
        self.assertEqual(rules.run(self.spec), 0)
        with open(self.spec.path("report", "rules.json"), encoding="utf-8") as f:
            rows = json.load(f)
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(r["ok"] for r in rows))


if __name__ == "__main__":
    unittest.main()
