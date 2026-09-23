"""e1v: derived ratios from the printed outputs of e1v_oracle.py / e1v_runs.py / e1v_rescore.py (values copied verbatim).

Run:  python3 analysis/e1v_summary.py
"""
MY_O, AN_O = 6_290_539, 6_216_635            # e1v_oracle (mine) / e1v_rescore (analyst plan re-scored)
MY_NOCAP_CELL, AN_NOCAP_CELL = 6_428_556, 6_292_681
TP, TEMPLATE_MED = 5_681_740, -357_948        # e1v_runs
MISS_TOTAL, MISS_SCREEN, MISS_CUT = 1_254_872.594, 943_853, 203_300
TP_NOCUT = 6_165_292

print(f"my oracle - analyst oracle = {MY_O - AN_O:,}")
print(f"cell-level nocap: mine - analyst = {MY_NOCAP_CELL - AN_NOCAP_CELL:,}")
print(f"template median % of my oracle = {100 * TEMPLATE_MED / MY_O:.1f}%")
print(f"planner gap (my oracle - true planner) = {MY_O - TP:,}; planner cut cost {TP_NOCUT - TP:,} = {(TP_NOCUT - TP) / (MY_O - TP):.0%} of it")
print(f"missing-cell regret from risk screen = {MISS_SCREEN / MISS_TOTAL:.1%}; screen / 10-cut = {MISS_SCREEN / MISS_CUT:.1f}x")
