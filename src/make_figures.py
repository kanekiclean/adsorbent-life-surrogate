# -*- coding: utf-8 -*-
"""
Построение графиков по готовым выборкам расчётов.
Aspen не требуется.

Вход:  ../data/runs.csv, ../data/runs4.csv (разделитель ';')
Выход: ../figures/*.png
"""

import csv
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
FIGS = os.path.join(HERE, "..", "figures")

CYCLE_H = 12.0
LIMIT_PPM = 10.0
DPI = 200


def load(name):
    """Читает CSV с разделителем ';' в словарь колонок."""
    path = os.path.join(DATA, name)
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    if not rows:
        raise SystemExit("пустой файл: " + path)
    cols = {}
    for key in rows[0]:
        if key is None:
            continue
        vals = []
        for r in rows:
            raw = (r.get(key) or "").strip().replace(",", ".")
            try:
                vals.append(float(raw))
            except ValueError:
                vals.append(np.nan)
        cols[key.strip()] = np.array(vals)
    return cols


def fig_time_vs_temperature(d):
    """Время проскока от температуры слоя, кривые по остаточной ёмкости."""
    t_c = d["T_C"]
    cap = d["capacity_frac"]
    t_br = d["t_breakthrough_h"]
    y = d["y_methanol_ppm"]

    # фиксируем концентрацию на самом населённом уровне
    levels, counts = np.unique(np.round(y, 1), return_counts=True)
    y_fix = levels[np.argmax(counts)]
    m = np.isclose(np.round(y, 1), y_fix)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    caps = np.unique(np.round(cap[m], 3))
    colors = plt.cm.viridis(np.linspace(0, 0.85, len(caps)))

    for c, color in zip(caps, colors):
        sel = m & np.isclose(np.round(cap, 3), c)
        if sel.sum() < 2:
            continue
        order = np.argsort(t_c[sel])
        ax.plot(t_c[sel][order], t_br[sel][order], "o-",
                color=color, lw=1.8, ms=4,
                label="capacity {:.2f}".format(c))

    ax.axhline(CYCLE_H, color="crimson", ls="--", lw=1.4)
    ax.text(ax.get_xlim()[1], CYCLE_H, " {:g} h cycle".format(CYCLE_H),
            color="crimson", va="bottom", ha="right", fontsize=9)

    ax.set_xlabel("Bed temperature, °C")
    ax.set_ylabel("Breakthrough time, h")
    ax.set_title("Breakthrough time vs bed temperature\n"
                 "(feed {:g} ppm)".format(y_fix), fontsize=11)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    out = os.path.join(FIGS, "time_vs_temperature.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out


def fig_operating_map(d4):
    """Карта режимов: выход в начале цикла по остатку и температуре."""
    w = d4["w_residual"]
    t_c = d4["T_C"]
    ys = d4["y_start_ppm"]

    ws = np.unique(np.round(w, 4))
    ts = np.unique(np.round(t_c, 1))
    grid = np.full((len(ws), len(ts)), np.nan)

    for i, wv in enumerate(ws):
        for j, tv in enumerate(ts):
            sel = np.isclose(np.round(w, 4), wv) & np.isclose(np.round(t_c, 1), tv)
            if sel.any():
                grid[i, j] = np.nanmean(ys[sel])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    im = ax.imshow(grid, origin="lower", aspect="auto", cmap="RdYlGn_r",
                   extent=[ts[0], ts[-1], ws[0] * 100, ws[-1] * 100])

    for i, wv in enumerate(ws):
        for j, tv in enumerate(ts):
            if np.isnan(grid[i, j]):
                continue
            ax.text(tv, wv * 100, "{:.1f}".format(grid[i, j]),
                    ha="center", va="center", fontsize=8,
                    color="black" if grid[i, j] < 40 else "white")

    cb = fig.colorbar(im, ax=ax)
    cb.set_label("Outlet at cycle start, ppm")

    ax.set_xlabel("Bed temperature, °C")
    ax.set_ylabel("Residual loading, % of equilibrium")
    ax.set_title("Operating map (limit {:g} ppm)".format(LIMIT_PPM), fontsize=11)
    fig.tight_layout()
    out = os.path.join(FIGS, "operating_map.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out


def fig_concentration(d):
    """Время проскока от концентрации примеси в сырье."""
    y = d["y_methanol_ppm"]
    t_br = d["t_breakthrough_h"]
    t_c = d["T_C"]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    sc = ax.scatter(y, t_br, c=t_c, cmap="coolwarm", s=28,
                    edgecolor="none", alpha=0.85)
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label("Bed temperature, °C")

    ax.axhline(CYCLE_H, color="crimson", ls="--", lw=1.4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Feed methanol, ppm")
    ax.set_ylabel("Breakthrough time, h")
    ax.set_title("Breakthrough time vs feed concentration", fontsize=11)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    out = os.path.join(FIGS, "time_vs_concentration.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out


def main():
    os.makedirs(FIGS, exist_ok=True)

    d = load("runs.csv")
    d4 = load("runs4.csv")

    # артефактные строки: слой вне нормы с первого шага
    if "t_breakthrough_h" in d4:
        keep = d4["t_breakthrough_h"] > 0.5
        d4 = {k: v[keep] for k, v in d4.items()}

    print("runs.csv  колонки:", ", ".join(sorted(d)))
    print("runs4.csv колонки:", ", ".join(sorted(d4)))
    print()

    for fn, arg in ((fig_time_vs_temperature, d),
                    (fig_operating_map, d4),
                    (fig_concentration, d)):
        try:
            print("готово:", os.path.basename(fn(arg)))
        except Exception as exc:
            print("ошибка в", fn.__name__, "->", exc)


if __name__ == "__main__":
    main()
