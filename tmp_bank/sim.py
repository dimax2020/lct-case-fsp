# -*- coding: utf-8 -*-
"""Симуляционная валидация CAT (IRT 2PL) на параметрах банка.
Запуск: python sim.py [bank.json]  → sim_results.json
Сценарии на каждую специализацию:
  start    — стартовый банк (детальные + теоретические шаблоны), выбор top-3 без ограничения экспозиции;
  expanded — расширенный банк + ограничение экспозиции 0.25 (скользящая доля), выбор top-5,
             остановка SE < 0.30 (макс. 20), блок продления у порога грейда (до 5 заданий)."""
import json, sys
import numpy as np

BANK = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "bank.json", encoding="utf-8"))
rng = np.random.default_rng(2026)
CUTS = [-1.2, 0.2, 1.2]
GRID = np.linspace(-4, 4, 161)
PRIOR = np.exp(-GRID ** 2 / 2)
SPECS = ["Backend", "Frontend", "QA", "DevOps"]

def grade_of(t): return int(np.searchsorted(CUTS, t, side="right"))
def p2pl(t, a, b): return 1 / (1 + np.exp(-1.7 * a * (t - b)))
def info(t, a, b):
    p = p2pl(t, a, b); return (1.7 * a) ** 2 * p * (1 - p)

def pool(spec, expanded):
    its = [t for t in BANK["templates"] if t["spec"] == spec] + \
          [t for t in BANK["theory_templates"] if t["spec"] == spec]
    if expanded:
        its += [t for t in BANK["extension_templates"] if t["spec"] == spec]
    return np.array([t["a"] for t in its]), np.array([t["b"] for t in its])

class Exposure:
    """Скользящий учёт доли тестов, в которых показан шаблон (ограничение exposure_cap)."""
    def __init__(self, n, cap, warmup=50):
        self.cnt = np.zeros(n); self.tests = 0; self.cap = cap; self.warmup = warmup
    def allowed(self):
        if self.cap >= 1 or self.tests < self.warmup: return np.ones_like(self.cnt, bool)
        return self.cnt / self.tests < self.cap
    def commit(self, used):
        self.tests += 1; self.cnt[used] += 1

def run_cat(true_t, A, Bp, start, cfg, exp, leak=None, leak_mode=None):
    post = PRIOR * np.exp(-(GRID - start) ** 2 / 2); post /= post.sum()
    used = []; th = start; se = 9.0
    allowed = exp.allowed()
    def step(target):
        nonlocal post, th, se
        mask = allowed.copy(); mask[used] = False
        if not mask.any():                       # все шаблоны исчерпали квоту — берём любой неиспользованный
            mask = np.ones(len(A), bool); mask[used] = False
        idx = np.flatnonzero(mask)
        inf = info(target, A[idx], Bp[idx])
        j = int(idx[rng.choice(np.argsort(-inf)[:cfg["topk"]])])
        used.append(j)
        p = p2pl(true_t, A[j], Bp[j])
        if leak is not None and leak[j]:
            p = 1.0 if leak_mode == "fixed" else p + 0.15 * (1 - p)
        x = rng.random() < p
        like = p2pl(GRID, A[j], Bp[j]); post *= like if x else 1 - like; post /= post.sum()
        th = float((GRID * post).sum()); se = float(np.sqrt(((GRID - th) ** 2 * post).sum()))
    for k in range(cfg["max_len"]):
        step(th)
        if k + 1 >= cfg["min_len"] and se < cfg["se"]: break
    if cfg["border"]:                            # блок продления в пограничной зоне
        for _ in range(5):
            cut = min(CUTS, key=lambda c: abs(c - th))
            if abs(th - cut) >= se: break
            step(cut)
    return th, se, used

def claimed_start(t):
    g = int(np.clip(grade_of(t) + rng.choice([-1, 0, 0, 0, 1]), 1, 3))
    return [-1.8, -0.5, 0.7, 1.8][g]

CFG = {
    "start":    dict(topk=3, cap=1.0,  se=0.35, max_len=15, min_len=8, border=False),
    "expanded": dict(topk=5, cap=0.25, se=0.30, max_len=20, min_len=8, border=True),
}

def simulate(spec, scen, n=2000):
    A, Bp = pool(spec, scen == "expanded"); cfg = CFG[scen]
    exp = Exposure(len(A), cfg["cap"])
    leak = np.zeros(len(A), bool); leak[rng.choice(len(A), len(A) // 5, replace=False)] = True
    acc = adj = ret = far_n = far_ok = 0; L = []; SE = []; ts = []; hs = []
    infl = {"base": 0, "fixed": 0, "param": 0}; bias = {"none": [], "fixed": [], "param": []}
    for _ in range(n):
        t = float(np.clip(rng.normal(0, 1.2), -3, 3)); s = claimed_start(t)
        th1, se1, used = run_cat(t, A, Bp, s, cfg, exp); exp.commit(used)
        th2, _, _ = run_cat(t, A, Bp, s, cfg, exp)
        thf, _, _ = run_cat(t, A, Bp, s, cfg, exp, leak, "fixed")
        thp, _, _ = run_cat(t, A, Bp, s, cfg, exp, leak, "param")
        gt, g1, g2 = grade_of(t), grade_of(th1), grade_of(th2)
        acc += g1 == gt; adj += abs(g1 - gt) <= 1; ret += g1 == g2
        if min(abs(t - c) for c in CUTS) > 0.3: far_n += 1; far_ok += g1 == g2
        L.append(len(used)); SE.append(se1); ts.append(t); hs.append(th1)
        infl["base"] += g2 > g1; infl["fixed"] += grade_of(thf) > g1; infl["param"] += grade_of(thp) > g1
        bias["none"].append(th1 - t); bias["fixed"].append(thf - t); bias["param"].append(thp - t)
    e = exp.cnt / exp.tests
    return dict(pool=len(A), accuracy=acc / n, within_one=adj / n, retest=ret / n, retest_far=far_ok / far_n,
                corr=float(np.corrcoef(ts, hs)[0, 1]), mean_len=float(np.mean(L)), mean_se=float(np.mean(SE)),
                max_exposure=float(e.max()), share_over_cap=float((e > 0.25 + 1e-9).mean()),
                median_exposure=float(np.median(e)), share_unused=float((e < 0.01).mean()),
                inflation_base=infl["base"] / n, inflation_fixed=infl["fixed"] / n, inflation_param=infl["param"] / n,
                bias_none=float(np.mean(bias["none"])), bias_fixed=float(np.mean(bias["fixed"])),
                bias_param=float(np.mean(bias["param"])))

if __name__ == "__main__":
    out = {}
    for spec in SPECS:
        out[spec] = {}
        for scen in CFG:
            r = simulate(spec, scen); out[spec][scen] = r
            print(spec, scen, {k: round(v, 3) for k, v in r.items()}, flush=True)
    json.dump(out, open("sim_results.json", "w"), ensure_ascii=False, indent=1)
