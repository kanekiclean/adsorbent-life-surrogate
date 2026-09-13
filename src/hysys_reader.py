# -*- coding: utf-8 -*-
"""
Связка HYSYS <-> Aspen Adsorption. Этап 1: чтение условий на входе в адсорбер.

Установка адсорбционной осушки, модель Unit_model_V1.hsc
Яковлев Н.Г., сентябрь 2026

Требуется: pip install pywin32
Запускать 32/64-битным Python в соответствии с разрядностью HYSYS.
"""

import win32com.client as win32

HSC_PATH = r"C:\models\Unit_model_V1.hsc"

# Имена объектов на флоушите
STREAM_FEED_A = "Gas_to_A"       # вход в первый адсорбер осушки
STREAM_FEED_B = "Gas_to_B"
SPLITTER_A = "X-100"
SPLITTER_B = "X-101"

# Компоненты, интересные для Adsorption
KEY_COMPS = ["Methane", "Nitrogen", "Methanol", "H2O"]


# ---------------------------------------------------------------- подключение

def connect(visible=True):
    """Подключается к запущенному HYSYS или открывает файл."""
    try:
        app = win32.GetActiveObject("HYSYS.Application")
        print("Подключились к запущенному HYSYS")
    except Exception:
        app = win32.Dispatch("HYSYS.Application")
        print("Запустили новый экземпляр HYSYS")

    app.Visible = visible

    # ищем уже открытый кейс, иначе открываем
    case = None
    for i in range(app.SimulationCases.Count):
        c = app.SimulationCases.Item(i)
        if HSC_PATH.lower().endswith(c.Title.Value.lower()):
            case = c
            print("Кейс уже открыт:", c.Title.Value)
            break
    if case is None:
        case = app.SimulationCases.Open(HSC_PATH)
        print("Открыли кейс:", HSC_PATH)

    case.Activate()
    return app, case


# ---------------------------------------------------------------- чтение

def read_stream(case, name):
    """Возвращает словарь с условиями материального потока."""
    fs = case.Flowsheet
    st = fs.MaterialStreams.Item(name)

    comps = [c.name for c in fs.FluidPackage.Components]
    fracs = list(st.ComponentMolarFractionValue)
    comp_map = dict(zip(comps, fracs))

    data = {
        "name": name,
        "molar_flow_kgmole_h": st.MolarFlow.GetValue("kgmole/h"),
        "T_C": st.Temperature.GetValue("C"),
        "P_bar": st.Pressure.GetValue("bar"),
        "MW": st.MolecularWeight.GetValue(),
        "comps": comp_map,
    }
    return data


def to_adsorption_inputs(data):
    """
    Пересчёт условий HYSYS в параметры блока B1 в Aspen Adsorption.

    B1 ожидает:
      F     кмоль/с
      T_Fwd K
      P     bar
      Y_Fwd мольные доли
    """
    F_kmol_s = data["molar_flow_kgmole_h"] / 3600.0
    T_K = data["T_C"] + 273.15
    P_bar = data["P_bar"]

    # Adsorption считает по четырём компонентам, остальные сворачиваем в метан.
    # Это допущение: C2+ по метанолу не конкурируют, инертны в модели слоя.
    y = data["comps"]
    y_methanol = y.get("Methanol", 0.0)
    y_water = y.get("H2O", 0.0)
    y_n2 = y.get("Nitrogen", 0.0)
    y_ch4 = 1.0 - y_methanol - y_water - y_n2   # остаток, замыкает баланс в 1,000

    return {
        "F": F_kmol_s,
        "T_Fwd": T_K,
        "P": P_bar,
        "Y_METHANE": y_ch4,
        "Y_NITROGEN": y_n2,
        "Y_METHANOL": y_methanol,
        "Y_WATER": y_water,
    }


# ---------------------------------------------------------------- разведка

def inspect(obj, title=""):
    """
    Печатает доступные свойства COM-объекта.
    Нужна один раз, чтобы узнать точные имена для Component Splitter.
    """
    print("\n--- Свойства объекта", title, "---")
    try:
        names = obj._oleobj_.GetTypeInfo().GetTypeAttr()
    except Exception:
        pass
    for attr in sorted(dir(obj)):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(obj, attr)
            if callable(val):
                continue
            print(f"  {attr:35s} = {val}")
        except Exception as e:
            print(f"  {attr:35s} <не читается: {type(e).__name__}>")


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    app, case = connect(visible=True)

    for sname in (STREAM_FEED_A, STREAM_FEED_B):
        d = read_stream(case, sname)
        print(f"\n=== {sname} ===")
        print(f"  Расход  {d['molar_flow_kgmole_h']:.1f} кгмоль/ч")
        print(f"  T       {d['T_C']:.2f} C")
        print(f"  P       {d['P_bar']:.2f} bar")
        print(f"  MW      {d['MW']:.3f}")
        for c in KEY_COMPS:
            v = d["comps"].get(c)
            if v is not None:
                print(f"  y({c:9s}) = {v:.6e}   ({v*1e6:.2f} ppm)")

        inp = to_adsorption_inputs(d)
        print("\n  --> в B1 Aspen Adsorption:")
        for k, v in inp.items():
            print(f"      {k:12s} = {v:.6g}")

    # Разведка по сплиттеру: раскомментировать один раз,
    # чтобы узнать, как называется свойство долей разделения
    #
    # spl = case.Flowsheet.Operations.Item(SPLITTER_A)
    # inspect(spl, SPLITTER_A)
