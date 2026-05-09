"""
Destination Geofence Health Monitor
Identifies incorrectly placed destination geofences from TL shipment tracking data.

Run with:  streamlit run geofence_health_monitor.py
Requires:  pip install streamlit pandas plotly
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Destination Geofence Health Monitor",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── THEME: clean light styling that works everywhere ──────────────────────────
st.markdown("""
<style>
    /* Header banner */
    .app-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
        color: white; padding: 22px 28px; border-radius: 12px;
        margin-bottom: 24px;
    }
    .app-header h1 { margin: 0; font-size: 22px; font-weight: 800; color: white; }
    .app-header p  { margin: 6px 0 0 0; font-size: 13px; opacity: 0.85; color: white; }

    /* Section labels */
    .section-label {
        font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 1px; color: #64748b;
        padding-bottom: 8px; border-bottom: 2px solid #e2e8f0;
        margin: 28px 0 16px 0;
    }

    /* Insight box */
    .insight-box {
        background: #eff6ff; border: 1px solid #bfdbfe;
        border-left: 4px solid #2563eb; border-radius: 8px;
        padding: 14px 18px; font-size: 14px; line-height: 1.7;
        color: #1e3a5f; margin: 16px 0;
    }
    .insight-box strong { color: #1d4ed8; }

    /* Warning insight */
    .insight-box-warn {
        background: #fff7ed; border: 1px solid #fed7aa;
        border-left: 4px solid #f97316; border-radius: 8px;
        padding: 14px 18px; font-size: 14px; line-height: 1.7;
        color: #431407; margin: 16px 0;
    }
    .insight-box-warn strong { color: #c2410c; }

    /* Upload landing */
    .upload-landing {
        text-align: center; padding: 80px 20px;
    }
    .upload-landing h2 { color: #1e293b; margin-bottom: 10px; }
    .upload-landing p  { color: #64748b; font-size: 15px; max-width: 480px; margin: 0 auto; }

    /* Priority badge */
    .badge-critical { background:#fee2e2; color:#b91c1c; padding:2px 10px;
        border-radius:12px; font-size:11px; font-weight:700; }
    .badge-high { background:#fef3c7; color:#b45309; padding:2px 10px;
        border-radius:12px; font-size:11px; font-weight:700; }
    .badge-medium { background:#dbeafe; color:#1d4ed8; padding:2px 10px;
        border-radius:12px; font-size:11px; font-weight:700; }

    /* Make Streamlit metrics look cleaner */
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="stMetricLabel"] { font-size: 12px !important; color: #64748b !important; }
    [data-testid="stMetricValue"] { color: #0f172a !important; }
</style>
""", unsafe_allow_html=True)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
COUNTRY_NAMES = {
    "DE": "Germany",    "SK": "Slovakia",  "IE": "Ireland",  "IT": "Italy",
    "GB": "UK",         "ES": "Spain",     "PL": "Poland",   "CZ": "Czechia",
    "LU": "Luxembourg", "HU": "Hungary",   "PT": "Portugal", "RO": "Romania",
    "NL": "Netherlands","FR": "France",    "SI": "Slovenia", "AT": "Austria",
    "BE": "Belgium",    "SE": "Sweden",    "DK": "Denmark",  "FI": "Finland",
    "NO": "Norway",     "RS": "Serbia",    "HR": "Croatia",  "BG": "Bulgaria",
}

PLOTLY_LIGHT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font_color="#374151",
    font_size=12,
)

BLUE_SCALE  = ["#dbeafe", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a5f"]
GAP_COLORS  = {
    "< 24h (plate change?)":    "#22c55e",
    "24–72h (borderline)":      "#f59e0b",
    "72–168h (likely geofence)":"#f97316",
    "> 168h (bad geofence)":    "#dc2626",
}


# ── DATA LOADING ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data(raw_bytes: bytes) -> pd.DataFrame:
    text = raw_bytes.decode("utf-8-sig")
    df = pd.read_csv(StringIO(text))
    df.columns = df.columns.str.strip().str.upper()

    for col in ["OUTER_GEOFENCE_TIMESTAMP", "TIMED_OUT_TIMESTAMP"]:
        if col not in df.columns:
            continue
        df[col] = (
            df[col].astype(str)
            .str.replace(" Z", "", regex=False)
            .str.replace("T", " ", regex=False)
        )
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    df["GAP_HOURS"] = (
        (df["TIMED_OUT_TIMESTAMP"] - df["OUTER_GEOFENCE_TIMESTAMP"])
        .dt.total_seconds() / 3600
    ).round(1)

    df["OUTER_WEEK"]         = df["OUTER_GEOFENCE_TIMESTAMP"].dt.strftime("W%V")
    df["DESTINATION_NAME"]   = df["DESTINATION_NAME"].astype(str).str.strip()
    df["DESTINATION_ADDRESS"]= df["DESTINATION_ADDRESS"].astype(str).str.strip()
    df["DEST_KEY"]           = df["DESTINATION_NAME"] + "||" + df["DESTINATION_ADDRESS"]
    df["BOL_PREFIX"]         = df["BILL_OF_LADING"].astype(str).str[:2]
    df["DESTINATION_COUNTRY"]= df["DESTINATION_COUNTRY"].astype(str).str.strip().str.upper()
    df["COUNTRY_LABEL"]      = df["DESTINATION_COUNTRY"].apply(
        lambda c: f"{c} — {COUNTRY_NAMES.get(c, c)}"
    )
    dest_counts              = df["DEST_KEY"].value_counts()
    df["DEST_COUNT"]         = df["DEST_KEY"].map(dest_counts)
    df["GAP_CAT"]            = df["GAP_HOURS"].apply(gap_category)

    return df


def gap_category(hours) -> str:
    if pd.isna(hours):          return "Unknown"
    if hours < 24:              return "< 24h (plate change?)"
    if hours < 72:              return "24–72h (borderline)"
    if hours < 168:             return "72–168h (likely geofence)"
    return "> 168h (bad geofence)"


def priority_tag(count: int) -> str:
    if count >= 20:  return "🔴 CRITICAL"
    if count >= 8:   return "🟡 HIGH"
    return "🔵 MEDIUM"


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📍 Geofence Health Monitor")
    st.caption(
        "Upload a CSV export of shipments that triggered the outer geofence "
        "(50 km radius) but never received the final geofence / arrival milestone."
    )
    st.divider()

    uploaded_file = st.file_uploader(
        "Upload CSV Export",
        type=["csv"],
        help="Expected columns: BILL_OF_LADING, OUTER_GEOFENCE_TIMESTAMP, "
             "TIMED_OUT_TIMESTAMP, DESTINATION_NAME, DESTINATION_COUNTRY, "
             "DESTINATION_CITY, DESTINATION_ADDRESS, DESTINATION_POSTAL_CODE",
    )

    st.divider()

    if uploaded_file:
        st.markdown("#### ⚙️ Filters")
        time_range_options = ["All time", "Last 30 days", "Last 60 days", "Last 90 days"]
        selected_time = st.selectbox("Time Range", time_range_options)

        country_placeholder = st.empty()

        dest_type_filter = st.radio(
            "Destination Type",
            ["All", "Repeat only (geofence issue)", "Single only (plate change?)"],
        )
        gap_filter = st.multiselect(
            "Gap Category (Outer → Timeout)",
            list(GAP_COLORS.keys()),
            placeholder="All categories",
        )
        bol_search = st.text_input("Search BOL / Destination", placeholder="e.g. 4220463559")

    st.divider()
    st.caption("All processing happens in-session. No data is stored or transmitted.")


# ── LANDING PAGE (no file) ────────────────────────────────────────────────────
if not uploaded_file:
    st.markdown("""
    <div class="app-header">
        <h1>📍 Destination Geofence Health Monitor</h1>
        <p>Identify incorrectly placed destination geofences from TL shipment tracking data</p>
    </div>
    """, unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info("**What this tool does**\n\nFinds shipments that entered the 50km outer geofence at the destination but never triggered the final geofence — a strong indicator of a misplaced destination geofence.")
    with col_b:
        st.info("**How to use it**\n\nExport the geofence query results from Snowflake as CSV and upload using the sidebar. All analysis runs instantly in the browser.")
    with col_c:
        st.info("**What you'll get**\n\nA ranked list of destination geofences to fix, geographic breakdown, time-gap analysis, and a downloadable priority action list.")
    st.stop()


# ── LOAD DATA ─────────────────────────────────────────────────────────────────
df_raw = load_data(uploaded_file.read())
df = df_raw.copy()

# Time filter
if selected_time != "All time":
    days_map = {"Last 30 days": 30, "Last 60 days": 60, "Last 90 days": 90}
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_map[selected_time])
    df = df[df["OUTER_GEOFENCE_TIMESTAMP"] >= cutoff]

# Country filter (dynamic)
all_countries = sorted(df["DESTINATION_COUNTRY"].dropna().unique())
country_labels = {c: f"{c} — {COUNTRY_NAMES.get(c, c)}" for c in all_countries}
with st.sidebar:
    selected_countries = country_placeholder.multiselect(
        "Destination Country",
        options=list(country_labels.values()),
        placeholder="All countries",
    )
if selected_countries:
    codes = [c for c, lbl in country_labels.items() if lbl in selected_countries]
    df = df[df["DESTINATION_COUNTRY"].isin(codes)]

# Destination type filter
if dest_type_filter == "Repeat only (geofence issue)":
    df = df[df["DEST_COUNT"] > 1]
elif dest_type_filter == "Single only (plate change?)":
    df = df[df["DEST_COUNT"] == 1]

# Gap filter
if gap_filter:
    df = df[df["GAP_CAT"].isin(gap_filter)]

# BOL / destination search
if bol_search.strip():
    q = bol_search.strip()
    df = df[
        df["BILL_OF_LADING"].astype(str).str.contains(q, case=False, na=False)
        | df["DESTINATION_NAME"].str.contains(q, case=False, na=False)
        | df["DESTINATION_CITY"].astype(str).str.contains(q, case=False, na=False)
    ]

total = len(df)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📍 Destination Geofence Health Monitor</h1>
    <p>Shipments that triggered the 50 km outer geofence but never reached the final destination geofence — indicating an incorrectly placed geofence</p>
</div>
""", unsafe_allow_html=True)

if total == 0:
    st.warning("No shipments match the current filters. Try adjusting the sidebar.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Summary</div>', unsafe_allow_html=True)

repeat_df     = df[df["DEST_COUNT"] > 1]
repeat_dests  = df[df["DEST_COUNT"] > 1]["DEST_KEY"].nunique()
repeat_ships  = len(repeat_df)
avg_gap       = df["GAP_HOURS"].mean()
max_gap       = df["GAP_HOURS"].max()

top5_keys = (
    df[df["DEST_COUNT"] > 1].groupby("DEST_KEY").size().nlargest(5).index
)
top5_count = df[df["DEST_KEY"].isin(top5_keys)].shape[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Total Shipments",
    f"{total:,}",
    help="Shipments with outer geofence event but no final geofence / arrival",
)
c2.metric(
    "Repeat Destinations",
    f"{repeat_dests:,}",
    delta=f"{repeat_ships:,} shipments ({round(repeat_ships/total*100)}%)",
    delta_color="inverse",
    help="Same destination appears multiple times = likely misplaced geofence",
)
c3.metric(
    "Countries Affected",
    df["DESTINATION_COUNTRY"].nunique(),
    help=f"{df['DESTINATION_NAME'].nunique()} unique destination names",
)
c4.metric(
    "Avg Gap (Outer → Timeout)",
    f"{avg_gap:.0f} h",
    delta=f"max {max_gap:.0f} h",
    delta_color="off",
    help="Time between outer geofence trigger and tracking timeout",
)
c5.metric(
    "Fix Top 5 → Resolves",
    f"{top5_count:,} shipments",
    delta=f"{round(top5_count/total*100)}% of all cases",
    help="Fixing just the 5 worst geofences eliminates this many incidents",
)

# ── INSIGHT BANNER ────────────────────────────────────────────────────────────
if repeat_ships > 0:
    top_entry = (
        df[df["DEST_COUNT"] > 1]
        .groupby(["DESTINATION_NAME", "DEST_KEY"])
        .size()
        .idxmax()
    )
    top_name  = top_entry[0]
    top_count = df[df["DEST_KEY"] == top_entry[1]].shape[0]

    st.markdown(f"""
    <div class="insight-box">
        📌 <strong>{round(repeat_ships/total*100)}% of all cases</strong> involve the
        same destination address appearing multiple times — this is a
        <strong>geofence placement problem</strong>, not random truck plate changes.
        The highest-frequency location is <strong>{top_name}</strong>
        with <strong>{top_count} incidents</strong>.
        Fixing the top 5 geofences alone resolves
        <strong>{round(top5_count/total*100)}% of all cases</strong>.
    </div>
    """, unsafe_allow_html=True)

# ── CHARTS ROW 1 ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Geographic & Time Analysis</div>',
            unsafe_allow_html=True)

col_l, col_r = st.columns([3, 2])

with col_l:
    country_counts = (
        df.groupby(["DESTINATION_COUNTRY", "COUNTRY_LABEL"])
        .size().reset_index(name="Shipments")
        .sort_values("Shipments", ascending=True)
    )
    fig_country = px.bar(
        country_counts, x="Shipments", y="COUNTRY_LABEL", orientation="h",
        title="Shipments by Destination Country",
        color="Shipments", color_continuous_scale=BLUE_SCALE,
        labels={"COUNTRY_LABEL": ""},
    )
    fig_country.update_layout(
        **PLOTLY_LIGHT, height=380, title_font_size=13,
        coloraxis_showscale=False,
        margin=dict(l=0, r=10, t=40, b=0),
        yaxis=dict(gridcolor="#f1f5f9"),
        xaxis=dict(gridcolor="#f1f5f9"),
    )
    fig_country.update_traces(marker_line_width=0)
    st.plotly_chart(fig_country, use_container_width=True)

with col_r:
    gap_order = list(GAP_COLORS.keys())
    gap_counts = df["GAP_CAT"].value_counts().reindex(gap_order, fill_value=0).reset_index()
    gap_counts.columns = ["Category", "Count"]

    fig_gap = px.pie(
        gap_counts, values="Count", names="Category",
        title="Time Gap Distribution",
        color="Category", color_discrete_map=GAP_COLORS,
        hole=0.45,
    )
    fig_gap.update_layout(
        **PLOTLY_LIGHT, height=380, title_font_size=13,
        legend=dict(orientation="v", x=1.02, y=0.5, font_size=11),
        margin=dict(l=0, r=140, t=40, b=0),
    )
    fig_gap.update_traces(
        textposition="inside", textinfo="percent+value",
        insidetextfont=dict(size=11, color="white"),
    )
    st.plotly_chart(fig_gap, use_container_width=True)

# ── CHARTS ROW 2 ──────────────────────────────────────────────────────────────
col2a, col2b, col2c = st.columns(3)

with col2a:
    weekly = (
        df.dropna(subset=["OUTER_WEEK"])
        .groupby("OUTER_WEEK").size()
        .reset_index(name="Shipments")
        .sort_values("OUTER_WEEK")
    )
    fig_weekly = px.line(
        weekly, x="OUTER_WEEK", y="Shipments",
        title="Weekly Volume Trend", markers=True,
        labels={"OUTER_WEEK": "Week"},
        color_discrete_sequence=["#2563eb"],
    )
    fig_weekly.update_traces(
        fill="tozeroy", fillcolor="rgba(37,99,235,0.08)", line_width=2.5,
        marker_size=6,
    )
    fig_weekly.update_layout(
        **PLOTLY_LIGHT, height=280, title_font_size=13,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(gridcolor="#f1f5f9"),
        yaxis=dict(gridcolor="#f1f5f9"),
    )
    st.plotly_chart(fig_weekly, use_container_width=True)

with col2b:
    bol_df = df["BOL_PREFIX"].value_counts().reset_index()
    bol_df.columns = ["Prefix", "Count"]
    bol_df["Label"] = "BOL " + bol_df["Prefix"] + "xxx"
    fig_bol = px.pie(
        bol_df, values="Count", names="Label",
        title="BOL Series Breakdown",
        color_discrete_sequence=["#2563eb","#3b82f6","#60a5fa","#93c5fd","#bfdbfe","#dbeafe"],
        hole=0.4,
    )
    fig_bol.update_layout(
        **PLOTLY_LIGHT, height=280, title_font_size=13,
        legend=dict(orientation="v", x=1.02, y=0.5, font_size=10),
        margin=dict(l=0, r=110, t=40, b=0),
    )
    fig_bol.update_traces(textposition="inside", textinfo="percent",
                          insidetextfont=dict(size=11, color="white"))
    st.plotly_chart(fig_bol, use_container_width=True)

with col2c:
    repeat_count = len(df[df["DEST_COUNT"] > 1])
    single_count = len(df[df["DEST_COUNT"] == 1])
    fig_repeat = go.Figure(go.Pie(
        labels=["Repeat (geofence issue)", "Single (plate change?)"],
        values=[repeat_count, single_count],
        hole=0.45,
        marker_colors=["#dc2626", "#2563eb"],
    ))
    fig_repeat.update_traces(
        textposition="inside", textinfo="percent",
        insidetextfont=dict(size=12, color="white"),
    )
    fig_repeat.update_layout(
        **PLOTLY_LIGHT, title="Repeat vs Single Destinations", title_font_size=13,
        height=280,
        legend=dict(orientation="h", x=0.5, y=-0.15, xanchor="center", font_size=11),
        margin=dict(l=0, r=0, t=40, b=40),
    )
    st.plotly_chart(fig_repeat, use_container_width=True)

# ── PRIORITY TABLE ────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">🎯 Geofence Remediation Priority List</div>',
            unsafe_allow_html=True)

st.markdown("""
<div class="insight-box-warn">
    Destinations appearing <strong>multiple times</strong> have an incorrectly placed geofence —
    the truck repeatedly enters the 50 km outer zone but the final geofence is never triggered.
    Address these in priority order for maximum impact.
</div>
""", unsafe_allow_html=True)

priority_df = (
    df[df["DEST_COUNT"] > 1]
    .groupby(["DESTINATION_NAME", "DESTINATION_COUNTRY", "DESTINATION_CITY", "DESTINATION_ADDRESS"])
    .agg(
        Occurrences=("BILL_OF_LADING", "count"),
        Avg_Gap_h=("GAP_HOURS", "mean"),
        Max_Gap_h=("GAP_HOURS", "max"),
    )
    .reset_index()
    .sort_values("Occurrences", ascending=False)
    .reset_index(drop=True)
)
priority_df.index += 1
priority_df["% of Total"] = (priority_df["Occurrences"] / total * 100).round(1).astype(str) + "%"
priority_df["Priority"]   = priority_df["Occurrences"].apply(priority_tag)
priority_df["Avg Gap"]    = priority_df["Avg_Gap_h"].apply(lambda x: f"{x:.0f} h")
priority_df["Max Gap"]    = priority_df["Max_Gap_h"].apply(lambda x: f"{x:.0f} h")
priority_df["Country"]    = priority_df["DESTINATION_COUNTRY"].apply(
    lambda c: f"{c} — {COUNTRY_NAMES.get(c, c)}"
)

display_priority = priority_df.rename(columns={
    "DESTINATION_NAME":    "Destination",
    "DESTINATION_CITY":    "City",
    "DESTINATION_ADDRESS": "Address",
})[["Destination", "Country", "City", "Address", "Occurrences", "% of Total", "Avg Gap", "Max Gap", "Priority"]]

max_occ = int(priority_df["Occurrences"].max())
st.dataframe(
    display_priority,
    use_container_width=True,
    height=420,
    column_config={
        "Occurrences": st.column_config.ProgressColumn(
            "Occurrences", min_value=0, max_value=max_occ, format="%d",
        ),
        "Priority": st.column_config.TextColumn("Priority", width="small"),
    },
)

dl1, dl2, _ = st.columns([1, 1, 4])
with dl1:
    st.download_button(
        "⬇ Download Priority List",
        data=display_priority.to_csv(index=True).encode("utf-8"),
        file_name="geofence_priority_list.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── ALL SHIPMENTS TABLE ───────────────────────────────────────────────────────
st.markdown('<div class="section-label">All Shipments</div>', unsafe_allow_html=True)

fc1, fc2, fc3 = st.columns([3, 2, 1])
with fc1:
    table_search = st.text_input(
        "search", label_visibility="collapsed",
        placeholder="🔍  Filter by BOL, destination, city…",
    )
with fc2:
    sort_option = st.selectbox(
        "sort", label_visibility="collapsed",
        options=["Outer Geofence ↓ (newest first)", "Gap ↓ (longest first)",
                 "Gap ↑ (shortest first)", "Country A–Z", "Destination A–Z"],
    )
with fc3:
    st.download_button(
        "⬇ Export",
        data=df.drop(columns=["DEST_KEY","OUTER_WEEK","BOL_PREFIX",
                               "DEST_COUNT","GAP_CAT","COUNTRY_LABEL"], errors="ignore")
              .to_csv(index=False).encode("utf-8"),
        file_name="geofence_shipments.csv",
        mime="text/csv",
        use_container_width=True,
    )

table_df = df.copy()
if table_search.strip():
    q = table_search.strip()
    mask = (
        table_df["BILL_OF_LADING"].astype(str).str.contains(q, case=False, na=False)
        | table_df["DESTINATION_NAME"].str.contains(q, case=False, na=False)
        | table_df["DESTINATION_CITY"].astype(str).str.contains(q, case=False, na=False)
        | table_df["DESTINATION_ADDRESS"].str.contains(q, case=False, na=False)
    )
    table_df = table_df[mask]

sort_map = {
    "Outer Geofence ↓ (newest first)": ("OUTER_GEOFENCE_TIMESTAMP", False),
    "Gap ↓ (longest first)":           ("GAP_HOURS", False),
    "Gap ↑ (shortest first)":          ("GAP_HOURS", True),
    "Country A–Z":                      ("DESTINATION_COUNTRY", True),
    "Destination A–Z":                  ("DESTINATION_NAME", True),
}
sort_col, sort_asc = sort_map[sort_option]
table_df = table_df.sort_values(sort_col, ascending=sort_asc)

st.caption(
    f"Showing **{len(table_df):,}** of **{total:,}** shipments  |  "
    "Gap colour: 🟢 <24 h · 🟡 24–72 h · 🟠 72–168 h · 🔴 >168 h"
)

display_df = table_df[[
    "BILL_OF_LADING", "OUTER_GEOFENCE_TIMESTAMP", "TIMED_OUT_TIMESTAMP",
    "GAP_HOURS", "DESTINATION_NAME", "DESTINATION_CITY",
    "DESTINATION_COUNTRY", "DESTINATION_POSTAL_CODE", "DESTINATION_ADDRESS",
]].rename(columns={
    "BILL_OF_LADING":            "BOL",
    "OUTER_GEOFENCE_TIMESTAMP":  "Outer Geofence (UTC)",
    "TIMED_OUT_TIMESTAMP":       "Timed Out (UTC)",
    "GAP_HOURS":                 "Gap (h)",
    "DESTINATION_NAME":          "Destination",
    "DESTINATION_CITY":          "City",
    "DESTINATION_COUNTRY":       "Country",
    "DESTINATION_POSTAL_CODE":   "Postal Code",
    "DESTINATION_ADDRESS":       "Address",
})

st.dataframe(
    display_df,
    use_container_width=True,
    height=480,
    hide_index=True,
    column_config={
        "BOL":                   st.column_config.TextColumn(width="small"),
        "Outer Geofence (UTC)":  st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Timed Out (UTC)":       st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Gap (h)":               st.column_config.NumberColumn(format="%.0f h"),
        "Country":               st.column_config.TextColumn(width="small"),
        "Postal Code":           st.column_config.TextColumn(width="small"),
    },
)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "📍 Destination Geofence Health Monitor  ·  "
    "Outer geofence = 50 km radius around stop  ·  "
    "Final geofence = ENTERED_FINAL_GEOFENCE event  ·  "
    "Shipments included only if TIMED_OUT (tracking window closed)"
)
