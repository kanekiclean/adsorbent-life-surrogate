# -*- coding: utf-8 -*-
"""Кривые проскока при разной температуре слоя -> PNG для слайда."""
import math, subprocess, time
import win32com.client as win32
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

F = r"C:\models\Adsorption_TEMPLATE.ada"
OUT = r"C:\models\breakthrough.png"

R, T0 = 8.314, 298.15
IP1, IP2, IP1W, IP2W = 8.59, 2500.0, 120.0, 4000.0
CASES = [(298.15, '25 °C', '#004596', 40),
         (318.15, '45 °C', '#2E75B6', 18),
         (328.15, '55 °C', '#E65907', 11),
         (338.15, '65 °C', '#C00000', 7)]
STEP = 1200.0            # шаг 20 мин


def f(T, Q):
    return (T / T0) * math.exp((Q / R) * (1.0 / T - 1.0 / T0))


def run(T, hours):
    subprocess.run("taskkill /F /IM AspenModeler.exe /T", shell=True, capture_output=True)
    time.sleep(1)
    a = win32.Dispatch("ACM Application")
    a._oleobj_.Invoke(a._oleobj_.GetIDsOfNames("OpenDocument"), 0, 1, 1, F)
    s = a.Simulation
    L = s.Flowsheet.Blocks.Item(2).Layer(1)
    fm, fw = f(T, 50000.0), f(T, 75380.0)
    L.IP(1, "METHANOL").Value = IP1 * fm
    L.IP(2, "METHANOL").Value = IP2 * fm
    L.IP(1, "WATER").Value = IP1W * fw
    L.IP(2, "WATER").Value = IP2W * fw
    B1 = s.Flowsheet.Blocks.Item(1)
    B1.T_Fwd.Value = T
    B1.F.Value = 6.2
    B1.Y_Fwd("METHANOL").Value = 132e-6
    s8 = s.Flowsheet.Streams.Item(2)
    s.CommunicationInterval = 60.0
    ts, ys, t = [0.0], [0.0], 0.0
    while t < hours * 3600:
        t += STEP
        s.EndTime = t
        s.Run(True)
        ts.append(t / 3600.0)
        ys.append(s8.Y("METHANOL").Value * 1e6)
    return ts, ys


plt.figure(figsize=(7.2, 4.4), dpi=200)
for T, lab, col, hrs in CASES:
    print(lab, '...')
    ts, ys = run(T, hrs)
    plt.plot(ts, ys, color=col, lw=2.2, label=f'слой {lab}')

plt.axhline(10, color='#E65907', ls='--', lw=1.4)
plt.text(0.4, 11.5, 'норма 10 ppm', color='#E65907', fontsize=9, weight='bold')
plt.xlabel('Время от начала цикла адсорбции, ч', fontsize=10)
plt.ylabel('Метанол на выходе слоя, ppm', fontsize=10)
plt.ylim(0, 60)
plt.xlim(0, 40)
plt.grid(alpha=.25)
plt.legend(fontsize=9, frameon=False)
plt.tight_layout()
plt.savefig(OUT)
subprocess.run("taskkill /F /IM AspenModeler.exe /T", shell=True, capture_output=True)
print('сохранено:', OUT)
