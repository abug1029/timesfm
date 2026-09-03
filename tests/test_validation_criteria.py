"""v2 固化判据单元测试 (S1 - 审核建议补全)。
覆盖 5 条规则 + Phase 4d 6 品种 fixture + 边界 (EV=0 / n=350)。"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from phase4d_parse_results import verdict, _replace_dominates


def m(n, ev, pf, maxdd, mape, diracc):
    return dict(n=n, ev=ev, pf=pf, maxdd=maxdd, mape=mape, diracc=diracc)


# Phase 4d 实测 fixtures
CF_B = m(396, -0.029, 0.94, -35.19, 1.66, 51)
CF_A = m(396, +0.043, 1.09, -34.83, 1.51, 56)
SR_B = m(396, +0.076, 1.17, -19.55, 1.08, 55)
SR_A = m(396, +0.093, 1.21, -9.81, 1.09, 57)
SP_B = m(396, +0.167, 1.40, -33.76, 1.91, 57)
SP_A = m(396, +0.157, 1.38, -37.99, 1.78, 57)
SP_R = m(396, +0.071, 1.15, -66.44, 1.89, 55)
UR_B = m(303, +0.002, 1.00, -57.71, 2.56, 54)
UR_A = m(303, +0.035, 1.07, -76.31, 2.61, 53)
M_B  = m(396, +0.061, 1.13, -29.90, 2.62, 52)
M_R  = m(396, +0.108, 1.24, -21.72, 1.87, 56)
JD_B = m(396, +0.042, 1.09, -49.04, 2.50, 50)
JD_R = m(396, +0.045, 1.09, -33.92, 2.49, 50)


class TestV2Verdict(unittest.TestCase):
    def test_cf_additive_rule3_ev_flip(self):
        s, tag, _ = verdict(CF_B, CF_A)
        self.assertEqual(s, "GREEN-EV")
        self.assertEqual(tag, "Rule3")

    def test_sr_additive_rule4_maxdd_green(self):
        s, tag, _ = verdict(SR_B, SR_A)
        self.assertEqual(s, "GREEN-MAXDD")
        self.assertEqual(tag, "Rule4")

    def test_sp_additive_ordinary_r2_pass(self):
        s, tag, _ = verdict(SP_B, SP_A)
        self.assertEqual(s, "PASS")
        self.assertIn("ordinary", tag)

    def test_sp_replace_ordinary_fail(self):
        # SP replace: ordinary 未达 (MAPE 1.0%<3%), 返回 FAIL (非 R1-VETO, 因 ordinary 先失败)
        s, tag, _ = verdict(SP_B, SP_R)
        self.assertEqual(s, "FAIL")
        self.assertNotEqual(tag, "R1-VETO")

    def test_cf_replace_r1_veto(self):
        # CF replace: ordinary 达标 (MAPE 5.4%) 但 MaxDD 恶化 43.5% -> R1-VETO
        CF_R = m(396, -0.035, 0.93, -50.50, 1.57, 52)
        s, tag, _ = verdict(CF_B, CF_R)
        self.assertEqual(s, "FAIL")
        self.assertEqual(tag, "R1-VETO")

    def test_ur_underpowered_rule5(self):
        s, tag, _ = verdict(UR_B, UR_A)
        self.assertEqual(s, "UNDERPOWERED")

    def test_m_replace_ordinary_pass(self):
        s, tag, _ = verdict(M_B, M_R)
        self.assertEqual(s, "PASS")
        self.assertIn("ordinary", tag)

    def test_jd_replace_rule4_green(self):
        s, tag, _ = verdict(JD_B, JD_R)
        self.assertEqual(s, "GREEN-MAXDD")
        self.assertEqual(tag, "Rule4")

    def test_r2_guard_veto(self):
        # 仅 MAPE 达标 + PF 退化 >2% -> R2-GUARD 否决
        base = m(396, +0.10, 1.20, -20.0, 2.00, 50)
        cand = m(396, +0.10, 1.10, -20.0, 1.50, 50)  # MAPE -25% 达标, PF -8.3% 退化>2%
        s, tag, _ = verdict(base, cand)
        self.assertEqual(s, "FAIL")
        self.assertEqual(tag, "R2-GUARD")

    def test_ev_zero_boundary_not_rule3(self):
        # baseline EV==0 不触发 Rule3 (严格 b_ev<0)
        base = m(396, 0.0, 1.00, -20.0, 2.00, 50)
        cand = m(396, +0.05, 1.10, -15.0, 1.50, 53)  # MaxDD 改善 + DirAcc+3 -> Rule4 or ordinary
        s, tag, _ = verdict(base, cand)
        self.assertNotEqual(s, "GREEN-EV")

    def test_n_350_boundary(self):
        # n=350 不 underpowered; n=349 且 FAIL -> underpowered
        base = m(350, +0.05, 1.10, -20.0, 2.00, 50)
        cand_fail = m(350, +0.05, 1.10, -25.0, 1.99, 50)  # 全未达
        s, _, _ = verdict(base, cand_fail)
        self.assertEqual(s, "FAIL")
        cand_fail_349 = m(349, +0.05, 1.10, -25.0, 1.99, 50)
        s2, _, _ = verdict(base, cand_fail_349)
        self.assertEqual(s2, "UNDERPOWERED")

    def test_replace_dominates(self):
        M_ADD = m(396, +0.087, 1.19, -27.91, 1.96, 55)
        self.assertTrue(_replace_dominates(M_R, M_ADD))   # M replace 全维不劣于 additive
        self.assertFalse(_replace_dominates(SP_R, SP_A))  # SP replace 劣于 additive (不 dominate)


if __name__ == "__main__":
    unittest.main()
