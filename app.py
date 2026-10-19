"""Sugar Cosmetics – Instagram Performance Analytics (Streamlit dashboard).

Run:  streamlit run app.py
Data: uses cleaned/sugar_instagram_clean.csv (from your notebook) if present,
      otherwise the Google Sheet.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Sugar Cosmetics – Instagram Analytics",
                   page_icon="💄", layout="wide")

SHEET_ID = "1D22pa1iiJ-8uYirpZq-4GndO3id7XU-AE14Hybe0_qk"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
LOCAL_CLEAN = Path("cleaned/sugar_instagram_clean.csv")
PINK, PURPLE = "#e91e63", "#9c27b0"
COUNT_COLS = ["likes", "comments", "shares", "saves"]
NUMERIC = COUNT_COLS + ["reach", "impressions", "profile_visits", "follows"]
CATS = ["post_type", "campaign_type", "audience_emotion", "engagement_source"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ------------------------------------------------------------------ data
def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Same cleaning steps as the notebook (safe to run on already-clean data)."""
    df = raw.copy()
    df.columns = (df.columns.astype(str).str.strip().str.lower()
                  .str.replace(r"[^\w]+", "_", regex=True).str.strip("_"))
    df["post_date"] = pd.to_datetime(df["post_date"], errors="coerce")
    df = df.dropna(subset=["post_date"])
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df[COUNT_COLS + ["profile_visits", "follows"]] = (
        df[COUNT_COLS + ["profile_visits", "follows"]].fillna(0).clip(lower=0))
    df = df.dropna(subset=["reach", "impressions"])
    df = df[(df["reach"] > 0) & (df["impressions"] > 0)].drop_duplicates()
    for c in CATS:
        df[c] = df[c].astype(str).str.strip().str.title()
    df["hashtag_list"] = df["hashtags"].astype(str).str.lower().apply(
        lambda t: list(dict.fromkeys(re.findall(r"#\w+", t))))
    df["hashtag_count"] = df["hashtag_list"].str.len()
    df["interactions"] = df[COUNT_COLS].sum(axis=1)
    df["engagement_rate"] = df["interactions"] / df["reach"] * 100
    df["follow_conversion"] = df["follows"] / df["profile_visits"].replace(0, np.nan) * 100
    df["post_date"] = df["post_date"].dt.normalize()
    df["month"] = df["post_date"].dt.to_period("M").dt.to_timestamp()
    df["weekday"] = df["post_date"].dt.day_name()
    return df.reset_index(drop=True)


@st.cache_data(show_spinner="Loading data…")
def load() -> pd.DataFrame:
    if LOCAL_CLEAN.exists():
        raw = pd.read_csv(LOCAL_CLEAN)
    else:
        raw = pd.read_csv(SHEET_URL)
    return prepare(raw)


# ------------------------------------------------------------------ sidebar
st.sidebar.title("💄 Filters")
try:
    data = load()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load data: {e}")
    st.info("Put `cleaned/sugar_instagram_clean.csv` next to this file, or share the Google Sheet as 'Anyone with the link'.")
    st.stop()

d_min, d_max = data["post_date"].min().date(), data["post_date"].max().date()
dates = st.sidebar.date_input("Date range", (d_min, d_max), min_value=d_min, max_value=d_max)
start, end = (dates if isinstance(dates, tuple) and len(dates) == 2 else (d_min, d_max))

df = data[(data["post_date"].dt.date >= start) & (data["post_date"].dt.date <= end)]
for col, label in [("post_type", "Post type"), ("campaign_type", "Campaign"),
                   ("audience_emotion", "Audience emotion"), ("engagement_source", "Engagement source")]:
    opts = sorted(data[col].unique())
    chosen = st.sidebar.multiselect(label, opts, default=opts)
    df = df[df[col].isin(chosen)]

if df.empty:
    st.warning("No posts match the current filters.")
    st.stop()

# ------------------------------------------------------------------ header + KPIs
st.title("Sugar Cosmetics – Instagram Performance Analytics")
st.caption(f"{len(df):,} posts · {start:%d %b %Y} → {end:%d %b %Y}")

k = st.columns(6)
k[0].metric("Posts", f"{len(df):,}")
k[1].metric("Total reach", f"{df['reach'].sum()/1e6:,.1f} M")
k[2].metric("Interactions", f"{df['interactions'].sum()/1e6:,.1f} M")
k[3].metric("Avg engagement rate", f"{df['engagement_rate'].mean():.2f} %")
k[4].metric("Total follows", f"{df['follows'].sum():,}")
k[5].metric("Follow conversion", f"{df['follows'].sum()/max(df['profile_visits'].sum(),1)*100:.1f} %")


def style(fig, h=380):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=50, b=10), title_font_size=16)
    return fig


def avg_bar(col, title, horizontal=False):
    t = df.groupby(col, as_index=False)["engagement_rate"].mean().sort_values("engagement_rate", ascending=False)
    t["engagement_rate"] = t["engagement_rate"].round(2)
    fig = px.bar(t, x="engagement_rate" if horizontal else col, y=col if horizontal else "engagement_rate",
                 text="engagement_rate", color_discrete_sequence=[PINK], title=title,
                 labels={"engagement_rate": "Avg engagement rate (%)"}, orientation="h" if horizontal else "v")
    return style(fig)


tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Content performance", "Timing", "Hashtags & funnel"])

# ------------------------------------------------------------------ Overview
with tab1:
    c1, c2 = st.columns(2)
    m = df.groupby("month").agg(reach=("reach", "sum"), impressions=("impressions", "sum")).reset_index()
    c1.plotly_chart(style(px.line(m, x="month", y=["reach", "impressions"], markers=True,
                                  title="Monthly reach & impressions",
                                  color_discrete_sequence=[PINK, PURPLE])), use_container_width=True)
    e = df.groupby("month")["engagement_rate"].mean().reset_index()
    c2.plotly_chart(style(px.line(e, x="month", y="engagement_rate", markers=True,
                                  title="Monthly avg engagement rate (%)",
                                  color_discrete_sequence=[PINK])), use_container_width=True)
    c3, c4 = st.columns(2)
    emo = df["audience_emotion"].value_counts().reset_index()
    c3.plotly_chart(style(px.pie(emo, names="audience_emotion", values="count", hole=0.5,
                                 title="Posts by audience emotion",
                                 color_discrete_sequence=px.colors.sequential.RdPu_r)), use_container_width=True)
    f = df.groupby("month")["follows"].sum().reset_index()
    c4.plotly_chart(style(px.bar(f, x="month", y="follows", title="Monthly new follows",
                                 color_discrete_sequence=[PURPLE])), use_container_width=True)

# ------------------------------------------------------------------ Content
with tab2:
    c1, c2 = st.columns(2)
    c1.plotly_chart(avg_bar("post_type", "Avg engagement rate by post type"), use_container_width=True)
    c2.plotly_chart(avg_bar("campaign_type", "Avg engagement rate by campaign", True), use_container_width=True)
    c3, c4 = st.columns(2)
    c3.plotly_chart(avg_bar("engagement_source", "Avg engagement rate by source"), use_container_width=True)
    heat = df.pivot_table(index="campaign_type", columns="post_type", values="engagement_rate", aggfunc="mean").round(2)
    c4.plotly_chart(style(px.imshow(heat, text_auto=True, color_continuous_scale="RdPu", aspect="auto",
                                    title="Engagement rate: campaign × post type")), use_container_width=True)

# ------------------------------------------------------------------ Timing
with tab3:
    c1, c2 = st.columns(2)
    wd = (df.groupby("weekday")["engagement_rate"].mean().reindex(WEEKDAYS).dropna().round(2).reset_index())
    c1.plotly_chart(style(px.bar(wd, x="weekday", y="engagement_rate", text="engagement_rate",
                                 title="Avg engagement rate by weekday",
                                 color_discrete_sequence=[PURPLE])), use_container_width=True)
    c2.plotly_chart(style(px.box(df, x="hashtag_count", y="engagement_rate",
                                 title="Engagement rate by number of hashtags",
                                 color_discrete_sequence=[PINK])), use_container_width=True)

# ------------------------------------------------------------------ Hashtags & funnel
with tab4:
    c1, c2 = st.columns(2)
    tags = df[["engagement_rate", "reach", "hashtag_list"]].explode("hashtag_list").dropna(subset=["hashtag_list"])
    th = (tags.groupby("hashtag_list").agg(uses=("reach", "size"), avg_eng=("engagement_rate", "mean"))
          .round(2).sort_values("avg_eng").tail(15).reset_index())
    c1.plotly_chart(style(px.bar(th, x="avg_eng", y="hashtag_list", orientation="h", text="avg_eng",
                                 title="Avg engagement rate by hashtag",
                                 labels={"avg_eng": "Avg engagement rate (%)", "hashtag_list": ""},
                                 color_discrete_sequence=[PINK])), use_container_width=True)
    stages = ["Impressions", "Reach", "Interactions", "Profile visits", "Follows"]
    vals = [df["impressions"].sum(), df["reach"].sum(), df["interactions"].sum(),
            df["profile_visits"].sum(), df["follows"].sum()]
    c2.plotly_chart(style(go.Figure(go.Funnel(y=stages, x=vals, marker_color=PINK,
                                              textinfo="value+percent initial"))
                          .update_layout(title="Audience funnel")), use_container_width=True)

# ------------------------------------------------------------------ Insights
st.divider()
st.subheader("Key takeaways")
best = lambda c: df.groupby(c)["engagement_rate"].mean().idxmax()
spread = lambda c: df.groupby(c)["engagement_rate"].mean().agg(lambda s: s.max() - s.min())
st.markdown(
    f"- Highest avg engagement: **{best('post_type')}** posts, **{best('campaign_type')}** campaigns, "
    f"**{best('engagement_source')}** source, **{best('weekday')}**s.\n"
    f"- The gaps are small: only **{spread('post_type'):.2f}** pts between best and worst post type and "
    f"**{spread('campaign_type'):.2f}** pts between campaigns, so no single format or campaign clearly dominates.\n"
    f"- Funnel: {vals[2]/vals[1]*100:.1f}% of reach interacts, and {vals[4]/max(vals[3],1)*100:.1f}% of profile visits turn into follows."
)

with st.expander("View / download filtered data"):
    show = df.drop(columns=["hashtag_list"])
    st.dataframe(show.head(1000), use_container_width=True)
    st.download_button("Download filtered CSV", show.to_csv(index=False).encode(), "filtered_posts.csv", "text/csv")
