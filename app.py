"""
Bridgestone EU — Missed M3 Arrival Dashboard
Run with: streamlit run bridgestone_dashboard_app.py
Requires: pip install streamlit pandas plotly
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Final Mile Geofence Validator",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f172a; }
    [data-testid="stSidebar"] { background-color: #1e293b; }
    .metric-card {
        background: #1e293b; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px; padding: 20px 24px; text-align: center;
    }
    .metric-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; color: #94a3b8; margin-bottom: 6px; }
    .metric-value { font-size: 38px; font-weight: 800; line-height: 1.1; }
    .metric-sub { font-size: 12px; color: #64748b; margin-top: 4px; }
    .red { color: #e30613; }
    .yellow { color: #f59e0b; }
    .blue { color: #3b82f6; }
    .green { color: #22c55e; }
    .insight-box {
        background: rgba(227,6,19,0.08); border: 1px solid rgba(227,6,19,0.25);
        border-left: 4px solid #e30613; border-radius: 10px;
        padding: 16px 20px; margin: 16px 0; font-size: 14px; line-height: 1.6;
    }
    .section-title {
        font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 1px; color: #64748b; margin: 32px 0 16px 0;
        padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .priority-critical { color: #ff6b6b; font-weight: 700; }
    .priority-high { color: #fbbf24; font-weight: 700; }
    .priority-medium { color: #60a5fa; font-weight: 600; }
    div[data-testid="stMetric"] {
        background: #1e293b; border-radius: 12px; padding: 16px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .stDownloadButton button {
        background: rgba(34,197,94,0.15) !important;
        border: 1px solid rgba(34,197,94,0.4) !important;
        color: #22c55e !important;
    }
</style>
""", unsafe_allow_html=True)

COUNTRY_NAMES = {
    "DE": "Germany", "SK": "Slovakia", "IE": "Ireland", "IT": "Italy",
    "GB": "UK", "ES": "Spain", "PL": "Poland", "CZ": "Czechia",
    "LU": "Luxembourg", "HU": "Hungary", "PT": "Portugal", "RO": "Romania",
    "NL": "Netherlands", "FR": "France", "SI": "Slovenia", "AT": "Austria",
    "BE": "Belgium", "SE": "Sweden", "DK": "Denmark", "FI": "Finland",
}

PLOTLY_THEME = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#94a3b8",
    font_size=12,
)

# ── DATA LOADING ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data(raw_bytes: bytes) -> pd.DataFrame:
    text = raw_bytes.decode("utf-8-sig")
    df = pd.read_csv(StringIO(text))
    df.columns = df.columns.str.strip().str.upper()

    for col in ["OUTER_GEOFENCE_TIMESTAMP", "TIMED_OUT_TIMESTAMP"]:
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

    df["OUTER_WEEK"] = df["OUTER_GEOFENCE_TIMESTAMP"].dt.strftime("W%V")
    df["DEST_KEY"] = df["DESTINATION_NAME"].str.strip() + "||" + df["DESTINATION_ADDRESS"].str.strip()
    df["BOL_PREFIX"] = df["BILL_OF_LADING"].astype(str).str[:2]
    df["DESTINATION_COUNTRY"] = df["DESTINATION_COUNTRY"].str.strip().str.upper()
    df["COUNTRY_LABEL"] = df["DESTINATION_COUNTRY"].map(
        lambda c: f"{c} — {COUNTRY_NAMES.get(c, c)}"
    )

    # Repeat occurrence count per destination
    dest_counts = df["DEST_KEY"].value_counts()
    df["DEST_COUNT"] = df["DEST_KEY"].map(dest_counts)

    return df


def priority_tag(count: int) -> str:
    if count >= 20:
        return "🔴 CRITICAL"
    elif count >= 8:
        return "🟡 HIGH"
    else:
        return "🔵 MEDIUM"


def gap_category(hours):
    if pd.isna(hours):
        return "Unknown"
    if hours < 24:
        return "< 24h (plate change?)"
    elif hours < 72:
        return "24–72h (borderline)"
    elif hours < 168:
        return "72–168h (7 days)"
    else:
        return "> 168h (bad geofence)"


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚛 Bridgestone EU")
    st.markdown("**Missed M3 Arrival Dashboard**")
    st.divider()

    uploaded_file = st.file_uploader(
        "Upload Snowflake CSV Export",
        type=["csv"],
        help="Export from the Bridgestone EU geofence query in Snowflake",
    )

    st.divider()

    if uploaded_file:
        st.markdown("### ⚙️ Filters")

        # Placeholder — populated after data load
        time_range_options = ["All time", "Last 30 days", "Last 60 days", "Last 90 days"]
        selected_time = st.selectbox("Time Range", time_range_options)

        country_placeholder = st.empty()
        dest_type_filter = st.radio(
            "Destination Type",
            ["All", "Repeat only (geofence issue)", "Single only (plate change?)"],
            index=0,
        )
        gap_filter = st.multiselect(
            "Gap Category",
            ["< 24h (plate change?)", "24–72h (borderline)", "72–168h (7 days)", "> 168h (bad geofence)"],
            default=[],
            placeholder="All categories",
        )
        bol_search = st.text_input("Search BOL", placeholder="e.g. 4220463559")

    st.divider()
    st.caption("Data is processed locally in your browser. Nothing is uploaded to any server.")


# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
if not uploaded_file:
    st.markdown("""
    <div style='text-align:center; padding: 80px 20px;'>
        <div style='font-size:64px; margin-bottom:24px;'>📂</div>
        <h2 style='color:#e2e8f0; margin-bottom:12px;'>Upload your Snowflake export to get started</h2>
        <p style='color:#64748b; font-size:15px; max-width:500px; margin:0 auto;'>
            Upload the CSV exported from the Bridgestone EU geofence query.<br>
            All analysis runs locally — no data leaves your machine.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── LOAD & FILTER DATA ────────────────────────────────────────────────────────
df_raw = load_data(uploaded_file.read())
df = df_raw.copy()

# Apply time filter
if selected_time != "All time":
    days = {"Last 30 days": 30, "Last 60 days": 60, "Last 90 days": 90}[selected_time]
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    df = df[df["OUTER_GEOFENCE_TIMESTAMP"] >= cutoff]

# Country filter (built dynamically after data load)
all_countries = sorted(df["DESTINATION_COUNTRY"].dropna().unique())
country_labels = {c: f"{c} — {COUNTRY_NAMES.get(c, c)}" for c in all_countries}
with st.sidebar:
    selected_countries = country_placeholder.multiselect(
        "Destination Country",
        options=list(country_labels.values()),
        default=[],
        placeholder="All countries",
    )
if selected_countries:
    selected_codes = [c for c, label in country_labels.items() if label in selected_countries]
    df = df[df["DESTINATION_COUNTRY"].isin(selected_codes)]

# Destination type filter
if dest_type_filter == "Repeat only (geofence issue)":
    df = df[df["DEST_COUNT"] > 1]
elif dest_type_filter == "Single only (plate change?)":
    df = df[df["DEST_COUNT"] == 1]

# Gap category filter
if gap_filter:
    df["GAP_CAT"] = df["GAP_HOURS"].apply(gap_category)
    df = df[df["GAP_CAT"].isin(gap_filter)]

# BOL search
if bol_search.strip():
    df = df[df["BILL_OF_LADING"].astype(str).str.contains(bol_search.strip(), case=False, na=False)]

total = len(df)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='background: linear-gradient(135deg, #e30613, #8b0000); padding: 24px 28px;
     border-radius: 12px; margin-bottom: 28px;'>
    <h1 style='margin:0; font-size:22px; font-weight:800;'>
        🚛 Bridgestone EU — Outer Geofence Without M3 Arrival
    </h1>
    <p style='margin:6px 0 0 0; opacity:0.85; font-size:13px;'>
        Completed shipments that triggered the 50km outer geofence but never received
        the arrival at destination (ENTERED_FINAL_GEOFENCE) milestone
    </p>
</div>
""", unsafe_allow_html=True)

if total == 0:
    st.warning("No shipments match the current filters.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Summary</div>', unsafe_allow_html=True)

repeat_df    = df[df["DEST_COUNT"] > 1]
repeat_dests = df[df["DEST_COUNT"] > 1]["DEST_KEY"].nunique()
repeat_ships = len(repeat_df)
avg_gap      = df["GAP_HOURS"].mean()
unique_countries = df["DESTINATION_COUNTRY"].nunique()

# Top 5 fix impact
top5_dests = (
    df[df["DEST_COUNT"] > 1]
    .groupby("DEST_KEY")
    .size()
    .nlargest(5)
    .index
)
top5_count = df[df["DEST_KEY"].isin(top5_dests)].shape[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Shipments", f"{total:,}", help="Shipments with outer geofence but no M3 arrival")
c2.metric("Repeat Destinations", f"{repeat_dests:,}",
          delta=f"{repeat_ships:,} shipments ({round(repeat_ships/total*100)}%)",
          delta_color="inverse",
          help="Same destination appears multiple times = misplaced geofence")
c3.metric("Countries Affected", unique_countries,
          help=f"{df['DESTINATION_NAME'].nunique()} unique destination names")
c4.metric("Avg Gap (Outer→Timeout)", f"{avg_gap:.0f}h",
          delta=f"{avg_gap/24:.1f} days avg",
          delta_color="off")
c5.metric("Fix Top 5 Geofences →", f"{top5_count:,} resolved",
          delta=f"{round(top5_count/total*100)}% of all cases",
          delta_color="normal")

# ── INSIGHT BANNER ────────────────────────────────────────────────────────────
if total > 0 and repeat_ships > 0:
    top_dest = (
        df[df["DEST_COUNT"] > 1]
        .groupby(["DESTINATION_NAME", "DEST_KEY"])
        .size()
        .idxmax()
    )
    top_dest_name = top_dest[0]
    top_dest_count = df[df["DEST_KEY"] == top_dest[1]].shape[0]

    st.markdown(f"""
    <div class="insight-box">
        📌 <strong>{round(repeat_ships/total*100)}% of all missing M3s</strong> occur at the same
        destination addresses repeatedly — this is a <strong>geofence placement problem</strong>,
        not random truck plate changes. The single biggest offender is
        <strong>{top_dest_name}</strong> with <strong>{top_dest_count} incidents</strong>.
        Fixing just the top 5 geofences resolves <strong>{round(top5_count/total*100)}%</strong> of all cases.
    </div>
    """, unsafe_allow_html=True)

# ── CHARTS ROW 1 ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Geographic & Time Analysis</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([3, 2])

with col_left:
    country_counts = (
        df.groupby(["DESTINATION_COUNTRY", "COUNTRY_LABEL"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
    )
    fig_country = px.bar(
        country_counts, x="count", y="COUNTRY_LABEL",
        orientation="h", title="Shipments by Destination Country",
        color="count",
        color_continuous_scale=["#3b82f6", "#e94560", "#e30613"],
        labels={"count": "Shipments", "COUNTRY_LABEL": ""},
    )
    fig_country.update_layout(**PLOTLY_THEME, title_font_size=13, height=380,
                               coloraxis_showscale=False, margin=dict(l=0,r=0,t=40,b=0))
    fig_country.update_traces(marker_line_width=0)
    st.plotly_chart(fig_country, use_container_width=True)

with col_right:
    df["GAP_CAT"] = df["GAP_HOURS"].apply(gap_category)
    gap_order = ["< 24h (plate change?)", "24–72h (borderline)", "72–168h (7 days)", "> 168h (bad geofence)"]
    gap_colors = {"< 24h (plate change?)": "#22c55e", "24–72h (borderline)": "#f59e0b",
                  "72–168h (7 days)": "#e94560", "> 168h (bad geofence)": "#e30613"}
    gap_counts = df["GAP_CAT"].value_counts().reindex(gap_order, fill_value=0).reset_index()
    gap_counts.columns = ["Category", "Count"]

    fig_gap = px.pie(
        gap_counts, values="Count", names="Category",
        title="Time Gap: Outer Geofence → Timeout",
        color="Category", color_discrete_map=gap_colors,
        hole=0.45,
    )
    fig_gap.update_layout(**PLOTLY_THEME, title_font_size=13, height=380,
                           legend=dict(orientation="v", x=1.05, y=0.5),
                           margin=dict(l=0, r=120, t=40, b=0))
    fig_gap.update_traces(textposition="inside", textinfo="percent+label",
                          insidetextfont=dict(size=10))
    st.plotly_chart(fig_gap, use_container_width=True)

# ── CHARTS ROW 2 ──────────────────────────────────────────────────────────────
col2a, col2b, col2c = st.columns(3)

with col2a:
    weekly = (
        df.dropna(subset=["OUTER_WEEK"])
        .groupby("OUTER_WEEK")
        .size()
        .reset_index(name="count")
        .sort_values("OUTER_WEEK")
    )
    fig_weekly = px.line(
        weekly, x="OUTER_WEEK", y="count",
        title="Weekly Volume Trend", markers=True,
        labels={"OUTER_WEEK": "Week", "count": "Shipments"},
        color_discrete_sequence=["#e30613"],
    )
    fig_weekly.update_traces(fill="tozeroy", fillcolor="rgba(227,6,19,0.1)", line_width=2)
    fig_weekly.update_layout(**PLOTLY_THEME, title_font_size=13, height=280,
                              margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig_weekly, use_container_width=True)

with col2b:
    bol_counts = df["BOL_PREFIX"].value_counts().reset_index()
    bol_counts.columns = ["Prefix", "Count"]
    bol_counts["Label"] = "BOL " + bol_counts["Prefix"] + "xxx"
    fig_bol = px.pie(
        bol_counts, values="Count", names="Label",
        title="BOL Series (Business Unit)",
        color_discrete_sequence=["#e30613","#e94560","#3b82f6","#f59e0b","#22c55e","#a855f7"],
        hole=0.4,
    )
    fig_bol.update_layout(**PLOTLY_THEME, title_font_size=13, height=280,
                           legend=dict(orientation="v", x=1.05, y=0.5),
                           margin=dict(l=0, r=100, t=40, b=0))
    fig_bol.update_traces(textposition="inside", textinfo="percent")
    st.plotly_chart(fig_bol, use_container_width=True)

with col2c:
    repeat_ships_count = len(df[df["DEST_COUNT"] > 1])
    single_ships_count = len(df[df["DEST_COUNT"] == 1])
    fig_repeat = go.Figure(go.Pie(
        labels=["Repeat destinations\n(geofence issue)", "Single occurrence\n(plate change?)"],
        values=[repeat_ships_count, single_ships_count],
        hole=0.45,
        marker_colors=["#e30613", "#3b82f6"],
    ))
    fig_repeat.update_layout(
        **PLOTLY_THEME, title="Single vs Repeat Destinations", title_font_size=13,
        height=280, legend=dict(orientation="h", x=0.5, y=-0.1, xanchor="center"),
        margin=dict(l=0, r=0, t=40, b=40),
    )
    fig_repeat.update_traces(textposition="inside", textinfo="percent",
                              insidetextfont=dict(size=12))
    st.plotly_chart(fig_repeat, use_container_width=True)

# ── PRIORITY TABLE ────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🎯 Geofence Remediation Priority List</div>',
            unsafe_allow_html=True)
st.markdown("""
<div class="insight-box" style="margin-top:0; margin-bottom:16px;">
    Destinations appearing <strong>multiple times</strong> are almost certainly
    <strong>misplaced geofences</strong>. Fix these in order of frequency for maximum impact.
</div>
""", unsafe_allow_html=True)

priority_data = (
    df[df["DEST_COUNT"] > 1]
    .groupby(["DESTINATION_NAME", "DESTINATION_COUNTRY", "DESTINATION_ADDRESS"])
    .agg(
        Occurrences=("BILL_OF_LADING", "count"),
        Avg_Gap_Hrs=("GAP_HOURS", "mean"),
        Min_Gap_Hrs=("GAP_HOURS", "min"),
        Max_Gap_Hrs=("GAP_HOURS", "max"),
    )
    .reset_index()
    .sort_values("Occurrences", ascending=False)
    .reset_index(drop=True)
)
priority_data.index += 1
priority_data["% of Total"] = (priority_data["Occurrences"] / total * 100).round(1).astype(str) + "%"
priority_data["Priority"] = priority_data["Occurrences"].apply(priority_tag)
priority_data["Avg Gap"] = priority_data["Avg_Gap_Hrs"].apply(lambda x: f"{x:.0f}h")
priority_data["Country"] = priority_data["DESTINATION_COUNTRY"].apply(
    lambda c: f"{c} — {COUNTRY_NAMES.get(c, c)}"
)

display_priority = priority_data.rename(columns={
    "DESTINATION_NAME": "Destination",
    "DESTINATION_ADDRESS": "Address",
})[["Destination", "Country", "Address", "Occurrences", "% of Total", "Avg Gap", "Priority"]]

st.dataframe(
    display_priority,
    use_container_width=True,
    height=400,
    column_config={
        "Occurrences": st.column_config.ProgressColumn(
            "Occurrences", min_value=0, max_value=int(priority_data["Occurrences"].max()),
            format="%d",
        ),
    },
)

col_dl1, col_dl2 = st.columns([1, 5])
with col_dl1:
    st.download_button(
        "⬇ Download Priority List",
        data=display_priority.to_csv(index=True).encode("utf-8"),
        file_name="bridgestone_geofence_priority.csv",
        mime="text/csv",
    )

# ── ALL SHIPMENTS TABLE ───────────────────────────────────────────────────────
st.markdown('<div class="section-title">All Shipments</div>', unsafe_allow_html=True)

# Table-level filters
filter_col1, filter_col2, filter_col3 = st.columns([3, 2, 1])
with filter_col1:
    table_search = st.text_input(
        "Search", placeholder="Filter by BOL, destination, city…",
        label_visibility="collapsed"
    )
with filter_col2:
    sort_col = st.selectbox(
        "Sort by", ["Outer Geofence ↓", "Gap Hours ↓", "Gap Hours ↑", "Country A–Z", "Destination A–Z"],
        label_visibility="collapsed"
    )
with filter_col3:
    st.download_button(
        "⬇ Download",
        data=df.drop(columns=["DEST_KEY","OUTER_WEEK","BOL_PREFIX","DEST_COUNT","GAP_CAT","COUNTRY_LABEL"], errors="ignore")
              .to_csv(index=False).encode("utf-8"),
        file_name="bridgestone_eu_missed_m3.csv",
        mime="text/csv",
    )

# Apply table search
table_df = df.copy()
if table_search.strip():
    mask = (
        table_df["BILL_OF_LADING"].astype(str).str.contains(table_search, case=False, na=False)
        | table_df["DESTINATION_NAME"].str.contains(table_search, case=False, na=False)
        | table_df["DESTINATION_CITY"].str.contains(table_search, case=False, na=False)
        | table_df["DESTINATION_ADDRESS"].str.contains(table_search, case=False, na=False)
    )
    table_df = table_df[mask]

sort_map = {
    "Outer Geofence ↓": ("OUTER_GEOFENCE_TIMESTAMP", False),
    "Gap Hours ↓":       ("GAP_HOURS", False),
    "Gap Hours ↑":       ("GAP_HOURS", True),
    "Country A–Z":       ("DESTINATION_COUNTRY", True),
    "Destination A–Z":   ("DESTINATION_NAME", True),
}
sort_field, sort_asc = sort_map[sort_col]
table_df = table_df.sort_values(sort_field, ascending=sort_asc)

st.caption(f"Showing {len(table_df):,} of {total:,} shipments | Gap color: 🟢 <24h · 🟡 24–72h · 🔴 >72h")

display_df = table_df[[
    "BILL_OF_LADING", "OUTER_GEOFENCE_TIMESTAMP", "TIMED_OUT_TIMESTAMP",
    "GAP_HOURS", "DESTINATION_NAME", "DESTINATION_CITY", "DESTINATION_COUNTRY",
    "DESTINATION_POSTAL_CODE", "DESTINATION_ADDRESS",
]].rename(columns={
    "BILL_OF_LADING":           "BOL",
    "OUTER_GEOFENCE_TIMESTAMP": "Outer Geofence (UTC)",
    "TIMED_OUT_TIMESTAMP":      "Timed Out (UTC)",
    "GAP_HOURS":                "Gap (hrs)",
    "DESTINATION_NAME":         "Destination",
    "DESTINATION_CITY":         "City",
    "DESTINATION_COUNTRY":      "Country",
    "DESTINATION_POSTAL_CODE":  "Postal Code",
    "DESTINATION_ADDRESS":      "Address",
})

st.dataframe(
    display_df,
    use_container_width=True,
    height=480,
    hide_index=True,
    column_config={
        "Outer Geofence (UTC)": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Timed Out (UTC)":      st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Gap (hrs)":            st.column_config.NumberColumn(format="%.0f h"),
        "BOL":                  st.column_config.TextColumn(width="small"),
        "Country":              st.column_config.TextColumn(width="small"),
        "Postal Code":          st.column_config.TextColumn(width="small"),
    },
)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Bridgestone EU · Project44 Tracking Analysis · "
    "Data source: PRODUCTION_LAKEHOUSE_EU.TRUCKLOADTRACKING · "
    "Outer geofence = 50km radius · M3 = ENTERED_FINAL_GEOFENCE event"
)
