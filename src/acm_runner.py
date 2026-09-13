# -*- coding: utf-8 -*-
"""
Автоматические прогоны Aspen Adsorption через COM.

Установка адсорбционной осушки, модель слоя адсорбера.
Яковлев Н.Г., сентябрь 2026

Что делает:
  задаёт параметры слоя -> считает -> ловит момент проскока 10 ppm -> пишет в CSV

Запуск:  py acm_runner.py
"""

import os
import csv
import time
import subprocess
import win32com.client as win32

# ------------------------------------------------------------------ настройки

ADA = r"C:\models\Adsorption_TEMPLATE.ada"
OUT_CSV = r"C:\models\runs.csv"

BREAKTHROUGH = 10e-6        # порог проскока, мольная доля (10 ppm)
STEP_S = 600.0              # шаг опроса, с (10 мин)
MAX_TIME_S = 130000.0       # предохранитель: 36 ч, дальше прогон бросаем
COMM_S = 60.0               # communication interval

# Базовые значения при 25 C (эталон производителя)
IP1_METHANOL_REF = 8.59
IP2_METHANOL_REF = 2500.0
IP1_WATER_REF = 120.0
IP2_WATER_REF = 4000.0
T_REF = 298.15

# Теплоты адсорбции, Дж/моль
Q_METHANOL = 50000.0
Q_WATER = 75380.0
R = 8.314

# Расход на аппарат, кмоль/с (из HYSYS)
F_KMOL_S = 6.2


# ------------------------------------------------------------------ физика

def vant_hoff(T, Q):
    """Множитель пересчёта константы Ленгмюра с 25 C на T (K)."""
    return (T / T_REF) * pow(2.718281828459045, (Q / R) * (1.0 / T - 1.0 / T_REF))


def ip_at(T, capacity_frac=1.0):
    """
    Параметры изотермы при температуре T (K) и остаточной ёмкости capacity_frac.

    capacity_frac=1.0  -> свежий слой
    capacity_frac=0.5  -> потеряна половина равновесной ёмкости

    IP1 и IP2 масштабируются одним множителем f: q_s = IP1/IP2 сохраняется.
    Деградация ёмкости бьёт только по IP1 (падает число центров).
    """
    fm = vant_hoff(T, Q_METHANOL)
    fw = vant_hoff(T, Q_WATER)
    return {
        "ip1_me": IP1_METHANOL_REF * fm * capacity_frac,
        "ip2_me": IP2_METHANOL_REF * fm,
        "ip1_wa": IP1_WATER_REF * fw * capacity_frac,
        "ip2_wa": IP2_WATER_REF * fw,
    }


def vg_at(T, P_bar=72.0, area=13.854):
    """Скорость газа в первом узле, м/с. Идеальный газ."""
    molar_density = P_bar * 1e5 / (R * T) / 1000.0   # кмоль/м3
    return F_KMOL_S / molar_density / area


# ------------------------------------------------------------------ COM

def kill_acm():
    """Снимает зависшие процессы ACM. Накопившиеся экземпляры вешают COM."""
    subprocess.run("taskkill /F /IM AspenModeler.exe /T",
                   shell=True, capture_output=True)
    time.sleep(1)


def open_model(path):
    """Открывает .ada. OpenDocument вызывается напрямую через Invoke:
    late binding принимает его за свойство и падает с 'A string value was expected'."""
    app = win32.Dispatch("ACM Application")
    app._oleobj_.Invoke(
        app._oleobj_.GetIDsOfNames("OpenDocument"), 0, 1, 1, path
    )
    return app


def set_params(sim, T, capacity_frac, w_residual, y_methanol):
    """Записывает параметры прогона в блоки B1 и B2."""
    fs = sim.Flowsheet
    B1 = fs.Blocks.Item(1)
    L = fs.Blocks.Item(2).Layer(1)

    ip = ip_at(T, capacity_frac)
    L.IP(1, "METHANOL").Value = ip["ip1_me"]
    L.IP(2, "METHANOL").Value = ip["ip2_me"]
    L.IP(1, "WATER").Value = ip["ip1_wa"]
    L.IP(2, "WATER").Value = ip["ip2_wa"]

    B1.T_Fwd.Value = T
    B1.F.Value = F_KMOL_S
    B1.Y_Fwd("METHANOL").Value = y_methanol
    B1.Y_Fwd("WATER").Value = 2.6e-5
    B1.Y_Fwd("NITROGEN").Value = 0.069
    B1.Y_Fwd("METHANE").Value = 1.0 - y_methanol - 2.6e-5 - 0.069

    return ip


def run_to_breakthrough(sim):
    """
    Считает шагами по STEP_S, пока метанол на выходе не превысит порог.
    Возвращает время проскока в часах или None.
    """
    s8 = sim.Flowsheet.Streams.Item(2)
    sim.CommunicationInterval = COMM_S


    t_prev, y_prev = 0.0, 0.0
    t = 0.0

    while t < MAX_TIME_S:
        t += STEP_S
        sim.EndTime = t
        sim.Run(True)

        if not sim.Successful:
            print("    прогон не сошёлся на t =", t)
            return None

        y = s8.Y("METHANOL").Value

        if y >= BREAKTHROUGH:
            # линейная интерполяция между последними двумя точками
            if y > y_prev:
                frac = (BREAKTHROUGH - y_prev) / (y - y_prev)
            else:
                frac = 0.0
            t_bt = t_prev + frac * (t - t_prev)
            return t_bt / 3600.0

        t_prev, y_prev = t, y

    print("    порог не достигнут за", MAX_TIME_S / 3600.0, "ч")
    return None


# ------------------------------------------------------------------ сетка

def build_grid():
    """
    Точки для выборки. Начните с малого — проверьте, что всё работает,
    потом расширяйте списки.
    """
    temps = [298.15, 308.15, 313.15, 318.15, 328.15, 338.15]      # 25/45/55/65 C
    caps = [1.0, 0.85, 0.7, 0.55, 0.42]                # остаточная ёмкость
    w_res = [0.0]                                 # остаточная загрузка
    y_me = [88e-6, 132e-6, 160e-6, 190e-6, 226e-6]                               # метанол в сырье

    grid = []
    for T in temps:
        for c in caps:
            for w in w_res:
                for y in y_me:
                    grid.append((T, c, w, y))
    return grid


# ------------------------------------------------------------------ main

def main():
    grid = build_grid()
    print("Точек в сетке:", len(grid))

    new_file = not os.path.exists(OUT_CSV)
    f = open(OUT_CSV, "a", newline="", encoding="utf-8")
    wr = csv.writer(f, delimiter=";")
    if new_file:
        wr.writerow(["T_K", "T_C", "capacity_frac", "w_residual",
                     "y_methanol_ppm", "IP1_methanol", "IP2_methanol",
                     "t_breakthrough_h"])

    for n, (T, cap, w, y) in enumerate(grid, 1):
        print(f"\n[{n}/{len(grid)}] T={T-273.15:.0f}C  ёмкость={cap:.3f}  "
              f"метанол={y*1e6:.0f}ppm")

        kill_acm()
        try:
            app = open_model(ADA)
            sim = app.Simulation
            ip = set_params(sim, T, cap, w, y)
            t_bt = run_to_breakthrough(sim)
        except Exception as e:
            print("    ОШИБКА:", type(e).__name__, e)
            t_bt, ip = None, {"ip1_me": 0, "ip2_me": 0}

        if t_bt is not None:
            print(f"    проскок 10 ppm: {t_bt:.3f} ч")

        wr.writerow([f"{T:.2f}", f"{T-273.15:.1f}", f"{cap:.4f}", f"{w:.3e}",
                     f"{y*1e6:.1f}", f"{ip['ip1_me']:.4f}",
                     f"{ip['ip2_me']:.2f}",
                     f"{t_bt:.4f}" if t_bt is not None else ""])
        f.flush()

    f.close()
    kill_acm()
    print("\nГотово. Результаты:", OUT_CSV)


if __name__ == "__main__":
    main()
