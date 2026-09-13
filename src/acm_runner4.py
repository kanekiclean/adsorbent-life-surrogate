# -*- coding: utf-8 -*-
"""
Прогоны Aspen Adsorption с четырьмя параметрами.

Четвёртый параметр (остаточная загрузка) задаётся выбором файла-шаблона:
инициализация слоя недоступна через COM, поэтому шаблоны с разной
загрузкой готовятся один раз вручную (Reset -> Spec=Initial -> W -> Initialize -> Save As).

Установка адсорбционной осушки. Яковлев Н.Г., сентябрь 2026
Запуск:  py acm_runner4.py
"""

import os
import csv
import time
import math
import subprocess
import win32com.client as win32

FOLDER = r"C:\models"
OUT_CSV = os.path.join(FOLDER, "runs4.csv")

# Шаблоны: остаточная загрузка -> файл
TEMPLATES = [
    (0.0,      "Adsorption_TEMPLATE.ada"),
    (5.07e-5,  "TEMPLATE_W03.ada"),
    (1.014e-4, "TEMPLATE_W06.ada"),
    (1.69e-4,  "TEMPLATE_W10.ada"),
    (2.535e-4, "TEMPLATE_W15.ada"),
]

BREAKTHROUGH = 10e-6
STEP_S = 600.0
MAX_TIME_S = 130000.0
COMM_S = 60.0

IP1_REF, IP2_REF = 8.59, 2500.0
IP1W_REF, IP2W_REF = 120.0, 4000.0
T_REF = 298.15
Q_ME, Q_WA, R = 50000.0, 75380.0, 8.314
F_KMOL_S = 6.2


def vant_hoff(T, Q):
    return (T / T_REF) * math.exp((Q / R) * (1.0 / T - 1.0 / T_REF))


def kill_acm():
    subprocess.run("taskkill /F /IM AspenModeler.exe /T",
                   shell=True, capture_output=True)
    time.sleep(1)


def open_model(path):
    app = win32.Dispatch("ACM Application")
    app._oleobj_.Invoke(app._oleobj_.GetIDsOfNames("OpenDocument"), 0, 1, 1, path)
    return app


def set_params(sim, T, cap, y_me):
    fs = sim.Flowsheet
    B1 = fs.Blocks.Item(1)
    L = fs.Blocks.Item(2).Layer(1)

    fm, fw = vant_hoff(T, Q_ME), vant_hoff(T, Q_WA)
    L.IP(1, "METHANOL").Value = IP1_REF * fm * cap
    L.IP(2, "METHANOL").Value = IP2_REF * fm
    L.IP(1, "WATER").Value = IP1W_REF * fw * cap
    L.IP(2, "WATER").Value = IP2W_REF * fw

    B1.T_Fwd.Value = T
    B1.F.Value = F_KMOL_S
    B1.Y_Fwd("METHANOL").Value = y_me
    B1.Y_Fwd("WATER").Value = 2.6e-5
    B1.Y_Fwd("NITROGEN").Value = 0.069
    B1.Y_Fwd("METHANE").Value = 1.0 - y_me - 2.6e-5 - 0.069

    return IP1_REF * fm * cap, IP2_REF * fm


def run_to_breakthrough(sim):
    """Возвращает (t_проскока_ч, выход_на_старте_ppm)."""
    s8 = sim.Flowsheet.Streams.Item(2)
    sim.CommunicationInterval = COMM_S

    y_start = None
    t_prev, y_prev = 0.0, 0.0
    t = 0.0

    while t < MAX_TIME_S:
        t += STEP_S
        sim.EndTime = t
        sim.Run(True)
        if not sim.Successful:
            return None, y_start

        y = s8.Y("METHANOL").Value
        if y_start is None:
            y_start = y * 1e6          # ppm на первом шаге

        if y >= BREAKTHROUGH:
            if y > y_prev:
                frac = (BREAKTHROUGH - y_prev) / (y - y_prev)
            else:
                frac = 0.0
            return (t_prev + frac * (t - t_prev)) / 3600.0, y_start

        t_prev, y_prev = t, y

    return None, y_start


def build_grid():
    temps = [298.15, 313.15, 318.15, 328.15, 338.15]     # 25/45/55/65
    caps = [1.0, 0.7]
    y_me = [88e-6, 226e-6]
    return [(T, c, y) for T in temps for c in caps for y in y_me]


def main():
    grid = build_grid()
    total = len(grid) * len(TEMPLATES)
    print("Шаблонов:", len(TEMPLATES), " точек на шаблон:", len(grid),
          " всего:", total)

    # проверка наличия файлов
    for _, fn in TEMPLATES:
        p = os.path.join(FOLDER, fn)
        if not os.path.exists(p):
            print("НЕТ ФАЙЛА:", p)
            return

    new = not os.path.exists(OUT_CSV)
    f = open(OUT_CSV, "a", newline="", encoding="utf-8")
    wr = csv.writer(f, delimiter=";")
    if new:
        wr.writerow(["w_residual", "T_K", "T_C", "capacity_frac",
                     "y_methanol_ppm", "IP1", "IP2",
                     "y_start_ppm", "t_breakthrough_h"])

    n = 0
    for w_res, fname in TEMPLATES:
        path = os.path.join(FOLDER, fname)
        for (T, cap, y) in grid:
            n += 1
            print(f"\n[{n}/{total}] W={w_res:.3e}  T={T-273.15:.0f}C  "
                  f"ёмкость={cap:.2f}  метанол={y*1e6:.0f}ppm")

            kill_acm()
            try:
                app = open_model(path)
                sim = app.Simulation
                ip1, ip2 = set_params(sim, T, cap, y)
                t_bt, y0 = run_to_breakthrough(sim)
            except Exception as e:
                print("    ОШИБКА:", type(e).__name__, e)
                t_bt, y0, ip1, ip2 = None, None, 0, 0

            if y0 is not None:
                print(f"    старт: {y0:.2f} ppm", end="")
            if t_bt is not None:
                print(f"    проскок: {t_bt:.3f} ч")
            else:
                print("    проскок не достигнут")

            wr.writerow([f"{w_res:.4e}", f"{T:.2f}", f"{T-273.15:.0f}",
                         f"{cap:.3f}", f"{y*1e6:.0f}",
                         f"{ip1:.4f}", f"{ip2:.2f}",
                         f"{y0:.3f}" if y0 is not None else "",
                         f"{t_bt:.4f}" if t_bt is not None else ""])
            f.flush()

    f.close()
    kill_acm()
    print("\nГотово:", OUT_CSV)


if __name__ == "__main__":
    main()
