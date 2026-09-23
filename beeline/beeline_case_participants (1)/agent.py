"""
Beeline tariff campaign agent.

Pipeline (deterministic, no randomness of our own):
  1. prior      — data/change_tariff.csv -> shrunk relative-ARPU effect x conversion share
                  per (current_tariff, arpu_segment, target). History is a different
                  subscriber sample, so it is only a prior (wide sd), never a revealed effect.
  2. pilots     — greedy value-of-information loop: each step pilots the hypothesis whose
                  (cell ARPU mass x posterior sd x density near the decision threshold) is
                  largest, sized so the pilot can actually move the decision. Gaussian
                  posterior update with the environment's stated noise 0.804/sqrt(n_actual).
  3. calibrate  — pilots re-centre the prior for hypotheses we could not afford to test.
  4. plan       — risk-adjusted lift (mu - sd) per cell, best target per cell, channel per
                  cell chosen by a Lagrangian allocation over the remaining money and reach,
                  packed into <=10 disjoint campaigns of <=5000 subscribers each.

Effects in the scorer depend on (current_tariff, arpu_segment, target_tariff) and scale
each subscriber's predicted_arpu; data/call segments only partition audiences, so they
are used here purely to size campaigns.
"""
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

NOISE_SD = 0.804            # per-customer sd of observed relative lift (environment.py)
PRIOR_SD = 0.30             # base-unit prior sd when history has the transition
PRIOR_SD_FALLBACK = 0.40    # ... when it does not
SHRINK_K = 15               # pseudo-count for hierarchical shrinkage of history means
KAPPA = 0.5                 # risk premium: deploy/value on mu - KAPPA*sd (half a posterior sd)
Z_PILOT = 2.0               # pilot sized so that z-score vs. threshold ~ Z_PILOT
PILOT_CHANNEL = "sms"       # cheap, still 0.65x signal; push halves the signal-to-noise
PILOT_N_MIN, PILOT_N_MAX = 60, 200
PILOT_MONEY_SHARE = 0.25    # never spend more than this share of total budget on pilots
PILOT_REACH_SHARE = 0.25
TARGETS_PER_CELL = 3        # top prior targets kept as hypotheses per cell
MIN_CELL = 20
MAX_CAMPAIGNS, MAX_PER_CAMPAIGN = 10, 5000
ARPU_BINS, ARPU_LABELS = [-np.inf, 1000, 5000, np.inf], ["LOW", "MID", "HIGH"]
DATA_SEGS = ["HEAVY", "LITE", "NON_USER"]


def _phi(z):
    return np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _eff_mult(m):
    # ponytail: conversion is capped at 1, so a >1 multiplier is only partly realised;
    # we cannot observe the conversion rate, so haircut 25% of the excess over 1.
    return m if m <= 1 else 1 + (m - 1) * 0.75


def _segment(profile, c):
    r = profile
    for col, key in [("arpu_segment", "filter_arpu_segment"), ("data_segment", "filter_data_segment"),
                     ("call_segment", "filter_call_segment")]:
        if c.get(key) is not None:
            r = r[r[col] == c[key]]
    if c.get("filter_current_tariff") is not None:
        r = r[r["current_tariff"].isin(c["filter_current_tariff"].split(";"))]
    return r


class Agent:
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.records = []   # our own pilot log incl. filters (env.pilot_history lacks them)
        self.calibration = None
        self.plan_detail = []

    def log(self, *a):
        if self.verbose:
            print("[agent]", *a)

    # ------------------------------------------------------------------ act
    def act(self, env):
        profile = env.customer_profile
        self.cost = {c: float(v["cost_per_contact"]) for c, v in env.channels.items()}
        cells = self._cells(profile)
        hyps = self._hypotheses(cells, self._prior(env), set(env.tariffs["tariff_plan_code"]))
        self._run_pilots(env, hyps)
        self._calibrate(hyps)
        self.hyps = hyps
        return self._plan(env, profile, hyps)

    # ---------------------------------------------------------------- cells
    @staticmethod
    def _cells(profile):
        df = profile.dropna(subset=["current_tariff", "arpu_segment", "predicted_arpu"])
        cells = (df.groupby(["current_tariff", "arpu_segment"], observed=True)
                   .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index())
        cells = cells.rename(columns={"current_tariff": "tariff", "arpu_segment": "seg"})
        cells["avg"] = cells["mass"] / cells["n"]
        return cells[cells["n"] >= MIN_CELL].reset_index(drop=True)

    # ---------------------------------------------------------------- prior
    def _prior(self, env):
        """Shrunk history means/conversion shares keyed by (from, seg, to), with parent fallbacks."""
        ct = pd.read_csv(os.path.join(HERE, "data", "change_tariff.csv"))
        ct = ct[ct["AVG_ARPU_PREV_3M"] >= 100].copy()   # tiny prior ARPU -> unstable ratios
        ct["seg"] = pd.cut(ct["AVG_ARPU_PREV_3M"], ARPU_BINS, labels=ARPU_LABELS).astype(str)
        ct["pct"] = ((ct["AVG_ARPU_NEXT_3M"] - ct["AVG_ARPU_PREV_3M"]) / ct["AVG_ARPU_PREV_3M"]).clip(-1, 3)
        f, t = "tariff_plan_code_from", "tariff_plan_code_to"
        K = SHRINK_K
        g0 = ct["pct"].mean()
        g1 = ct.groupby(t)["pct"].agg(["sum", "size"])
        m1 = (g1["sum"] + K * g0) / (g1["size"] + K)
        g2 = ct.groupby([f, t])["pct"].agg(["sum", "size"])
        m2 = (g2["sum"] + K * m1.reindex(g2.index.get_level_values(1)).values) / (g2["size"] + K)
        g3 = ct.groupby([f, "seg", t])["pct"].agg(["sum", "size"])
        parent = m2.reindex(list(zip(g3.index.get_level_values(0), g3.index.get_level_values(2)))).values
        m3 = (g3["sum"] + K * parent) / (g3["size"] + K)
        n_from_seg = ct.groupby([f, "seg"]).size()
        n_targets = len(env.tariffs)
        tot = n_from_seg.reindex(list(zip(g3.index.get_level_values(0), g3.index.get_level_values(1)))).values
        conv = (g3["size"] + 0.5) / (tot + 0.5 * n_targets)
        return dict(g0=g0, m1=m1, m2=m2, m3=m3, n3=g3["size"], conv=conv, n_from_seg=n_from_seg,
                    n_targets=n_targets, conv_median=float(conv.median()))

    def _hypotheses(self, cells, P, valid_targets):
        rows = []
        for _, c in cells.iterrows():
            for tgt in sorted(valid_targets):
                if tgt == c["tariff"]:
                    continue
                key = (c["tariff"], c["seg"], tgt)
                if key in P["m3"].index:
                    pct, cv = P["m3"][key], P["conv"][key]
                    sd = PRIOR_SD if P["n3"][key] >= 5 else PRIOR_SD_FALLBACK
                else:   # transition unseen in history: parent mean, near-zero conversion share
                    pct = P["m2"].get((c["tariff"], tgt), P["m1"].get(tgt, P["g0"]))
                    N = P["n_from_seg"].get((c["tariff"], c["seg"]), 0)
                    cv = 0.5 / (N + 0.5 * P["n_targets"]) if N > 0 else P["conv_median"]
                    sd = PRIOR_SD_FALLBACK
                rows.append(dict(tariff=c["tariff"], seg=c["seg"], target=tgt, n=int(c["n"]),
                                 mass=float(c["mass"]), avg=float(c["avg"]), mu0=float(pct * cv), sd0=sd))
        h = pd.DataFrame(rows)
        h = (h.sort_values(["tariff", "seg", "mu0", "target"], ascending=[True, True, False, True])
              .groupby(["tariff", "seg"]).head(TARGETS_PER_CELL).reset_index(drop=True))
        h["mu"], h["sd"] = h["mu0"], h["sd0"]
        h["n_obs"], h["ysum"] = 0, 0.0      # pilot-only evidence, used for calibration
        return h

    # --------------------------------------------------------------- pilots
    def _run_pilots(self, env, h):
        m_ref = float(env.channels[PILOT_CHANNEL]["conversion_multiplier"])
        cost_p = self.cost[PILOT_CHANNEL]
        money_cap = PILOT_MONEY_SHARE * env.total_budget
        reach_cap = PILOT_REACH_SHARE * env.max_total_contacts
        spent = reached = 0
        mass_share = (h["mass"] / h.drop_duplicates(["tariff", "seg"])["mass"].sum()).values
        while env.pilots_left > 0:
            # decision threshold per hypothesis: best posterior mean among the cell's other targets (>=0)
            grp = h.groupby(["tariff", "seg"])["mu"]
            top = grp.transform("max").values
            second = grp.transform(lambda s: s.nlargest(2).iloc[-1] if len(s) > 1 else 0.0).values
            tau = np.clip(np.where(h["mu"].values >= top, second, top), 0.0, None)
            gap = h["mu"].values - tau
            z = gap / h["sd"].values
            n = (Z_PILOT * NOISE_SD / (m_ref * np.maximum(np.abs(gap), 0.05))) ** 2
            n = n * np.clip(np.sqrt(mass_share / 0.05), 0.6, 1.5)
            n = np.minimum(np.clip(np.round(n), PILOT_N_MIN, PILOT_N_MAX), h["n"].values)
            voi = h["mass"].values * m_ref * h["sd"].values * _phi(z)
            risk = n * m_ref * np.maximum(-h["mu"].values, 0) * h["avg"].values
            prio = voi - n * cost_p - risk
            i = int(np.lexsort((h["target"].values, h["seg"].values, h["tariff"].values, -prio))[0])
            if prio[i] <= 0:
                self.log("stop pilots: no hypothesis worth another pilot")
                break
            ni = int(n[i])
            if cost_p > 0:
                ni = min(ni, int((money_cap - spent) // cost_p), int(env.remaining_budget // cost_p))
            ni = min(ni, int(reach_cap - reached), int(env.remaining_contacts))
            if ni < 10:
                self.log("stop pilots: pilot budget guard reached")
                break
            row = h.loc[i]
            try:
                res = env.run_pilot(target_tariff=row["target"], channel=PILOT_CHANNEL, n_customers=ni,
                                    filter_arpu_segment=row["seg"], filter_current_tariff=row["tariff"])
            except (RuntimeError, ValueError) as e:
                self.log("pilot failed:", e)
                h.loc[i, "sd"] = 1e-6      # ponytail: mark unpilotable so the loop moves on
                h.loc[i, "mu"] = min(h.loc[i, "mu"], 0.0)
                continue
            n_act = int(res["n_customers"])
            y = float(res["observed_lift_ratio"]) / m_ref            # to base units
            v = (NOISE_SD / m_ref) ** 2 / n_act
            prec = 1 / h.loc[i, "sd"] ** 2 + 1 / v
            h.loc[i, "mu"] = (h.loc[i, "mu"] / h.loc[i, "sd"] ** 2 + y / v) / prec
            h.loc[i, "sd"] = math.sqrt(1 / prec)
            h.loc[i, "n_obs"] += n_act
            h.loc[i, "ysum"] += y * n_act
            spent += res["cost"]
            reached += n_act
            self.records.append(dict(tariff=row["tariff"], seg=row["seg"], target=row["target"],
                                     channel=PILOT_CHANNEL, n=n_act, cost=res["cost"],
                                     observed=res["observed_lift_ratio"], prior_mu=row["mu0"],
                                     post_mu=h.loc[i, "mu"], post_sd=h.loc[i, "sd"],
                                     budget_after=res["remaining_budget"], contacts_after=res["remaining_contacts"]))
            self.log(f"pilot {len(self.records):2d} {row['tariff']:>9}/{row['seg']:<4} -> {row['target']:<9} "
                     f"n={n_act:3d} obs={res['observed_lift_ratio']:+.3f} prior={row['mu0']:+.3f} "
                     f"post={h.loc[i, 'mu']:+.3f}±{h.loc[i, 'sd']:.3f}")
        self.log(f"pilots done: {len(self.records)} pilots, {reached} contacts, {spent:,.0f} money")

    def _calibrate(self, h):
        """Shift the prior of untested hypotheses by the mean (observed - prior) residual of tested ones."""
        tested = h["n_obs"] > 0
        if tested.sum() < 3:
            return
        resid = h.loc[tested, "ysum"] / h.loc[tested, "n_obs"] - h.loc[tested, "mu0"]
        bias = float(resid.mean()) * tested.sum() / (tested.sum() + 3)
        sd = max(PRIOR_SD, float(resid.std()))
        h.loc[~tested, "mu"] = h.loc[~tested, "mu0"] + bias
        h.loc[~tested, "sd"] = np.maximum(h.loc[~tested, "sd0"], sd)
        self.calibration = dict(bias=bias, sd=sd, n_tested=int(tested.sum()))
        self.log(f"calibration: prior bias {bias:+.3f}, residual sd {sd:.3f} applied to untested hypotheses")

    # ----------------------------------------------------------------- plan
    def _plan(self, env, profile, h):
        names = list(env.channels)
        cost = np.array([self.cost[c] for c in names])
        mult = np.array([_eff_mult(float(env.channels[c]["conversion_multiplier"])) for c in names])
        B, R = float(env.remaining_budget), int(env.remaining_contacts)

        h["r_adj"] = h["mu"] - KAPPA * h["sd"]
        best = (h.sort_values(["r_adj", "target"], ascending=[False, True])
                 .groupby(["tariff", "seg"]).head(1))
        best = best[best["r_adj"] > 0].sort_values(["tariff", "seg"]).reset_index(drop=True)
        if best.empty:   # nothing is confidently positive: one free (push) campaign on the best mean
            top = h.sort_values(["mu", "tariff", "seg", "target"], ascending=[False, True, True, True]).iloc[0]
            self.log("no confidently positive cell; falling back to one push campaign")
            return self._build([dict(tariff=top["tariff"], seg=top["seg"], data=None, target=top["target"],
                                     channel="push", n=int(top["n"]), value=0.0)], profile, B, R)

        r, mass, n = best["r_adj"].values, best["mass"].values, best["n"].values.astype(float)
        gross = r[:, None] * mult[None, :] * mass[:, None]

        def alloc(lam, rho):
            val = gross - n[:, None] * (cost[None, :] * (1 + lam) + rho)
            c = val.argmax(1)
            keep = val[np.arange(len(r)), c] > 0
            return keep, c, float((n[keep] * cost[c[keep]]).sum()), float(n[keep].sum())

        def solve_lam(rho):
            lo, hi = 0.0, 1.0
            while alloc(hi, rho)[2] > B and hi < 1e6:
                hi *= 2
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if alloc(mid, rho)[2] > B else (lo, mid)
            return hi

        lo, hi = 0.0, 1.0
        while alloc(solve_lam(hi), hi)[3] > R and hi < 1e9:
            hi *= 2
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if alloc(solve_lam(mid), mid)[3] > R else (lo, mid)
        rho = hi
        lam = solve_lam(rho)
        keep, c, _, _ = alloc(lam, rho)
        units = [dict(tariff=best.loc[i, "tariff"], seg=best.loc[i, "seg"], data=None,
                      target=best.loc[i, "target"], channel=names[c[i]], n=int(n[i]),
                      value=float(gross[i, c[i]] - n[i] * cost[c[i]]))
                 for i in np.where(keep)[0]]
        # safety against the non-monotone corner of the 2-D bisection
        units.sort(key=lambda u: -u["value"] / u["n"])
        while units and (sum(u["n"] for u in units) > R or
                         sum(u["n"] * self.cost[u["channel"]] for u in units) > B):
            units.pop()
        self.log(f"allocation: money price {lam:.3f}, reach price {rho:,.0f}; {len(units)} cells kept")

        # fill leftover reach/money with data-segment slices of the best excluded cells
        R_left = R - sum(u["n"] for u in units)
        B_left = B - sum(u["n"] * self.cost[u["channel"]] for u in units)
        excluded = sorted([i for i in range(len(best)) if not keep[i]],
                          key=lambda i: -(gross[i] - n[i] * cost).max() / n[i])
        sub = (profile.dropna(subset=["current_tariff", "arpu_segment", "data_segment"])
                      .groupby(["current_tariff", "arpu_segment", "data_segment"], observed=True)
                      .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")))
        for i in excluded:
            if R_left < 10:
                break
            for d in DATA_SEGS:
                key = (best.loc[i, "tariff"], best.loc[i, "seg"], d)
                if key not in sub.index:
                    continue
                nd, md = int(sub.loc[key, "n"]), float(sub.loc[key, "mass"])
                if nd > R_left or nd > MAX_PER_CAMPAIGN:
                    continue
                vals = r[i] * mult * md - nd * cost
                vals[nd * cost > B_left] = -np.inf
                j = int(vals.argmax())
                if vals[j] <= 0:
                    continue
                units.append(dict(tariff=key[0], seg=key[1], data=d, target=best.loc[i, "target"],
                                  channel=names[j], n=nd, value=float(vals[j])))
                R_left -= nd
                B_left -= nd * cost[j]
        return self._build(units, profile, B, R)

    def _build(self, units, profile, B, R):
        """Units -> <=10 disjoint campaigns of <=5000; split oversize cells by data segment."""
        sub = (profile.dropna(subset=["current_tariff", "arpu_segment", "data_segment"])
                      .groupby(["current_tariff", "arpu_segment", "data_segment"], observed=True).size())
        split = []
        for u in units:
            if u["data"] is None and u["n"] > MAX_PER_CAMPAIGN:
                for d in DATA_SEGS:
                    nd = int(sub.get((u["tariff"], u["seg"], d), 0))
                    if nd:
                        split.append({**u, "data": d, "n": nd, "value": u["value"] * nd / u["n"]})
            else:
                split.append(u)
        groups = {}
        for u in split:
            groups.setdefault((u["target"], u["channel"], u["seg"], u["data"]), []).append(u)
        campaigns = []
        for (target, channel, seg, data), us in sorted(groups.items(), key=lambda kv: str(kv[0])):
            bins = []   # first-fit decreasing by tariff into <=5000 bins
            for u in sorted(us, key=lambda u: (-u["n"], u["tariff"])):
                for b in bins:
                    if b["n"] + u["n"] <= MAX_PER_CAMPAIGN:
                        b["n"] += u["n"]; b["value"] += u["value"]; b["tariffs"].append(u["tariff"])
                        break
                else:
                    bins.append(dict(n=u["n"], value=u["value"], tariffs=[u["tariff"]]))
            for b in bins:
                tariffs = ";".join(sorted(b["tariffs"]))
                campaigns.append(dict(campaign_name=f"{target}<-{tariffs}|{seg}|{data or 'ALL'}|{channel}",
                                      filter_arpu_segment=seg, filter_data_segment=data,
                                      filter_call_segment=None, filter_current_tariff=tariffs,
                                      target_tariff=target, channel=channel, _n=b["n"], _value=b["value"]))
        campaigns.sort(key=lambda c: -c["_value"] / max(c["_n"], 1))
        campaigns = campaigns[:MAX_CAMPAIGNS]
        # verify against the real profile filters and the real remaining limits
        sizes, costs = [], []
        while campaigns:
            sizes = [min(len(_segment(profile, c)), MAX_PER_CAMPAIGN) for c in campaigns]
            costs = [s * self.cost[c["channel"]] for s, c in zip(sizes, campaigns)]
            if all(s > 0 for s in sizes) and sum(sizes) <= R and sum(costs) <= B:
                break
            campaigns.pop()
        for c, s in zip(campaigns, sizes):
            self.log(f"campaign {c['campaign_name']:<52} n={s:5d} value~{c['_value']:>12,.0f}")
        self.log(f"plan: {len(campaigns)} campaigns, {sum(sizes)} contacts, {sum(costs):,.0f} money "
                 f"(limits {R} / {B:,.0f})")
        plan = [{k: v for k, v in c.items() if not k.startswith("_")} for c in campaigns]
        self.plan_detail = [dict(c, n=s, cost=k, value=raw["_value"])
                            for c, raw, s, k in zip(plan, campaigns, sizes, costs)]
        return plan
