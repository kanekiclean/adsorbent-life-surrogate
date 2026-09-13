# -*- coding: utf-8 -*-
"""Собирает analysis.ipynb. Запускать из корня репозитория."""

import json
import io

def md(src):
    return {"cell_type": "markdown", "metadata": {},
            "source": src.splitlines(keepends=True)}

def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}

cells = []

cells.append(md("""# Adsorbent bed service life - data walkthrough

This notebook reproduces the analysis in the repository from the published data only.
**Aspen is not required.** Everything below runs on the two CSV files in `data/`.

See [README.md](README.md) for the method and the full discussion.
"""))

cells.append(code("""import os, sys, subprocess
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import Image, display

sys.path.insert(0, "src")
import make_figures as mf

print("python:", sys.version.split()[0])
"""))

cells.append(md("""## 1. The data

Two samples of rigorous Aspen Adsorption runs, generated automatically over a parameter grid.

- `runs.csv` - three parameters: bed temperature, residual adsorbent capacity, feed concentration
- `runs4.csv` - adds the residual loading left in the bed after regeneration
"""))

cells.append(code("""d = mf.load("runs.csv")
d4 = mf.load("runs4.csv")

# rows where the bed is off-spec from the first step are an artefact, not a breakthrough time
keep = d4["t_breakthrough_h"] > 0.5
d4 = {k: v[keep] for k, v in d4.items()}

print("runs.csv :", len(d["t_breakthrough_h"]), "runs")
print("runs4.csv:", len(d4["t_breakthrough_h"]), "runs after filtering")
print()
for name, arr in [("bed temperature, C", d["T_C"]),
                  ("residual capacity", d["capacity_frac"]),
                  ("feed methanol, ppm", d["y_methanol_ppm"]),
                  ("breakthrough time, h", d["t_breakthrough_h"])]:
    print("{:24s} {:8.2f} .. {:8.2f}".format(name, np.nanmin(arr), np.nanmax(arr)))
"""))

cells.append(md("""## 2. Operating map

Methanol at the outlet at the start of the cycle, in ppm. The specification limit is 10 ppm.

Rows are the residual loading left after regeneration, columns are the bed temperature.
Neither factor alone pushes the unit off-spec; their combination does.
"""))

cells.append(code("""ws = np.unique(np.round(d4["w_residual"], 4))
ts = np.unique(np.round(d4["T_C"], 1))

print("residual", "".join("{:>9.0f} C".format(t) for t in ts))
for w in ws:
    row = "{:6.0f} %  ".format(w * 100)
    for t in ts:
        sel = (np.isclose(np.round(d4["w_residual"], 4), w)
               & np.isclose(np.round(d4["T_C"], 1), t))
        if sel.any():
            row += "{:>11.1f}".format(np.nanmean(d4["y_start_ppm"][sel]))
        else:
            row += "{:>11s}".format("-")
    print(row)
"""))

cells.append(md("""## 3. Figures

Built by `src/make_figures.py` from the same data.
"""))

cells.append(code("""for path in (mf.fig_time_vs_temperature(d),
             mf.fig_operating_map(d4),
             mf.fig_concentration(d)):
    display(Image(filename=path))
"""))

cells.append(md("""## 4. Surrogate model: physics against gradient boosting

`src/surrogate.py` fits three forms on the same hold-out split and prints the metrics.
Random seeds are fixed, so these numbers match the table in the README.
"""))

cells.append(code("""res = subprocess.run([sys.executable, "surrogate.py"], cwd="src",
                     capture_output=True, text=True)
print(res.stdout)
if res.returncode:
    print(res.stderr)
"""))

cells.append(md("""## 5. What comes out of it

- Bed temperature dominates. At 45 C, the lower bound of the design cooling range,
  even a sound and fully regenerated bed does not sustain the 12-hour cycle.
- Residual loading and temperature are individually within tolerance but jointly off-spec.
- The physics-based form, with two or three coefficients, matches or beats gradient
  boosting with hundreds of trees. The response is a smooth inverted Langmuir isotherm;
  there is nothing here for a tree ensemble to discover that the physics does not
  already provide.
"""))

nb = {"cells": cells,
      "metadata": {"kernelspec": {"display_name": "Python 3",
                                  "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}

with io.open("analysis.ipynb", "w", encoding="utf-8") as fh:
    json.dump(nb, fh, ensure_ascii=False, indent=1)

print("analysis.ipynb собран, ячеек:", len(cells))
