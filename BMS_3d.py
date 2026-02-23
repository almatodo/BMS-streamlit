# bms_app.py
import base64
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components  # fixes stray </div> by using components.html

st.set_page_config(layout="wide")
st.title("BMS Frontend Prototype")

# ============================================================
# 1) Helpers
# ============================================================
def img_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def fmt(v, nd=2, units=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NA"
    try:
        x = float(v)
        if abs(x) >= 1e6:
            s = f"{x:.3e}"
        elif abs(x) >= 1000:
            s = f"{x:.1f}"
        else:
            s = f"{x:.{nd}f}"
        return f"{s}{units}"
    except Exception:
        return str(v)


def canonical_col(s: str) -> str:
    """
    Canonicalize column names so matching survives:
    - non-breaking spaces
    - tabs / repeated whitespace
    - minor unit/frequency formatting differences
    Also strips trailing " [units](Hourly)" so we can fall back to base-name matching.
    """
    s = str(s)
    s = s.replace("\u00a0", " ").replace("\t", " ").strip()
    s = " ".join(s.split()).lower()
    s = re.sub(r"\s*\[[^\]]*\]\([^)]+\)\s*$", "", s)
    return s


def find_col(df: pd.DataFrame, wanted: str):
    """
    1) Exact match after whitespace normalization.
    2) Canonical match with units/frequency stripped.
    """
    w_full = " ".join(str(wanted).replace("\u00a0", " ").replace("\t", " ").strip().split()).lower()
    w_can = canonical_col(wanted)

    # pass 1: exact normalized match
    for c in df.columns:
        c_full = " ".join(str(c).replace("\u00a0", " ").replace("\t", " ").strip().split()).lower()
        if c_full == w_full:
            return c

    # pass 2: canonical match (units/frequency ignored)
    for c in df.columns:
        if canonical_col(c) == w_can:
            return c

    return None


@st.cache_data(show_spinner=False)
def load_csv_from_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def find_closest_row_by_oa(df: pd.DataFrame, oa_col: str, target_oa: float) -> int:
    return (df[oa_col] - target_oa).abs().idxmin()


# ============================================================
# 2) Render background image + manual-position tags (BAS-style)
#    Fixed-width canvas + horizontal scroll (consistent across screens)
# ============================================================
def render_background_with_tags(
    img_b64: str,
    tags: list[dict],
    canvas_width_px: int = 1500,
    height_px: int = 900,  # fallback only; JS will resize
):
    tags_html = ""
    for t in tags:
        cls = t.get("class", "")
        tags_html += (
            f'<div class="tag {cls}" style="left:{t["left"]}; top:{t["top"]};">'
            f'{t["html"]}'
            f"</div>\n"
        )

    html = f"""
    <style>
    html, body {{
        margin: 0;
        padding: 0;
    }}

    /* Scrollable viewport for small screens */
    .bmsViewport {{
        width: 100%;
        overflow-x: auto;
        overflow-y: hidden;
        padding-bottom: 6px;
    }}

    /* FIXED canvas width (consistent across monitors) */
    .bms {{
        position: relative;
        width: {canvas_width_px}px;
        margin: 0 auto;
        border-radius: 10px;
    }}

    .bms img {{
        width: {canvas_width_px}px;
        height: auto;
        display: block;
        border-radius: 10px;
    }}

    .tag {{
        position: absolute;
        min-width: 160px;
        padding: 8px 10px 7px 10px;
        color: #eaeef2;
        border-radius: 3px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        border: 1px solid rgba(255,255,255,0.18);
        background: linear-gradient(180deg, rgba(52,58,64,0.92), rgba(24,27,31,0.92));
        box-shadow:
            inset 0 1px 0 rgba(255,255,255,0.12),
            inset 0 -1px 0 rgba(0,0,0,0.35),
            0 2px 8px rgba(0,0,0,0.35);
        white-space: nowrap;
        z-index: 2;
        line-height: 1.05;
    }}

    .tag .label {{
        font-size: 11px;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        opacity: 0.85;
        margin-bottom: 4px;
    }}

    .tag .value {{
        font-size: 16px;
        font-weight: 700;
        color: #ffffff;
    }}

    .tag .unit {{
        font-size: 12px;
        font-weight: 600;
        opacity: 0.9;
        margin-left: 4px;
    }}

    .tag .led {{
        display: inline-block;
        width: 9px;
        height: 9px;
        border-radius: 50%;
        margin-right: 7px;
        box-shadow: 0 0 6px rgba(0,0,0,0.55), inset 0 1px 1px rgba(255,255,255,0.35);
        vertical-align: middle;
    }}
    .led-ok {{ background: #2ecc71; }}
    .led-warn {{ background: #f1c40f; }}
    .led-bad {{ background: #e74c3c; }}
    .led-off {{ background: #7f8c8d; }}

    .inactive {{
        opacity: 0.45;
        filter: grayscale(0.25);
    }}
    </style>

    <div class="bmsViewport" id="bmsViewport">
      <div class="bms" id="bmsRoot">
          <img id="bmsImg" src="data:image/svg+xml;base64,{img_b64}">
          {tags_html}
      </div>
    </div>

    <script>
    function setStreamlitFrameHeight(px) {{
        window.parent.postMessage({{
            isStreamlitMessage: true,
            type: "streamlit:setFrameHeight",
            height: Math.ceil(px)
        }}, "*");
    }}

    function resizeToContent() {{
        const root = document.getElementById("bmsRoot");
        const viewport = document.getElementById("bmsViewport");
        if (!root || !viewport) return;
        setStreamlitFrameHeight(root.getBoundingClientRect().height + 18);
    }}

    const img = document.getElementById("bmsImg");
    if (img) img.addEventListener("load", resizeToContent);

    window.addEventListener("resize", resizeToContent);

    const ro = new ResizeObserver(() => resizeToContent());
    const root = document.getElementById("bmsRoot");
    if (root) ro.observe(root);

    setTimeout(resizeToContent, 80);
    </script>
    """

    components.html(html, height=height_px, scrolling=False)


# ============================================================
# 3) Files: Images + CSV
# ============================================================
IMG_AHU = Path("AHU 3D BMS Schematic.svg")
IMG_HW = Path("HW 3D BMS Schematic.svg")
IMG_CHW = Path("CHW 3D BMS Schematic.svg")

missing_imgs = [p.name for p in [IMG_AHU, IMG_HW, IMG_CHW] if not p.exists()]
if missing_imgs:
    st.error(
        "Missing background image(s): " + ", ".join(missing_imgs)
        + "\n\nPut them in the same folder as bms_app.py (or update filenames in code)."
    )
    st.stop()

ahu_b64 = img_to_b64(IMG_AHU)
hw_b64 = img_to_b64(IMG_HW)
chw_b64 = img_to_b64(IMG_CHW)

with st.sidebar:
    st.header("EnergyPlus data source")
    uploaded = st.file_uploader("Upload EnergyPlus CSV (eplusout.csv)", type=["csv"])
    st.divider()
    st.header("Operator Inputs")
    oa_slider = st.slider("Outside Air Temperature (°C)", -40.0, 40.0, -5.0, 0.5)
    occupied_toggle = st.toggle("Occupied", value=True)

# Load df
if uploaded is not None:
    df = pd.read_csv(uploaded)
else:
    if Path("eplusout.csv").exists():
        df = load_csv_from_path("eplusout.csv")
    elif Path("Final VAV model.csv").exists():
        df = load_csv_from_path("Final VAV model.csv")
    else:
        st.error("Upload a CSV in the sidebar OR place eplusout.csv next to bms_app.py.")
        st.stop()

# ============================================================
# 4) Required columns (robust matching)
# ============================================================
OA_COL_WANTED = "Environment:Site Outdoor Air Drybulb Temperature [C](Hourly)"
DT_COL_WANTED = "Date/Time"
OCC_COL_WANTED = "SCH_OCC_FRACTION:Schedule Value [](Hourly)"

oa_col = find_col(df, OA_COL_WANTED)
dt_col = find_col(df, DT_COL_WANTED)
occ_col = find_col(df, OCC_COL_WANTED)

if oa_col is None:
    st.error(f"Missing required OA column:\n{OA_COL_WANTED}")
    st.stop()

df[oa_col] = pd.to_numeric(df[oa_col], errors="coerce")

# ============================================================
# 5) Occupancy filtering
# ============================================================
df_filt = df
occ_filter_used = False

if occ_col is not None:
    df_filt[occ_col] = pd.to_numeric(df_filt[occ_col], errors="coerce")
    if occupied_toggle:
        df_filt = df_filt[df_filt[occ_col] >= 0.5]
    else:
        df_filt = df_filt[df_filt[occ_col] < 0.5]
    occ_filter_used = True

    if df_filt.empty:
        st.error(
            "Occupancy filter left 0 rows.\n"
            "This usually means the schedule column is empty/NaN or not output correctly."
        )
        st.stop()
else:
    st.warning(
        f"Occupancy schedule column not found:\n{OCC_COL_WANTED}\n"
        "Occupied toggle will not filter until that output exists in the CSV."
    )

# ============================================================
# 6) Select closest OA row (within filtered df)
# ============================================================
row_i = find_closest_row_by_oa(df_filt, oa_col, oa_slider)
row = df_filt.loc[row_i]

matched_oa = row[oa_col]
matched_dt = row[dt_col] if dt_col is not None else f"Row {row_i}"
matched_occ = row[occ_col] if (occ_col is not None) else None


def header_caption():
    occ_part = ""
    if occ_filter_used:
        occ_part = f" | Occ Sch: {fmt(matched_occ, nd=0)}"
    return (
        f"Selected row: {row_i} | Date/Time: {matched_dt} | "
        f"Slider OA: {oa_slider:.1f}°C | Matched OA: {fmt(matched_oa, nd=2, units='°C')}"
        f"{occ_part}"
    )


# ============================================================
# 7) Wiring map (Displayed label -> CSV column)
# ============================================================
ZONE_FOR_SETPOINTS = "F1_NW"

# --- CHW wanted columns ---
CHW_PUMP_FLOW_WANTED = "CHILLED WATER LOOP CHW SUPPLY PUMP:Pump Mass Flow Rate [kg/s](Hourly)"
CHW_PUMP_PWR_WANTED = "CHILLED WATER LOOP CHW SUPPLY PUMP:Pump Electricity Rate [W](Hourly)"
CHW_PUMP_EN_WANTED = "CHILLED WATER LOOP CHW SUPPLY PUMP:Pump Electricity Energy [J](Hourly)"
CHILLER_ELEC_WANTED = "MAIN CHILLER:Chiller Electricity Rate [W](Hourly)"

CHW_SUP_TEMP_WANTED = "CHILLED WATER LOOP CHW SUPPLY OUTLET:System Node Temperature [C](Hourly)"
CHW_SUP_SETP_WANTED = "CHILLED WATER LOOP CHW SUPPLY OUTLET:System Node Setpoint Temperature [C](Hourly)"
CHW_RTN_TEMP_WANTED = "CHILLED WATER LOOP CHW DEMAND OUTLET:System Node Temperature [C](Hourly)"

# --- CHW bypass wanted columns (you added these to the IDF) ---
CHW_SUP_BYPASS_MDOT_WANTED = "CHILLED WATER LOOP CHW SUPPLY BYPASS INLET:System Node Mass Flow Rate [kg/s](Hourly)"
CHW_DEM_BYPASS_MDOT_WANTED = "CHILLED WATER LOOP CHW DEMAND BYPASS INLET:System Node Mass Flow Rate [kg/s](Hourly)"

# --- HW pump electrical points (optional to display later) ---
HW_PUMP_PWR_WANTED = "HOT WATER LOOP HW SUPPLY PUMP:Pump Electricity Rate [W](Hourly)"
HW_PUMP_EN_WANTED = "HOT WATER LOOP HW SUPPLY PUMP:Pump Electricity Energy [J](Hourly)"

# --- NEW: Fan flow for VFD-style proxy (speed% + Hz) ---
FAN_MDOT_WANTED = "AHU 1 FLOORS 1-3 SUPPLY FAN OUTLET:System Node Mass Flow Rate [kg/s](Hourly)"

MAP_WANTED = {
    #"Occ Sch (0/1)": OCC_COL_WANTED,
    "OA Temp": OA_COL_WANTED,
    # AHU temps
    "Return Air Temp": "AHU 1 FLOORS 1-3 RETURN AIR OUTLET:System Node Temperature [C](Hourly)",
    "Mixed Air Temp": "AHU 1 FLOORS 1-3 MIXED AIR OUTLET:System Node Temperature [C](Hourly)",
    "Supply Air Temp": "AHU 1 FLOORS 1-3 SUPPLY FAN OUTLET:System Node Temperature [C](Hourly)",
    # Zone thermostat setpoints (one zone only)
    "Zone Heating Setpoint": f"{ZONE_FOR_SETPOINTS}:Zone Thermostat Heating Setpoint Temperature [C](Hourly)",
    "Zone Cooling Setpoint": f"{ZONE_FOR_SETPOINTS}:Zone Thermostat Cooling Setpoint Temperature [C](Hourly)",
    # Coil flows (AHU)
    "CHW Coil Flow": "AHU 1 FLOORS 1-3 COOLING COIL CHW INLET:System Node Mass Flow Rate [kg/s](Hourly)",
    "HW Coil Flow": "AHU 1 FLOORS 1-3 HEATING COIL HW INLET:System Node Mass Flow Rate [kg/s](Hourly)",
    # Fan
    "Supply Fan Power": "AHU 1 FLOORS 1-3 SUPPLY FAN:Fan Electricity Rate [W](Hourly)",
    "Supply Fan Flow": FAN_MDOT_WANTED,  # NEW (used for fan speed proxy)
    # HW pumps / plant
    "Pump 3 Flow": "HOT WATER LOOP HW SUPPLY PUMP:Pump Mass Flow Rate [kg/s](Hourly)",
    "HW Pump Power": HW_PUMP_PWR_WANTED,
    "HW Pump Energy": HW_PUMP_EN_WANTED,
    # CHW pumps / plant
    "CHW Pump Flow": CHW_PUMP_FLOW_WANTED,
    "CHW Pump Power": CHW_PUMP_PWR_WANTED,
    "CHW Pump Energy": CHW_PUMP_EN_WANTED,
    "Chiller Elec Rate": CHILLER_ELEC_WANTED,
    # OA-related
    "OA Flow Fraction (E+)": "AHU 1 FLOORS 1-3:Air System Outdoor Air Flow Fraction [](Hourly)",
    "OA Vol Flow (StdDens)": "AHU 1 FLOORS 1-3 OUTDOOR AIR INLET:System Node Standard Density Volume Flow Rate [m3/s](Hourly)",
    # HW plant points
    "HW SUPP TEMP": "HOT WATER LOOP HW SUPPLY OUTLET:System Node Temperature [C](Hourly)",
    "HW SUPP SETPNT": "HOT WATER LOOP HW SUPPLY OUTLET:System Node Setpoint Temperature [C](Hourly)",
    "HW RTN TEMP": "HOT WATER LOOP HW DEMAND OUTLET:System Node Temperature [C](Hourly)",
    "Boiler 1 Gas Rate": "MAIN BOILER:Boiler NaturalGas Rate [W](Hourly)",
    "Boiler 2 Gas Rate": "SECONDARY BOILER:Boiler NaturalGas Rate [W](Hourly)",
    # CHW plant points
    "CHW SUPP TEMP": CHW_SUP_TEMP_WANTED,
    "CHW SUPP SETPNT": CHW_SUP_SETP_WANTED,
    "CHW RTN TEMP": CHW_RTN_TEMP_WANTED,
    # CHW bypass (new)
    "CHW Supply Bypass Flow": CHW_SUP_BYPASS_MDOT_WANTED,
    "CHW Demand Bypass Flow": CHW_DEM_BYPASS_MDOT_WANTED,
}

MAP = {disp: find_col(df, wanted_col) for disp, wanted_col in MAP_WANTED.items()}


def v(disp):
    col = MAP.get(disp)
    if col is None:
        return None
    return row[col]


# ============================================================
# Fixed "max" values you specified (used as 100% open references)
# ============================================================
FAN_MAX_M3S = 14.16  # design max supply flow (m3/s) used for OA damper %

CHW_MAX_M3S = 1.14e-2  # cooling coil max water flow (m3/s) -> 100% valve
HW_MAX_M3S = 9.50e-3  # heating coil max water flow (m3/s) -> 100% valve

RHO_WATER = 1000.0  # kg/m3 proxy conversion for water
CHW_MAX_KGS = CHW_MAX_M3S * RHO_WATER
HW_MAX_KGS = HW_MAX_M3S * RHO_WATER


def _chw_pump_max_flow_from_csv():
    """Use filtered data to compute a reasonable 'max' for CHW pump flow (for % speed proxy)."""
    col = MAP.get("CHW Pump Flow")
    if col is None:
        return None
    s = pd.to_numeric(df_filt[col], errors="coerce")
    if s.dropna().empty:
        return None
    mx = float(s.max())
    if mx <= 0:
        return None
    return mx


def _hw_pump3_max_flow_from_csv():
    """Use filtered data to compute a reasonable 'max' for HW pump 3 flow (for % speed proxy)."""
    col = MAP.get("Pump 3 Flow")
    if col is None:
        return None
    s = pd.to_numeric(df_filt[col], errors="coerce")
    if s.dropna().empty:
        return None
    mx = float(s.max())
    if mx <= 0:
        return None
    return mx


def _fan_max_mdot_from_csv():
    """Use filtered data to compute a reasonable 'max' for fan flow (for % speed proxy)."""
    col = MAP.get("Supply Fan Flow")
    if col is None:
        return None
    s = pd.to_numeric(df_filt[col], errors="coerce")
    if s.dropna().empty:
        return None
    mx = float(s.max())
    if mx <= 0:
        return None
    return mx


CHW_PUMP_MAX_KGS_PROXY = _chw_pump_max_flow_from_csv()
HW_PUMP3_MAX_KGS_PROXY = _hw_pump3_max_flow_from_csv()
FAN_MAX_KGS_PROXY = _fan_max_mdot_from_csv()


def computed_value(disp: str):
    """Computed points that aren't direct CSV columns."""

    # -------------------------
    # AHU dummy safety points (NEW)
    # -------------------------
    if disp == "FreezeStat":
        return "NORMAL"
    if disp == "Pressure Switch":
        return "NORMAL"

    # -------------------------
    # AHU dampers
    # -------------------------
    if disp == "OA Damper Position (%)":
        oa_v = v("OA Vol Flow (StdDens)")
        if oa_v is None or (isinstance(oa_v, float) and pd.isna(oa_v)):
            return None
        try:
            pct = 100.0 * float(oa_v) / FAN_MAX_M3S
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "Return Damper Position (%)":
        oa_frac = v("OA Flow Fraction (E+)")
        if oa_frac is None or (isinstance(oa_frac, float) and pd.isna(oa_frac)):
            return None
        try:
            pct = 100.0 * (1.0 - float(oa_frac))
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    # -------------------------
    # AHU Fan VFD-style proxy (NEW)
    # -------------------------
    if disp == "Supply Fan Speed (%)":
        f = v("Supply Fan Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        if FAN_MAX_KGS_PROXY is None:
            return None
        try:
            pct = 100.0 * float(f) / float(FAN_MAX_KGS_PROXY)
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "Supply Fan VFD Output (Hz)":
        sp = computed_value("Supply Fan Speed (%)")
        if sp is None:
            return None
        try:
            hz = 60.0 * float(sp) / 100.0
            return max(0.0, min(60.0, hz))
        except Exception:
            return None

    if disp == "Supply Fan VFD Alarm":
        return "NORMAL"

    # -------------------------
    # Valve position proxies
    # -------------------------
    if disp == "CHW Valve Position (%)":
        chw_mdot = v("CHW Coil Flow")
        if chw_mdot is None or (isinstance(chw_mdot, float) and pd.isna(chw_mdot)):
            return None
        try:
            pct = 100.0 * float(chw_mdot) / CHW_MAX_KGS
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "HW Valve Position (%)":
        hw_mdot = v("HW Coil Flow")
        if hw_mdot is None or (isinstance(hw_mdot, float) and pd.isna(hw_mdot)):
            return None
        try:
            pct = 100.0 * float(hw_mdot) / HW_MAX_KGS
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    # -------------------------
    # HW statuses
    # -------------------------
    if disp == "Boiler 1 Status":
        gas = v("Boiler 1 Gas Rate")
        if gas is None or (isinstance(gas, float) and pd.isna(gas)):
            return None
        try:
            return "ON" if float(gas) > 0.0 else "OFF"
        except Exception:
            return None

    if disp == "Boiler 2 Status":
        gas = v("Boiler 2 Gas Rate")
        if gas is None or (isinstance(gas, float) and pd.isna(gas)):
            return None
        try:
            return "ON" if float(gas) > 0.0 else "OFF"
        except Exception:
            return None

    if disp == "Pump 3 Status":
        f = v("Pump 3 Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        try:
            return "ON" if float(f) > 0.0 else "OFF"
        except Exception:
            return None

    # Dummy Pump 4 (HW)
    if disp == "Pump 4 Status":
        return "OFF"
    if disp == "Pump 4 Flow":
        return 0.0

    # -------------------------
    # HW pump VFD-style points (mirrors CHW)
    # -------------------------
    if disp == "HW Pump 3 Speed (%)":
        f = v("Pump 3 Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        if HW_PUMP3_MAX_KGS_PROXY is None:
            return None
        try:
            pct = 100.0 * float(f) / float(HW_PUMP3_MAX_KGS_PROXY)
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "HW Pump 3 VFD Output (Hz)":
        sp = computed_value("HW Pump 3 Speed (%)")
        if sp is None:
            return None
        try:
            hz = 60.0 * float(sp) / 100.0
            return max(0.0, min(60.0, hz))
        except Exception:
            return None

    if disp == "HW Pump 3 VFD Alarm":
        return "NORMAL"

    # Pump 4 dummy VFD-style points
    if disp == "HW Pump 4 Speed (%)":
        return 0.0
    if disp == "HW Pump 4 VFD Output (Hz)":
        return 0.0
    if disp == "HW Pump 4 VFD Alarm":
        return "NORMAL"

    # -------------------------
    # CHW bypass flow & bypass “valve” position (PROXY)
    # -------------------------
    if disp == "CHW Supply Bypass (%)":
        bypass = v("CHW Supply Bypass Flow")
        pump = v("CHW Pump Flow")
        if bypass is None or pump is None:
            return None
        if (isinstance(bypass, float) and pd.isna(bypass)) or (isinstance(pump, float) and pd.isna(pump)):
            return None
        try:
            pump_f = float(pump)
            if pump_f <= 0.0:
                return 0.0
            pct = 100.0 * float(bypass) / pump_f
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "CHW Demand Bypass (%)":
        bypass = v("CHW Demand Bypass Flow")
        pump = v("CHW Pump Flow")
        if bypass is None or pump is None:
            return None
        if (isinstance(bypass, float) and pd.isna(bypass)) or (isinstance(pump, float) and pd.isna(pump)):
            return None
        try:
            pump_f = float(pump)
            if pump_f <= 0.0:
                return 0.0
            pct = 100.0 * float(bypass) / pump_f
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    # -------------------------
    # CHW tab points
    # -------------------------
    if disp == "CHW Flow Meter (L/s)":
        f = v("CHW Pump Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        try:
            # For water, kg/s ≈ L/s
            return float(f)
        except Exception:
            return None

    if disp == "CHW Pump 1 Enable":
        f = v("CHW Pump Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        try:
            return "ON" if float(f) > 0.0 else "OFF"
        except Exception:
            return None

    if disp == "CHW Pump 1 Status":
        f = v("CHW Pump Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        try:
            return "ON" if float(f) > 0.0 else "OFF"
        except Exception:
            return None

    if disp == "CHW Pump 1 Speed (%)":
        f = v("CHW Pump Flow")
        if f is None or (isinstance(f, float) and pd.isna(f)):
            return None
        if CHW_PUMP_MAX_KGS_PROXY is None:
            return None
        try:
            pct = 100.0 * float(f) / float(CHW_PUMP_MAX_KGS_PROXY)
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    if disp == "CHW VFD Output (Hz)":
        sp = computed_value("CHW Pump 1 Speed (%)")
        if sp is None:
            return None
        try:
            hz = 60.0 * float(sp) / 100.0
            return max(0.0, min(60.0, hz))
        except Exception:
            return None

    if disp == "CHW VFD Alarm":
        return "NORMAL"

    # Second CHW pump is dummy for now
    if disp == "CHW Pump 2 Enable":
        return "OFF"
    if disp == "CHW Pump 2 Status":
        return "OFF"
    if disp == "CHW Pump 2 Speed (%)":
        return 0.0
    if disp == "CHW2 VFD Output (Hz)":
        return 0.0
    if disp == "CHW2 VFD Alarm":
        return "NORMAL"

    # Combined zone setpoints in ONE box (two lines)
    if disp == "Zone Setpoints (H/C)":
        h = v("Zone Heating Setpoint")
        c = v("Zone Cooling Setpoint")
        if h is None or c is None:
            return None
        if (isinstance(h, float) and pd.isna(h)) or (isinstance(c, float) and pd.isna(c)):
            return None
        try:
            return f"H: {float(h):.1f}°C<br>C: {float(c):.1f}°C"
        except Exception:
            return None

    return None


# ============================================================
# 8) Manual tag layouts
# ============================================================
AHU_LAYOUT = [
    {"disp": "OA Temp", "left": "1.5%", "top": "41.5%"},
    {"disp": "Return Air Temp", "left": "16%", "top": "33%"},
    {"disp": "Mixed Air Temp", "left": "37%", "top": "39%"},
    {"disp": "Supply Air Temp", "left": "78%", "top": "39%"},
    {"disp": "Zone Setpoints (H/C)", "left": "78%", "top": "25%"},
    # NEW: dummy safety/status points 
    {"disp": "FreezeStat", "left": "80%", "top": "2%"},
    {"disp": "Pressure Switch", "left": "67%", "top": "2%"},
    # NEW: fan VFD-style proxy points
    {"disp": "Supply Fan Speed (%)", "left": "60%", "top": "72%"},
    {"disp": "Supply Fan VFD Output (Hz)", "left": "60%", "top": "81%"},
    {"disp": "Supply Fan VFD Alarm", "left": "60%", "top": "90%"},
    #
    {"disp": "OA Damper Position (%)", "left": "17%", "top": "72%"},
    {"disp": "Return Damper Position (%)", "left": "15%", "top": "21%"},
    {"disp": "CHW Valve Position (%)", "left": "63%", "top": "28%"},
    {"disp": "HW Valve Position (%)", "left": "49%", "top": "28%"},
]

HW_LAYOUT = [
    {"disp": "HW SUPP TEMP", "left": "44%", "top": "9%"},
    {"disp": "HW SUPP SETPNT", "left": "44%", "top": "0%"},
    {"disp": "HW RTN TEMP", "left": "44%", "top": "77%"},
    {"disp": "Boiler 1 Status", "left": "43%", "top": "36%"},
    {"disp": "Boiler 2 Status", "left": "58%", "top": "84%"},
    # Pump 3 (real)
    {"disp": "Pump 3 Status", "left": "30%", "top": "32%"},
    {"disp": "Pump 3 Flow", "left": "30%", "top": "42%"},
    {"disp": "HW Pump 3 Speed (%)", "left": "30%", "top": "52%"},
    {"disp": "HW Pump 3 VFD Output (Hz)", "left": "30%", "top": "62%"},
    {"disp": "HW Pump 3 VFD Alarm", "left": "30%", "top": "72%"},
    # Pump 4 (dummy)
    {"disp": "Pump 4 Status", "left": "30%", "top": "90%"},
    {"disp": "Pump 4 Flow", "left": "30%", "top": "95%"},
    {"disp": "HW Pump 4 Speed (%)", "left": "30%", "top": "100%"},
    {"disp": "HW Pump 4 VFD Output (Hz)", "left": "30%", "top": "105%"},
    {"disp": "HW Pump 4 VFD Alarm", "left": "30%", "top": "110%"},
]

CHW_LAYOUT = [
    {"disp": "CHW Flow Meter (L/s)", "left": "68%", "top": "2%"},
    {"disp": "CHW SUPP SETPNT", "left": "52%", "top": "1%"},
    {"disp": "CHW SUPP TEMP", "left": "52%", "top": "10%"},
    {"disp": "CHW RTN TEMP", "left": "53%", "top": "64%"},
    # BYPASS (new)
    {"disp": "CHW Supply Bypass Flow", "left": "70%", "top": "20%"},
    {"disp": "CHW Supply Bypass (%)", "left": "70%", "top": "28%"},
    {"disp": "CHW Demand Bypass Flow", "left": "70%", "top": "72%"},
    {"disp": "CHW Demand Bypass (%)", "left": "70%", "top": "80%"},
    # Pump 1 table
    {"disp": "CHW Pump 1 Enable", "left": "7%", "top": "36%"},
    {"disp": "CHW Pump 1 Status", "left": "7%", "top": "44%"},
    {"disp": "CHW Pump 1 Speed (%)", "left": "7%", "top": "52%"},
    {"disp": "CHW VFD Output (Hz)", "left": "7%", "top": "60%"},
    {"disp": "CHW VFD Alarm", "left": "7%", "top": "68%"},
    # Pump 2 table (dummy)
    {"disp": "CHW Pump 2 Enable", "left": "7%", "top": "75%"},
    {"disp": "CHW Pump 2 Status", "left": "7%", "top": "83%"},
    {"disp": "CHW Pump 2 Speed (%)", "left": "7%", "top": "91%"},
    {"disp": "CHW2 VFD Output (Hz)", "left": "7%", "top": "99%"},
    {"disp": "CHW2 VFD Alarm", "left": "7%", "top": "107%"},
]


def make_tags(layout):
    def led_from_onoff(state):
        if state == "ON":
            return "led-ok"
        if state == "OFF":
            return "led-off"
        return "led-off"

    def led_class_from_value(disp, val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "led-off"

        # Force HW Pump 4 Flow to look inactive (grey LED)
        if disp == "Pump 4 Flow":
            return "led-off"

        # Strings: treat ON/OFF specially, otherwise OK
        if isinstance(val, str):
            v2 = val.strip().upper()
            if v2 in ("ON", "OFF"):
                return led_from_onoff(v2)
            return "led-ok"

        try:
            x = float(val)
        except Exception:
            return "led-off"

        if "Damper" in disp or "Valve" in disp:
            if x < -1 or x > 101:
                return "led-bad"
            return "led-ok"

        if "Power" in disp or "Elec" in disp:
            if x < 0:
                return "led-bad"
            return "led-ok"

        if "Flow" in disp:
            if x < 0:
                return "led-bad"
            return "led-ok"

        if "Temp" in disp or "Setp" in disp or "SETP" in disp.upper():
            return "led-ok"

        if "Speed" in disp or "Hz" in disp:
            if x < 0:
                return "led-bad"
            return "led-ok"

        if "Bypass (%)" in disp:
            return "led-ok"

        return "led-ok"

    def build_html(label, value_str, unit_str="", led="led-ok"):
        unit_html = f'<span class="unit">{unit_str}</span>' if unit_str else ""
        return (
            f'<div class="label"><span class="led {led}"></span>{label}</div>'
            f'<div class="value">{value_str}{unit_html}</div>'
        )

    tags = []

    computed_points = (
        "FreezeStat",
        "Pressure Switch",
        "OA Damper Position (%)",
        "Return Damper Position (%)",
        "Supply Fan Speed (%)",
        "Supply Fan VFD Output (Hz)",
        "Supply Fan VFD Alarm",
        "CHW Valve Position (%)",
        "HW Valve Position (%)",
        "Boiler 1 Status",
        "Boiler 2 Status",
        "Pump 3 Status",
        "Pump 4 Status",
        "Pump 4 Flow",
        "Zone Setpoints (H/C)",
        # CHW computed points
        "CHW Flow Meter (L/s)",
        "CHW Pump 1 Enable",
        "CHW Pump 1 Status",
        "CHW Pump 1 Speed (%)",
        "CHW VFD Output (Hz)",
        "CHW VFD Alarm",
        "CHW Pump 2 Enable",
        "CHW Pump 2 Status",
        "CHW Pump 2 Speed (%)",
        "CHW2 VFD Output (Hz)",
        "CHW2 VFD Alarm",
        # HW computed pump VFD points
        "HW Pump 3 Speed (%)",
        "HW Pump 3 VFD Output (Hz)",
        "HW Pump 3 VFD Alarm",
        "HW Pump 4 Speed (%)",
        "HW Pump 4 VFD Output (Hz)",
        "HW Pump 4 VFD Alarm",
        # CHW bypass computed points (only % are computed; flow comes from CSV mapping)
        "CHW Supply Bypass (%)",
        "CHW Demand Bypass (%)",
    )

    for item in layout:
        disp = item["disp"]

        # Computed points
        if disp in computed_points:
            comp = computed_value(disp)
            if comp is None:
                html = build_html(disp, "MISSING", "", "led-off")
                cls = "inactive"
            else:
                if disp.endswith("(%)"):
                    led = led_class_from_value(disp, comp)
                    html = build_html(disp, f"{float(comp):.1f}", "%", led)
                elif disp.endswith("(Hz)"):
                    led = led_class_from_value(disp, comp)
                    html = build_html(disp, f"{float(comp):.1f}", "Hz", led)
                elif disp.endswith("(L/s)"):
                    led = led_class_from_value(disp, comp)
                    html = build_html(disp, f"{float(comp):.1f}", "L/s", led)
                else:
                    # Special formatting for HW Pump 4 Flow -> 0.000 kg/s
                    if disp == "Pump 4 Flow":
                        led = led_class_from_value(disp, comp)  # will be led-off
                        html = build_html(disp, f"{float(comp):.3f}", "kg/s", led)
                    else:
                        led = led_class_from_value(disp, comp)
                        html = build_html(disp, str(comp), "", led)
                cls = ""
            tags.append({"html": html, "left": item["left"], "top": item["top"], "class": cls})
            continue

        # CSV-mapped points
        val = v(disp)

        if MAP.get(disp) is None:
            html = build_html(disp, "MISSING", "", "led-off")
            cls = "inactive"
        else:
            led = led_class_from_value(disp, val)
            cls = ""

            # Format by type
            if "SETP" in disp.upper() or "SETPOINT" in disp.upper():
                html = build_html(disp, f"{float(val):.1f}", "°C", led)
            elif "TEMP" in disp.upper() or "Temp" in disp:
                html = build_html(disp, f"{float(val):.1f}", "°C", led)
            elif "Bypass Flow" in disp:
                html = build_html(disp, f"{float(val):.3f}", "kg/s", led)
            elif disp.endswith("Flow"):
                html = build_html(disp, f"{float(val):.3f}", "kg/s", led)
            elif "Energy" in disp:
                html = build_html(disp, f"{float(val):.0f}", "J", led)
            elif "Power" in disp or "Elec" in disp:
                html = build_html(disp, f"{float(val):.0f}", "W", led)
            else:
                try:
                    html = build_html(disp, f"{float(val):.2f}", "", led)
                except Exception:
                    html = build_html(disp, str(val), "", "led-off")

        tags.append({"html": html, "left": item["left"], "top": item["top"], "class": cls})

    return tags


# ============================================================
# 9) Tabs render
# ============================================================
tab_ahu, tab_hw, tab_chw = st.tabs(["AHU", "Hot Water Plant", "Chilled Water Plant"])

with tab_ahu:
 #   st.subheader("AHU")
    st.caption(header_caption())
    render_background_with_tags(ahu_b64, make_tags(AHU_LAYOUT), canvas_width_px=1500, height_px=760)

with tab_hw:
    st.subheader("Hot Water Plant – closest OA match (filtered by Occupied if schedule column exists)")
    st.caption(header_caption())
    render_background_with_tags(hw_b64, make_tags(HW_LAYOUT), canvas_width_px=1500, height_px=900)

with tab_chw:
    st.subheader("Chilled Water Plant – closest OA match (filtered by Occupied if schedule column exists)")
    st.caption(header_caption())
    render_background_with_tags(chw_b64, make_tags(CHW_LAYOUT), canvas_width_px=1500, height_px=900)

# ============================================================
# 10) Verification panel
# ============================================================
with st.expander("🔎 Verify wiring (Displayed point → CSV column) + selected row values"):
    st.write("### Occupancy filter status")
    st.write(f"- Occupancy column found? **{occ_col is not None}**")
    st.write(f"- Filter applied? **{occ_filter_used}**")
    if occ_filter_used:
        st.write(f"- Toggle: **{'Occupied' if occupied_toggle else 'Unoccupied'}**")
        st.write(f"- Selected row Occ value: **{fmt(matched_occ, nd=3)}**")
        st.write(f"- Filtered rows: **{len(df_filt)} / {len(df)}**")

    st.write("### Wiring map (CSV-mapped points)")
    wiring_rows = []
    for disp, actual_col in MAP.items():
        wiring_rows.append(
            {
                "Displayed point": disp,
                "CSV column used": actual_col if actual_col is not None else "MISSING",
                "Exists?": actual_col is not None,
            }
        )
    st.dataframe(pd.DataFrame(wiring_rows), use_container_width=True)

    st.write("### Values from selected row (CSV-mapped points)")
    values_rows = []
    for disp, actual_col in MAP.items():
        values_rows.append({"Displayed point": disp, "Value": row[actual_col] if actual_col is not None else "MISSING"})
    st.dataframe(pd.DataFrame(values_rows), use_container_width=True)

    st.write("### Computed points")
    st.write(
        {
            "FreezeStat": computed_value("FreezeStat"),
            "Pressure Switch": computed_value("Pressure Switch"),
            "OA Damper Position (%)": computed_value("OA Damper Position (%)"),
            "Return Damper Position (%)": computed_value("Return Damper Position (%)"),
            "Supply Fan Speed (%)": computed_value("Supply Fan Speed (%)"),
            "Supply Fan VFD Output (Hz)": computed_value("Supply Fan VFD Output (Hz)"),
            "Supply Fan VFD Alarm": computed_value("Supply Fan VFD Alarm"),
            "CHW Valve Position (%)": computed_value("CHW Valve Position (%)"),
            "HW Valve Position (%)": computed_value("HW Valve Position (%)"),
            "Boiler 1 Status": computed_value("Boiler 1 Status"),
            "Boiler 2 Status": computed_value("Boiler 2 Status"),
            "Pump 3 Status": computed_value("Pump 3 Status"),
            "Pump 4 Status": computed_value("Pump 4 Status"),
            "Pump 4 Flow": computed_value("Pump 4 Flow"),
            "Zone Setpoints (H/C)": computed_value("Zone Setpoints (H/C)"),
            "CHW Supply Bypass (%)": computed_value("CHW Supply Bypass (%)"),
            "CHW Demand Bypass (%)": computed_value("CHW Demand Bypass (%)"),
            "FAN_MAX_KGS_PROXY used": FAN_MAX_KGS_PROXY,
            "CHW_PUMP_MAX_KGS_PROXY used": CHW_PUMP_MAX_KGS_PROXY,
            "HW_PUMP3_MAX_KGS_PROXY used": HW_PUMP3_MAX_KGS_PROXY,
            "FAN_MAX_M3S used (OA only)": FAN_MAX_M3S,
        }
    )

st.caption("If you don’t see images: make sure the .svg files are in the same folder you run Streamlit from.")
