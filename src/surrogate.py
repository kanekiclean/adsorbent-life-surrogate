# -*- coding: utf-8 -*-
"""
Суррогатная модель времени проскока и выхода примеси в начале цикла
для слоя циклической адсорбции.

Обучается на выборке строгих расчётов, сгенерированной в Aspen Adsorption.
Сравниваются три формы: физическая параметрическая, лог-линейная,
градиентный бустинг. Валидация — отложенная выборка 30 %.

Вход:  runs.csv, runs4.csv (разделитель ';')
Выход: метрики в консоль, коэффициенты модели, файл surrogate_params.json

Запуск:  py surrogate.py
"""

import csv
import json
import math
import numpy as np
from scipy.optimize import curve_fit
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------- константы

R = 8.314                 # Дж/(моль·К)
T0 = 298.15               # K, опорная температура
IP1_0, IP2_0 = 8.59, 2500.0     # параметры изотермы при T0
P_BAR = 72.0
AREA = 13.854             # м², сечение слоя
F_KMOL_S = 6.2            # кмоль/с


def vant_hoff(Tk, Q):
    """Множитель пересчёта константы Ленгмюра с T0 на Tk.

    b_C = b_P · z · R · T, поэтому перед экспонентой возникает T/T0:
    концентрационная форма изотермы против давлениевой формы Вант-Гоффа.
    """
    return (Tk / T0) * np.exp((Q / R) * (1.0 / Tk - 1.0 / T0))


def molar_density(Tk):
    """Мольная плотность газа, кмоль/м³ (идеальный газ)."""
    return P_BAR * 1e5 / (R * Tk) / 1000.0


# ---------------------------------------------------------------- модели

def model_time(par, Tk, cap, y_ppm):
    """Время проскока, ч.

    t = k · q*(T, cap, y) · M / (F · y),
    где q* — равновесная ёмкость по изотерме Ленгмюра при данных условиях.
    Деградация уменьшает число центров, поэтому бьёт только по IP1.
    """
    Q, k, alpha = par
    f = vant_hoff(Tk, Q)
    Cg = molar_density(Tk) * y_ppm * 1e-6
    W = (IP1_0 * f * cap ** alpha) * Cg / (1.0 + IP2_0 * f * Cg)
    return k * W / (y_ppm * 1e-6)


def model_start(par, Tk, cap, W_res):
    """Выход примеси в начале цикла, ppm.

    Обращение изотермы Ленгмюра относительно концентрации газа
    при заданной остаточной загрузке слоя W_res:
        C = W / (IP1 − IP2 · W)
    """
    Q, k = par
    f = vant_hoff(Tk, Q)
    Cg = W_res / (IP1_0 * f * cap - IP2_0 * f * W_res)
    return k * Cg / molar_density(Tk) * 1e6


def loglinear(X, y):
    """Полностью факторизованная форма: log t = a0 + a1·log(cap) + a2/T + a3·log(y)."""
    b, *_ = np.linalg.lstsq(X, np.log(y), rcond=None)
    return b


# ---------------------------------------------------------------- метрики

def metrics(pred, obs):
    mape = 100.0 * np.mean(np.abs(pred - obs) / obs)
    mx = 100.0 * np.max(np.abs(pred - obs) / obs)
    r2 = 1.0 - ((obs - pred) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()
    return mape, mx, r2


def report(name, pred, obs):
    mape, mx, r2 = metrics(pred, obs)
    print(f"  {name:34s} MAPE={mape:6.3f} %   max={mx:6.2f} %   R2={r2:.6f}")
    return mape, mx, r2


# ---------------------------------------------------------------- данные

def load(path, cols):
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            try:
                out.append([float(row[c].replace(",", ".")) for c in cols])
            except (ValueError, KeyError):
                continue
    return np.array(out)


# ---------------------------------------------------------------- главное

def fit_time_model():
    """Суррогат времени проскока: три параметра (T, cap, y)."""
    d = load("../data/runs.csv", ["T_K", "capacity_frac", "y_methanol_ppm",
                          "t_breakthrough_h"])
    Tk, cap, y, t = d[:, 0], d[:, 1], d[:, 2], d[:, 3]
    ok = t > 0.5                      # отбрасываем точки, изначально вне нормы
    Tk, cap, y, t = Tk[ok], cap[ok], y[ok], t[ok]
    print(f"\nМОДЕЛЬ ВРЕМЕНИ ПРОСКОКА   точек: {len(t)}")

    idx = np.arange(len(t))
    itr, ite = train_test_split(idx, test_size=0.3, random_state=42)

    fn = lambda _x, Q, k, a: model_time((Q, k, a), Tk[itr], cap[itr], y[itr])
    p, _ = curve_fit(fn, np.zeros(len(itr)), t[itr], p0=[50000, 0.02, 1.0],
                     bounds=([20000, 1e-4, 0.5], [90000, 10, 1.5]), maxfev=50000)
    report("физическая (3 коэфф.)", model_time(p, Tk[ite], cap[ite], y[ite]), t[ite])
    print(f"    Q = {p[0]:.0f} Дж/моль   k = {p[1]:.4f}   "
          f"показатель при ёмкости = {p[2]:.4f}")

    X = np.column_stack([np.ones(len(t)), np.log(cap), 1.0 / Tk, np.log(y)])
    b = loglinear(X[itr], t[itr])
    report("лог-линейная (4 коэфф.)", np.exp(X[ite] @ b), t[ite])

    Xm = np.column_stack([Tk, cap, y])
    g = GradientBoostingRegressor(n_estimators=800, max_depth=3,
                                  learning_rate=0.05, random_state=0)
    g.fit(Xm[itr], np.log(t[itr]))
    report("градиентный бустинг", np.exp(g.predict(Xm[ite])), t[ite])
    return p


def fit_start_model():
    """Суррогат выхода в начале цикла: четвёртый параметр — остаточная загрузка."""
    d = load("../data/runs4.csv", ["T_K", "capacity_frac", "w_residual", "y_start_ppm"])
    Tk, cap, W, ys = d[:, 0], d[:, 1], d[:, 2], d[:, 3]
    ok = W > 0
    Tk, cap, W, ys = Tk[ok], cap[ok], W[ok], ys[ok]
    print(f"\nМОДЕЛЬ ВЫХОДА В НАЧАЛЕ ЦИКЛА   точек: {len(ys)}")

    idx = np.arange(len(ys))
    itr, ite = train_test_split(idx, test_size=0.3, random_state=1)

    fn = lambda _x, Q, k: model_start((Q, k), Tk[itr], cap[itr], W[itr])
    p, _ = curve_fit(fn, np.zeros(len(itr)), ys[itr], p0=[50000, 1.0],
                     bounds=([20000, 0.1], [90000, 10]), maxfev=50000)
    report("физическая (2 коэфф.)", model_start(p, Tk[ite], cap[ite], W[ite]), ys[ite])
    print(f"    Q = {p[0]:.0f} Дж/моль   k = {p[1]:.4f}")

    X = np.column_stack([np.ones(len(ys)), np.log(W), np.log(cap), 1.0 / Tk])
    b = loglinear(X[itr], ys[itr])
    report("лог-линейная (4 коэфф.)", np.exp(X[ite] @ b), ys[ite])

    Xm = np.column_stack([Tk, cap, W])
    g = GradientBoostingRegressor(n_estimators=600, max_depth=3,
                                  learning_rate=0.05, random_state=0)
    g.fit(Xm[itr], np.log(ys[itr]))
    report("градиентный бустинг", np.exp(g.predict(Xm[ite])), ys[ite])
    return p


def predict_table(p_start):
    """Карта режимов: выход в начале цикла при разной загрузке и температуре."""
    print("\nКАРТА РЕЖИМОВ — выход в начале цикла, ppm (норма 10 ppm)")
    temps = [25, 40, 45, 55, 65]
    print("  остаток " + "".join(f"{T:>8d} °C" for T in temps))
    for frac, W in [(3, 5.07e-5), (6, 1.014e-4), (10, 1.69e-4), (15, 2.535e-4)]:
        vals = [model_start(p_start, np.array([T + 273.15]),
                            np.array([1.0]), np.array([W]))[0] for T in temps]
        print(f"  {frac:5d} % " + "".join(f"{v:>11.1f}" for v in vals))


if __name__ == "__main__":
    pt = fit_time_model()
    ps = fit_start_model()
    predict_table(ps)
    json.dump({"time_model": {"Q": pt[0], "k": pt[1], "alpha": pt[2]},
               "start_model": {"Q": ps[0], "k": ps[1]}},
              open("surrogate_params.json", "w"), indent=2)
    print("\nКоэффициенты сохранены: surrogate_params.json")
