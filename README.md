# Surrogate Model for Adsorbent Bed Service Life

*[Русская версия](README.ru.md)*

Diagnosing the mechanism of adsorbent performance loss from the shape of the breakthrough curve, plus a fast surrogate model trained on a set of rigorous Aspen Adsorption runs.

Aspen HYSYS and Aspen Adsorption linked through COM, automated sample generation, and a comparison of a physics-based parametric model against gradient boosting.

---

## Problem

A cyclic adsorption unit for natural gas dehydration shows methanol levels in the dried gas above the specification limit. The cause is unknown: the adsorbent may be degraded, regeneration may be incomplete, or the bed may not be cooled enough. Direct diagnosis would require opening the vessel and shutting the unit down.

The task is to identify the mechanism by calculation and to estimate the remaining service life of the bed without opening the vessel.

Three mechanisms leave distinguishable signatures on the breakthrough curve:

| Mechanism | Signature on the curve |
| --- | --- |
| Loss of equilibrium capacity | monotonic rise at the end of the cycle, over a timescale of hours |
| Incomplete regeneration | non-zero outlet concentration from the first minute of the cycle |
| Insufficient bed cooling | a peak right after switching, followed by a decay |

---

## Method

### 1. Bed model

Dynamic model in Aspen Adsorption: 20 axial nodes, Langmuir isotherm in concentration form, Lumped Resistance kinetics, isothermal approximation.

Calibration was performed against an **independent reference point supplied by the adsorbent manufacturer**, not against operating data. This avoids circularity: the model knows nothing about the deviations it is later asked to explain. Deviation from the reference point is 0.009 %.

### 2. Rescaling the isotherm with temperature

The Langmuir isotherm in Aspen Adsorption carries no temperature dependence, so its parameters are recalculated by hand for each isothermal run.

Reducing it to the canonical form `W = q_s·b·C/(1 + b·C)` gives `IP2 = b`, `IP1 = q_s·b`, `q_s = IP1/IP2`. The van 't Hoff equation is applied to the equilibrium constant `b`:

```
f(T) = (T/T₀) · exp[(Q/R) · (1/T − 1/T₀)]
IP1(T) = IP1(T₀) · f(T)
IP2(T) = IP2(T₀) · f(T)
```

Both coefficients are scaled by the same factor. Otherwise the saturation capacity `q_s` changes implicitly, which is physically wrong and underestimates the equilibrium capacity by 41 % at 65 °C.

The factor `T/T₀` in front of the exponential follows from the concentration form of the isotherm: `b_C = b_P·z·R·T`, whereas the van 't Hoff equation describes the pressure form. Its contribution reaches 13 %.

Input sanity check: `IP1/IP2` must stay constant at any temperature.

### 3. Automated sample generation

Aspen Adsorption is driven from Python over COM. The model is opened in a background process with no graphical interface, parameters are written, the run is started, and the result is read back.

A single point calculated by hand takes about 5 minutes. Automated sweeps cover the whole operating map in one pass.

218 runs were collected over four parameters:

| Parameter | Range | Levels |
| --- | --- | --- |
| Bed temperature | 25–65 °C | 6 |
| Residual adsorbent capacity | 0.42–1.00 | 5 |
| Residual loading after regeneration | 0–15 % of equilibrium | 5 |
| Feed impurity concentration | 88–226 ppm | 5 |

### 4. Surrogate model

Breakthrough time:

```
t = k · q*(T, cap, y) · M / (F · y)
q* = IP1(T)·cap^α · C / (1 + IP2(T)·C),   C = ρ(T)·y·10⁻⁶
```

Outlet impurity at the start of the cycle is obtained by inverting the Langmuir isotherm with respect to gas concentration at a given residual loading:

```
C = W_res / (IP1(T)·cap − IP2(T)·W_res)
y_start = k · C / ρ(T) · 10⁶
```

---

## Results

### Effect of bed temperature

| Bed temperature | Breakthrough time | Ratio to the 12 h cycle |
| --- | --- | --- |
| 25 °C | 28.5 h | 2.37 |
| 45 °C | 11.0 h | **0.92** |
| 55 °C | 6.4 h | 0.54 |
| 65 °C | 3.8 h | 0.32 |

At 45 °C, the lower bound of the design cooling range, even a fully sound and fully regenerated bed fails to sustain a 12-hour cycle.

### Sensitivity hierarchy

What it takes to reach the cycle limit:

| Mechanism | Threshold |
| --- | --- |
| Loss of equilibrium capacity | −58 % capacity |
| Incomplete regeneration | 10 % residual loading |
| Insufficient bed cooling | 45 °C, within design spec |

**Bed temperature ≫ completeness of regeneration > capacity loss.**

### Combined effect

| Bed state at the start of the cycle | Outlet, ppm |
| --- | --- |
| 10 % residual, 25 °C | 6.3 — within spec |
| Clean bed, 45 °C | 0.0 — within spec |
| 10 % residual, 45 °C | **23.0 — off-spec** |
| Limit | 10 |

Neither factor alone produces an exceedance. Both lie within design tolerances.

### Operating map

Methanol at the outlet at the start of the cycle, ppm (limit 10), at full adsorbent capacity:

| Residual | 25 °C | 40 °C | 45 °C | 55 °C | 65 °C |
| --- | --- | --- | --- | --- | --- |
| 0 % | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 % | 1.8 | 4.9 | 6.7 | 12.0 | 20.9 |
| 6 % | 3.7 | 9.9 | 13.5 | 24.4 | 42.4 |
| 10 % | 6.3 | 16.9 | 23.0 | 41.4 | 72.0 |
| 15 % | 9.7 | 26.0 | 35.4 | 63.8 | 110.9 |

The spec boundary runs diagonally: at 25 °C a residual of up to 15 % is acceptable, while at 55 °C even 3 % already pushes the unit off-spec.

### Comparison of surrogate model forms

Hold-out set, 30 % of the data:

| Target | Model | MAPE | Max error | R² | Coefficients |
| --- | --- | --- | --- | --- | --- |
| Breakthrough time, 166 points | physics-based parametric | **1.06 %** | 6.24 % | 0.99986 | 3 |
| | log-linear | 6.21 % | 22.20 % | 0.97726 | 4 |
| | gradient boosting | 2.10 % | 6.32 % | 0.99679 | 800 trees |
| Outlet at cycle start, 50 points | physics-based parametric | **0.13 %** | 0.34 % | 0.999998 | 2 |
| | log-linear | 0.39 % | 1.11 % | 0.99995 | 4 |
| | gradient boosting | 3.32 % | 15.52 % | 0.99225 | 600 trees |

For the outlet at cycle start the physics-based form is 25 times more accurate on MAPE while using two coefficients against 600 trees. For breakthrough time the margin is narrower: twice as accurate on MAPE, with maximum errors that are effectively equal, 6.24 % against 6.32 %.

The bed response is an inverted Langmuir isotherm, a smooth function whose shape is known from physics. Piecewise-constant trees approximate it at a visible cost on a sample of this size, and the log-linear form is the weakest of the three on breakthrough time.

**Methodological conclusion: gradient boosting buys nothing here that the physical form does not already provide, while carrying two to three orders of magnitude more parameters.** The simplest adequate form was chosen on the strength of the comparison, not assumed in advance.

Every number in this section is reproduced by `src/surrogate.py`; the random seeds are fixed in the code.

### Recovery of physical constants

| Quantity | Set in the model | Recovered by the surrogate | Reference range |
| --- | --- | --- | --- |
| Heat of adsorption of methanol, kJ/mol | 50.0 | 55.4 from breakthrough time, 51.1 from cycle-start outlet | 45–60 |
| Exponent on residual capacity | 1.0 | 1.0050 | 1.0 |

Coefficients were obtained by fitting the sample; reference values took no part in the fit.

---

## Validation

| Check | Reference | Result | Deviation |
| --- | --- | --- | --- |
| Manufacturer reference point | 24.0000 h | 24.0023 h | 0.009 % |
| Automated vs manual run, 25 °C | 28.46 h | 28.454 h | 0.02 % |
| Automated vs manual run, 45 °C | 11.01 h | 11.005 h | 0.05 % |
| Automated vs manual run, 55 °C | 6.44 h | 6.436 h | 0.06 % |
| Automated vs manual run, 65 °C | 3.80 h | 3.790 h | 0.26 % |
| Outlet at cycle start | 23.0 ppm | 23.023 ppm | 0.10 % |
| Methanol mass balance | — | — | 3.2 % |

Robustness to the heat of adsorption: at 65 °C, `Q = 40` kJ/mol gives roughly 7.2 h, `Q = 50` gives 3.80 h, and `Q = 60` gives about 3.0 h. Across the whole physically admissible range, the service life of a hot bed stays below the cycle duration.

Kinetics check: changing the mass transfer coefficient by a factor of 25 shifts the result by 3 %. The process is equilibrium-limited.

---

## Repository layout

```
.
├── README.md
├── README.ru.md
├── LICENSE
├── requirements.txt
├── src/
│   ├── hysys_reader.py        reads process conditions from Aspen HYSYS over COM
│   ├── acm_runner.py          automated sweeps, three-parameter grid
│   ├── acm_runner4.py         automated sweeps including residual loading
│   ├── surrogate.py           training and validation of the surrogate model
│   └── curve.py               breakthrough curve plotting
└── data/
    ├── runs.csv               150 runs, three parameters
    └── runs4.csv              68 runs, four parameters
```

---

## Running the code

### Requirements

- Windows with Aspen HYSYS and Aspen Adsorption installed (V14 or compatible)
- Python 3.10+, matching the bitness of the Aspen installation

```bash
pip install -r requirements.txt
```

### Training the surrogate on the supplied data

A standalone step; Aspen is not required:

```bash
cd src
python surrogate.py
```

The script reads `../data/runs.csv` and `../data/runs4.csv`, trains both models, compares them against gradient boosting on a hold-out set, prints metrics and the operating map, and saves the coefficients to `surrogate_params.json`.

### Generating a new sample

Requires an Aspen Adsorption installation and a prepared model file.

```bash
taskkill /F /IM AspenModeler.exe /T
python acm_runner.py
```

Grid ranges are defined in `build_grid()`. Results are appended to the CSV after every point, so an interrupted run loses nothing.

For the fourth parameter, template files with different residual loadings must be prepared in advance (see below), then:

```bash
python acm_runner4.py
```

### Reading conditions from Aspen HYSYS

```bash
python hysys_reader.py
```

Connects to a running HYSYS instance, reads the material streams entering the adsorber, and converts them into boundary block parameters for Aspen Adsorption.

---

## Notes on the Aspen Adsorption COM interface

Documentation is scarce, so what follows was established experimentally. It may save someone a few days.

- **The type library is not published.** `dir()` returns an empty list and `win32com.client.gencache.EnsureDispatch` fails. Access is possible only through names known in advance.

- **`OpenDocument` has to be called through a direct `Invoke`.** Accessing it as an ordinary property is rejected with `A string value was expected`:

  ```python
  app = win32com.client.Dispatch("ACM Application")
  app._oleobj_.Invoke(app._oleobj_.GetIDsOfNames("OpenDocument"), 0, 1, 1, path)
  ```

- **Objects cannot be converted to strings.** `print(obj)` recurses infinitely inside `__str__`. Use `repr()` and read `.Value` instead.

- **`GetActiveObject` does not work** — the instance is not registered in the running object table. The model must be opened by the script, not by the user.

- **An instance opened manually blocks `OpenDocument`** with `A new document could not be created`. Existing processes must be killed before launching.

- **Accumulated processes hang subsequent calls.** Killing them before every run is built into the scripts.

- **`Simulation.Time` is read-only.** `Restart()` resumes an interrupted run rather than reinitialising it.

- **Bed initialisation over COM is not available.** Values written directly into `W(node, comp)` or `W_First_Node` are discarded by the solver when the initial state is assembled: after 600 s of simulated time, an assigned `1.69e-4` collapses to `1.8e-11`. The workaround is a set of template files prepared by hand.

- **Opening a file resets the clock but not the concentrations.** A file saved after a run starts with a saturated bed. A separate template is needed, saved after initialisation but before any run.

### Object access paths

| Task | Call |
| --- | --- |
| Flowsheet blocks | `Simulation.Flowsheet.Blocks.Item(n)`, indexed from 1 |
| Isotherm parameter | `Blocks.Item(2).Layer(1).IP(1,"METHANOL").Value` |
| Loading at a node | `Layer(1).W(node,"METHANOL").Value` |
| Initial loading | `Layer(1).W_First_Node(comp)`, properties `Spec` and `Value` |
| Feed parameters | `Blocks.Item(1).T_Fwd.Value`, `.F.Value`, `.Y_Fwd(comp).Value` |
| Run control | `Simulation.EndTime`, `Simulation.Run(True)` |
| Convergence flag | `Simulation.Successful` |
| Outlet result | `Flowsheet.Streams.Item(2).Y("METHANOL").Value` |

---

## Preparing the template files

For runs with a non-zero residual loading, initialisation is done by hand once per value:

1. Open the base model and run Reset
2. `B2 → Presets/Initials`: for `W_First_Node("METHANOL")` switch `Spec` from `RateInitial` to `Initial`, enter the loading, and zero out `Y_First_Node("METHANOL")`
3. `B2 → Configure → Initialize` (this item is absent from the Run menu)
4. **Without running the simulation**, save under a separate name

Check: after reopening the template, `Layer(1).W(10,"METHANOL").Value` should return the assigned value rather than zero.

---

## Limitations

- **Isothermal approximation.** Runs at elevated bed temperature give an upper bound on the damage from insufficient cooling. The peak-then-decay shape is not reproduced; the result is a plateau whose height matches the calculated peak. Quantitative reproduction requires a non-isothermal formulation.

- **Mismatch of characteristic times.** The thermal front lags the gas front by roughly a factor of 11; front transit through the bed takes 2–3 min, or 5–6 min accounting for the vessel metal. The observed transient lasts tens of minutes. The order-of-magnitude discrepancy remains unexplained.

- **Ill-conditioned inverse problem.** The pair (residual loading, bed temperature) cannot be separated from a single point on the breakthrough curve. Unambiguous diagnosis requires an independent measurement of bed temperature at the moment the vessel is put on line.

- **Channeling** is not characterised quantitatively; it would require a two-dimensional formulation or an explicit bypass flow fraction.

- **A single unit.** Transferability of the method is argued structurally but has not been tested on other installations.

---

## License

MIT
