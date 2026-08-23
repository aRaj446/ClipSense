import base64
import io
import os
import re as _re
from datetime import datetime
from urllib.parse import urlparse

import html
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components  # noqa: F401  (kept for dashboard charts)
from wordcloud import STOPWORDS, WordCloud

st.set_page_config(
    page_title="Sensecap — Customer Sentiment",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "df" not in st.session_state:
    st.session_state["df"] = None
if "uploaded_name" not in st.session_state:
    st.session_state["uploaded_name"] = None
if "clipsense_mode" not in st.session_state:
    st.session_state["clipsense_mode"] = False
if "clipsense_dataset_url" not in st.session_state:
    st.session_state["clipsense_dataset_url"] = None
if "audience_preferences" not in st.session_state:
    st.session_state["audience_preferences"] = None

# -----------------------------------------------------------------------------
# ClipSense deep-link loader
# Reads ?source=clipsense&dataset_url=<url>&dataset_name=<name> on first load.
# SSRF guard: dataset_url must share origin with CLIPSENSE_BASE_URL.
# Duplicate-fetch prevention: skips if dataset_url unchanged in session.
# -----------------------------------------------------------------------------
_CLIPSENSE_BASE = os.environ.get("CLIPSENSE_BASE_URL", "http://localhost:8000").rstrip("/")
_ALLOWED_ORIGIN = "{u.scheme}://{u.netloc}".format(u=urlparse(_CLIPSENSE_BASE))

def _clipsense_url_allowed(url: str) -> bool:
    try:
        p = urlparse(url)
        return "{u.scheme}://{u.netloc}".format(u=p) == _ALLOWED_ORIGIN
    except Exception:
        return False

def _parse_pipe(val) -> list:
    """Decode a pipe-delimited cell back into a list, unescaping \\| → |."""
    if not val or (isinstance(val, float) and val != val):
        return []
    return [item.replace("\\|", "|") for item in str(val).split("|") if item.strip()]


def normalize_clipsense(raw: pd.DataFrame) -> pd.DataFrame:
    """Map SENSECAP_CS_COLUMNS → Sensecap internal schema without fabricating geo/ROI."""
    df = raw.copy()
    # canonical column renames
    renames = {
        "theme":           "theme",
        "sentiment_label": "sentiment_label",
        "sentiment_score": "sentiment_score",
        "confidence":      "confidence",
        "video_timestamp": "video_timestamp",
        "dataset_name":    "dataset_name",
        "source":          "source",
    }
    for src, dst in renames.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    # timestamp: use wall-clock created_at exported as "timestamp"
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.Timestamp.utcnow()
    df = df.dropna(subset=["timestamp", "text"])
    # platform derived from source column
    if "platform" not in df.columns:
        df["platform"] = df["source"].fillna("ClipSense") if "source" in df.columns else "ClipSense"
    # region/country — no fabrication, use single neutral value
    for col, val in [("region", "Global"), ("country", "Global"), ("country_code", "")]:
        if col not in df.columns:
            df[col] = val
    # engagement columns — zero, not fabricated
    for col in ["likes", "shares", "replies", "engagement"]:
        if col not in df.columns:
            df[col] = 0
    # no lat/lon — omit entirely so map card gets empty reg DataFrame
    # no roi columns — omit entirely
    # numeric coercion
    for col in ["sentiment_score", "confidence"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _extract_audience_preferences(df: pd.DataFrame) -> dict:
    """
    Read audience_preferences from the first data row of the ap_* columns.
    Returns a dict with keys: liked, disliked, recurring_requests,
    recurring_complaints, recurring_praise — each a list of strings.
    Returns all-empty lists if the columns are absent.
    """
    ap = {"liked": [], "disliked": [], "recurring_requests": [], "recurring_complaints": [], "recurring_praise": []}
    if df.empty:
        return ap
    row = df.iloc[0]
    mapping = {
        "liked":                "ap_liked",
        "disliked":             "ap_disliked",
        "recurring_requests":   "ap_recurring_requests",
        "recurring_complaints": "ap_recurring_complaints",
        "recurring_praise":     "ap_recurring_praise",
    }
    for key, col in mapping.items():
        if col in df.columns:
            ap[key] = _parse_pipe(row.get(col, ""))
    return ap

_params = st.query_params
if _params.get("source") == "clipsense":
    _dataset_url  = _params.get("dataset_url", "")
    _dataset_name = _params.get("dataset_name", "ClipSense Dataset")
    if _dataset_url and _dataset_url != st.session_state["clipsense_dataset_url"]:
        if not _clipsense_url_allowed(_dataset_url):
            st.error(f"Blocked: dataset_url origin is not allowed. Expected origin: {_ALLOWED_ORIGIN}")
            st.stop()
        with st.spinner("Loading ClipSense dataset…"):
            try:
                resp = requests.get(_dataset_url, timeout=15)
                resp.raise_for_status()
                raw = pd.read_csv(io.StringIO(resp.text))
                st.session_state["audience_preferences"] = _extract_audience_preferences(raw)
                st.session_state["df"] = normalize_clipsense(raw)
                st.session_state["uploaded_name"] = _dataset_name
                st.session_state["clipsense_mode"] = True
                st.session_state["clipsense_dataset_url"] = _dataset_url
            except Exception as exc:
                st.error(f"Failed to load ClipSense dataset: {exc}")
                st.stop()

# -----------------------------------------------------------------------------
# Sensecap visual system — tuned to the supplied reference screenshot
# -----------------------------------------------------------------------------
TEXT   = "#26221F"
MUTED  = "#91887E"
BORDER = "#E9E3DA"
ORANGE = "#F47A20"
DARK   = "#3A3734"
GRAY   = "#C9C3BB"
BLUE   = "#78A8D7"
GREEN  = "#55A88B"
YELLOW = "#E7B545"

# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------
def normalize(df):
    df = df.copy()
    required = ["platform", "text", "timestamp"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("Missing required columns: " + ", ".join(missing))
        st.stop()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "text"])
    defaults = {
        "theme":"Unspecified", "likes":0, "shares":0, "replies":0, "engagement":0,
        "region":"Global", "country":"Global", "country_code":"", "language":"English",
        "campaign":"Trailer Campaign", "content_type":"Comment", "roi_driver":"Brand Value",
        "roi_value_usd":0.0, "sentiment_label":"Neutral", "sentiment_score":0.0,
        "lat":0.0, "lon":0.0,
    }
    for c, v in defaults.items():
        if c not in df.columns:
            df[c] = v
    if df["sentiment_label"].isna().all():
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        scores = df["text"].astype(str).map(lambda x: analyzer.polarity_scores(x)["compound"])
        df["sentiment_score"] = scores
        df["sentiment_label"] = np.select([scores >= .05, scores <= -.05], ["Positive", "Negative"], default="Neutral")
    for c in ["likes","shares","replies","engagement","roi_value_usd","sentiment_score","lat","lon"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if (df["engagement"] == 0).all():
        df["engagement"] = df["likes"] + 2 * df["shares"] + df["replies"]
    return df

# -----------------------------------------------------------------------------
# Upload gate
# Skipped entirely when arriving via ClipSense deep-link (df already loaded).
# -----------------------------------------------------------------------------
if st.session_state["df"] is None:
    st.markdown("""
    <style>
      html, body, [data-testid="stAppViewContainer"],
      section[data-testid="stMain"], .block-container,
      [data-testid="stMainBlockContainer"] {
        background: #F8F6F1 !important;
      }
      header[data-testid="stHeader"], div[data-testid="stToolbar"],
      section[data-testid="stSidebar"], [data-testid="stDecoration"],
      [data-testid="stStatusWidget"] { display: none !important; }
      [data-testid="stFileUploaderDropzone"] {
        border: 1.5px dashed #D5CBBF !important;
        border-radius: 14px !important;
        background: #fff !important;
      }
    </style>
    """, unsafe_allow_html=True)

    st.html("""
    <div style="max-width:520px;margin:10vh auto 0;text-align:center;font-family:Inter,-apple-system,sans-serif;">
      <div style="display:inline-flex;align-items:center;gap:10px;margin-bottom:24px;">
        <span style="width:30px;height:30px;border-radius:50%;background:#F47A20;display:inline-flex;align-items:center;justify-content:center;box-shadow:0 3px 12px rgba(244,122,32,.35);">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="white" stroke-width="2.2"/></svg>
        </span>
        <span style="font-size:22px;font-weight:740;letter-spacing:-.5px;color:#D85E16;">Sensecap</span>
      </div>
      <div style="font-size:36px;font-weight:720;letter-spacing:-1.6px;line-height:1.05;color:#26221F;">Upload your sentiment data</div>
      <div style="margin-top:12px;font-size:14px;color:#91887E;line-height:1.6;">Upload a CSV containing customer feedback to generate your sentiment intelligence dashboard.</div>
    </div>
    """)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        uploaded = st.file_uploader(
            "Drop your CSV here or click to browse",
            type=["csv"],
            help="Requires at least: platform, text, timestamp columns.",
        )

    st.html("""
    <div style="text-align:center;margin-top:16px;font-family:Inter,-apple-system,sans-serif;">
      <div style="font-size:11px;font-weight:500;color:#B5AFA8;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px;">Supported fields</div>
      <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:7px;">
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">platform</span>
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">text</span>
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">timestamp</span>
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">sentiment</span>
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">theme</span>
        <span style="padding:5px 13px;border-radius:999px;background:#F4F0EA;border:1px solid #E9E3DA;color:#756E66;font-size:11px;">region</span>
      </div>
    </div>
    """)

    if uploaded is not None:
        with st.spinner("Loading dataset…"):
            source = pd.read_csv(uploaded, parse_dates=["timestamp"])
            st.session_state["audience_preferences"] = _extract_audience_preferences(source)
            st.session_state["df"] = normalize(source)
            st.session_state["uploaded_name"] = uploaded.name
        st.rerun()
    st.stop()

df = st.session_state["df"]
cs_mode = st.session_state["clipsense_mode"]
audience_prefs = st.session_state.get("audience_preferences") or {}

# Inject full-bleed CSS directly into <head> via JS — the only reliable way
# to override Streamlit's JS-injected layout styles.
st.components.v1.html("""
<script>  /* global CSS injector — must use components.html to write to parent document head */
(function(){
  var css = `
    /* ── TOKENS ── */
    :root {
      --bg:#F8F6F1; --card:#FFFFFF; --text:#26221F; --text-2:#756E66; --muted:#91887E;
      --border:#E9E3DA; --orange:#F47A20; --orange-dark:#D85E16;
      --orange-pale:#FFF0E3; --dark:#3A3734; --gray:#BDB8B1;
      --blue:#78A8D7; --green:#55A88B; --yellow:#E7B545;
      --font:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
      --radius:16px; --shadow:0 2px 12px rgba(50,40,30,.07);
      --shadow-hover:0 8px 32px rgba(50,40,30,.12);
    }

    /* ── RESET ── */
    html,body { margin:0!important; padding:0!important; width:100%!important; overflow-x:hidden!important; background:var(--bg)!important; }
    *,*::before,*::after { box-sizing:border-box; }
    html,body,[class*='css'] { font-family:var(--font)!important; font-size:14px; color:var(--text); -webkit-font-smoothing:antialiased; }

    /* ── STREAMLIT SHELL ── */
    .stApp { background:var(--bg)!important; width:100vw!important; max-width:100vw!important; overflow-x:hidden!important; }
    [data-testid='stAppViewContainer'],
    [data-testid='stAppViewContainer']>section,
    [data-testid='stAppViewContainer']>section>div {
      width:100%!important; max-width:100%!important;
      padding:0!important; margin:0!important; flex:1 1 auto!important;
    }
    section[data-testid='stMain'],
    section[data-testid='stMain']>div {
      width:100%!important; max-width:100%!important; padding:0!important;
    }
    .block-container,
    [data-testid="stMainBlockContainer"] {
      width:100%!important; max-width:100%!important;
      padding:1.5rem 5rem 4rem!important;
      margin:0 auto!important; box-sizing:border-box!important;
    }

    header[data-testid='stHeader'] { display:none!important; }
    div[data-testid='stToolbar'] { display:none!important; }
    section[data-testid='stSidebar'] { display:none!important; }
    [data-testid='stDecoration'] { display:none!important; }
    [data-testid='stStatusWidget'] { display:none!important; }

    /* ── COLUMNS ── */
    [data-testid='stVerticalBlock'] { width:100%!important; max-width:100%!important; min-width:0!important; }
    [data-testid='stHorizontalBlock'],div[data-orientation='horizontal'] {
      width:100%!important; max-width:100%!important;
      gap:1.5rem!important; flex-wrap:nowrap!important;
    }
    [data-testid='stTabsContent'],[data-testid='stTabsContent']>div {
      width:100%!important; max-width:100%!important; padding:0!important;
    }
    [data-testid='stColumn'] { flex:1 1 0%!important; min-width:0!important; max-width:100%!important; overflow:visible!important; }
    [data-testid='stColumn']>div { width:100%!important; max-width:100%!important; }
    .stPlotlyChart,.stImage { margin-top:0!important; width:100%!important; }

    /* ── HIDE SIDE COLUMNS IN HEADER ROW ── */
    .st-emotion-cache-1y0go3k,.st-emotion-cache-y4m9vf { display:none!important; }
    [data-testid='stHorizontalBlock']:has(.st-emotion-cache-1y0go3k) [data-testid='stColumn']:not(.st-emotion-cache-1y0go3k):not(.st-emotion-cache-y4m9vf) {
      flex:1 1 100%!important; max-width:100%!important;
    }

    /* ── TABS — hide native bar, keep content ── */
    div[data-baseweb='tab-list'] { display:none!important; }
    div[data-baseweb='tab-highlight'],div[data-baseweb='tab-border'] { display:none!important; }
    [data-testid='stTabs'] { margin-top:0!important; }

    /* ── CUSTOM PILL NAV ── */
    #sc-nav-pill .sc-tab {
      border-radius:999px; height:34px;
      padding:0 16px; font-size:11px; letter-spacing:.1px;
      font-weight:620; color:#756E66;
      background:transparent; border:none;
      cursor:pointer; white-space:nowrap;
      transition:background .2s,color .2s,box-shadow .2s;
      display:inline-flex;align-items:center;
    }
    #sc-nav-pill .sc-tab:hover { background:rgba(64,59,55,.07); }
    #sc-nav-pill .sc-tab.sc-active {
      background:#3A3734; color:#fff;
      box-shadow:0 1px 6px rgba(0,0,0,.18);
    }

    /* ── NATIVE CONTROLS ── */
    div[data-baseweb='select']>div {
      border-radius:10px!important; border-color:var(--border)!important;
      background:#fff!important; min-height:38px!important;
      font-size:13px!important;
    }
    div[data-baseweb='select'] span { font-size:13px!important; }
    button[data-testid='stPopoverButton'] {
      border-radius:10px!important; border:1px solid var(--border)!important;
      background:#fff!important; font-size:13px!important; min-height:38px!important;
    }
    button[data-testid='stDownloadButton'] {
      border-radius:10px!important; font-size:13px!important;
      background:var(--orange)!important; color:#fff!important;
      border:none!important; padding:10px 20px!important;
      font-weight:600!important; cursor:pointer!important;
      transition:background .18s!important;
    }
    button[data-testid='stDownloadButton']:hover { background:var(--orange-dark)!important; }
    [data-testid='stDataFrame'] { border:1px solid var(--border)!important; border-radius:12px!important; overflow:hidden!important; }

    /* ── PAGE TITLE ── */
    .title-row { display:flex; justify-content:space-between; align-items:flex-end; margin:28px 0 20px; }
    .pg-title { font-size:38px; line-height:1.02; font-weight:700; letter-spacing:-1.5px; color:var(--text); }
    .pg-sub { font-size:13px; font-weight:400; color:var(--muted); margin-top:5px; line-height:1.5; }
    .pg-badge {
      font-size:11px; font-weight:500; color:var(--muted); background:#EDE9E3;
      border-radius:999px; padding:5px 13px; white-space:nowrap; letter-spacing:0;
    }

    /* ── KPI CARDS ── */
    .kpi-card {
      background:#fff; border:1px solid var(--border); border-radius:var(--radius);
      padding:22px 24px 20px; min-height:110px;
      display:flex; flex-direction:column; justify-content:center;
      box-shadow:var(--shadow);
      transition:box-shadow .22s ease;
      overflow:hidden;
    }
    .kpi-card:hover { box-shadow:0 6px 20px rgba(50,40,30,.09); }
    .kpi-label {
      font-size:10px; font-weight:600; letter-spacing:.5px;
      text-transform:uppercase; color:var(--muted); white-space:nowrap;
    }
    .kpi-value {
      font-size:32px; font-weight:700; letter-spacing:-1px;
      margin-top:8px; white-space:nowrap; line-height:1; color:var(--text);
    }
    .kpi-meta { font-size:11px; font-weight:400; color:var(--muted); margin-top:6px; white-space:nowrap; }
    .kpi-accent { color:var(--orange-dark); }
    .kpi-up { color:#55A88B; font-weight:600; }

    /* ── CONTENT CARDS ── */
    .sc-card {
      background:#fff; border:1px solid var(--border); border-radius:var(--radius);
      padding:24px 24px 20px; box-shadow:var(--shadow);
      transition:box-shadow .22s ease;
    }
    .sc-card:hover { box-shadow:0 6px 24px rgba(50,40,30,.09); }
    .sc-card-title { font-size:13px; font-weight:600; color:var(--text); letter-spacing:-.1px; }
    .sc-card-sub { font-size:11px; font-weight:400; color:var(--muted); margin-top:4px; line-height:1.5; }
    .sc-card-divider { height:1px; background:var(--border); margin:14px 0; }

    /* ── UPLOAD GATE ── */
    .upload-shell { max-width:680px; margin:12vh auto 20px; text-align:center; }
    .upload-brand {
      display:inline-flex; align-items:center; gap:9px;
      color:var(--orange-dark); font-size:19px; font-weight:740; letter-spacing:-.4px;
    }
    .brand-mark {
      width:24px; height:24px; border-radius:50%; background:var(--orange);
      display:inline-flex; align-items:center; justify-content:center;
      box-shadow:0 2px 8px rgba(244,122,32,.3);
    }
    .brand-mark::after { content:''; width:8px; height:8px; border:2.5px solid #fff; border-radius:50%; display:block; }
    .upload-title { margin-top:28px; font-size:40px; line-height:1; font-weight:700; letter-spacing:-2px; color:var(--text); }
    .upload-subtitle { margin-top:10px; font-size:14px; font-weight:400; color:var(--muted); }
    .upload-hint { margin-top:14px; font-size:11px; font-weight:400; color:#756E66; }
    .upload-hint b { color:var(--orange-dark); }
    .upload-empty {
      max-width:680px; margin:0 auto; padding:32px;
      background:rgba(255,255,255,.8); border:1.5px dashed #D5CBBF;
      border-radius:20px; box-shadow:0 8px 32px rgba(50,40,30,.05);
    }
    .upload-icon {
      width:52px; height:52px; margin:0 auto 14px; border-radius:50%;
      display:flex; align-items:center; justify-content:center;
      background:var(--orange-pale); color:var(--orange-dark);
      font-size:26px; animation:floatUp 2.8s ease-in-out infinite;
    }
    @keyframes floatUp { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-5px)} }
    .upload-empty-title { font-size:15px; font-weight:680; color:var(--text); }
    .upload-empty-copy { max-width:480px; margin:8px auto 0; font-size:12px; font-weight:400; line-height:1.6; color:var(--muted); }
    .upload-schema { display:flex; justify-content:center; flex-wrap:wrap; gap:7px; margin-top:18px; }
    .upload-schema span {
      padding:5px 11px; border-radius:999px; background:#F4F0EA;
      color:#776F67; font-size:11px; border:1px solid #E9E3DA;
    }
    [data-testid='stFileUploaderDropzone'] {
      border:1.5px dashed #D5CBBF!important; border-radius:14px!important;
      background:#fff!important; min-height:80px!important;
    }
    [data-testid='stFileUploaderDropzone']>div { padding:12px 18px!important; }
    [data-testid='stFileUploaderDropzoneInstructions'] { font-size:12px!important; color:var(--muted)!important; }
    [data-testid='stFileUploaderDropzoneInstructions'] span { font-size:12px!important; }
    [data-testid='stFileUploaderDropzone'] button { border-radius:999px!important; font-size:12px!important; }

    /* ═══════════════════════════════════════════════════════════════════════
       RESPONSIVE SYSTEM
       Breakpoints: 1600 / 1440 / 1280 / 1024 / 768 / 480 / 390
       Rules use only: padding, font-size, gap, margin, width, flex, grid.
       No transform:scale() anywhere.
    ═══════════════════════════════════════════════════════════════════════ */

    /* ── 1600+ : full desktop — spacious & premium (base styles above) ── */

    /* ── ≤1440 : slightly tighter horizontal padding ── */
    @media(max-width:1440px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:48px!important;
        padding-right:48px!important;
      }
      .pg-title{ font-size:34px; letter-spacing:-1.3px; }
    }

    /* ── ≤1280 : reduce page title, card padding, section gaps ── */
    @media(max-width:1280px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:36px!important;
        padding-right:36px!important;
        padding-top:1rem!important;
        padding-bottom:3rem!important;
      }
      .pg-title{ font-size:30px; letter-spacing:-1.1px; }
      .pg-sub{ font-size:12px; }
      .title-row{ margin:20px 0 16px; }
      .sc-card{ padding:20px 20px 16px; }
      .sc-card-divider{ margin:12px 0; }
      :root{ --radius:14px; }
    }

    /* ── ≤1024 : two-column hero still works, reduce further ── */
    @media(max-width:1024px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:24px!important;
        padding-right:24px!important;
        padding-top:.875rem!important;
        padding-bottom:2.5rem!important;
      }
      .pg-title{ font-size:26px; letter-spacing:-.9px; }
      .pg-sub{ font-size:11.5px; }
      .pg-badge{ font-size:10px; padding:4px 10px; }
      .title-row{ margin:16px 0 14px; }
      .sc-card{ padding:18px 18px 14px; }
      .sc-card-title{ font-size:12px; }
      .sc-card-sub{ font-size:10.5px; }
      :root{ --radius:13px; }
      [data-testid="stHorizontalBlock"],
      div[data-orientation="horizontal"]{
        gap:1rem!important;
      }
    }

    /* ── ≤768 : stack major columns, tablet portrait & mobile landscape ── */
    @media(max-width:768px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:20px!important;
        padding-right:20px!important;
        padding-top:.75rem!important;
        padding-bottom:2rem!important;
      }
      .pg-title{ font-size:22px; letter-spacing:-.7px; }
      .pg-sub{ font-size:11px; }
      .pg-badge{ display:none; }
      .title-row{ margin:14px 0 12px; align-items:flex-start; flex-direction:column; gap:6px; }
      .sc-card{ padding:16px 16px 14px; border-radius:12px; }
      .sc-card-title,.sc-card-sub{ font-size:12px; }
      :root{ --radius:12px; --shadow:0 1px 8px rgba(50,40,30,.06); }
      [data-testid="stHorizontalBlock"],
      div[data-orientation="horizontal"]{
        flex-wrap:wrap!important;
        gap:.75rem!important;
      }
      [data-testid="stColumn"]{
        flex:1 1 100%!important;
        max-width:100%!important;
        min-width:0!important;
      }
    }

    /* ── ≤480 : large phone landscape / small tablet ── */
    @media(max-width:480px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:16px!important;
        padding-right:16px!important;
      }
      .pg-title{ font-size:20px; letter-spacing:-.5px; }
      .sc-card{ padding:12px 14px 10px; }
      :root{ --radius:11px; }
    }

    /* ── ≤390 : iPhone 14 Pro / small Android — single column ── */
    @media(max-width:390px){
      .block-container,
      [data-testid="stMainBlockContainer"]{
        padding-left:12px!important;
        padding-right:12px!important;
        padding-bottom:1.5rem!important;
      }
      .pg-title{ font-size:18px; letter-spacing:-.4px; }
      .pg-sub{ font-size:10.5px; }
      .sc-card{ padding:11px 12px 9px; border-radius:10px; }
      :root{ --radius:10px; }
    }

    /* ═══════════════════════════════════════════════════════════════════════
       MICRO-ANIMATION SYSTEM
       All animations are CSS-only except the one-shot entrance class
       assignment (done once in JS below, no Streamlit reruns).
    ═══════════════════════════════════════════════════════════════════════ */

    /* ── KEYFRAMES ── */
    @keyframes sc-fadeUp {
      from { opacity:0; transform:translateY(var(--sc-dy,10px)); }
      to   { opacity:1; transform:translateY(0); }
    }
    @keyframes sc-fadeDown {
      from { opacity:0; transform:translateY(var(--sc-dy,-6px)); }
      to   { opacity:1; transform:translateY(0); }
    }
    @keyframes sc-sheenMove {
      0%,100% { background-position:220% 0; }
      50%      { background-position:-40% 0; }
    }
    @keyframes sc-pulse {
      0%,100% { box-shadow:0 0 0 0   rgba(255,255,255,.45); }
      50%      { box-shadow:0 0 0 7px rgba(255,255,255,0);   }
    }
    @keyframes sc-barGrow { to { width:var(--w); } }
    @keyframes sc-floatRing {
      0%,100% { transform:translateY(0);   }
      50%      { transform:translateY(-8px); }
    }

    /* ── ENTRANCE — animation fill-mode:both handles opacity:0 start ── */
    .sc-enter {
      animation: sc-fadeUp var(--sc-dur,520ms) cubic-bezier(.22,1,.36,1)
                 var(--sc-delay,0ms) both;
    }
    .sc-enter-down {
      animation: sc-fadeDown var(--sc-dur,480ms) cubic-bezier(.22,1,.36,1)
                 var(--sc-delay,0ms) both;
    }

    /* ── CARD HOVER — shadow only, no lift ── */
    .sc-card:hover  { box-shadow:0 6px 24px rgba(50,40,30,.09); }
    .kpi-card:hover { box-shadow:0 6px 20px rgba(50,40,30,.09); }

    /* ── BUTTON HOVER / ACTIVE ── */
    button[data-testid='stDownloadButton'] {
      transition: background .16s ease, transform .16s ease, box-shadow .16s ease !important;
    }
    button[data-testid='stDownloadButton']:hover {
      transform:translateY(-1px) !important;
      box-shadow:0 4px 14px rgba(200,80,20,.22) !important;
    }
    button[data-testid='stDownloadButton']:active {
      transform:translateY(0) !important;
    }

    /* ── REGION BARS — stagger via nth-child ── */
    .rf {
      width:0;
      animation: sc-barGrow 950ms cubic-bezier(.22,1,.36,1) forwards;
    }
    .rr:nth-child(1) .rf { animation-delay: 180ms; }
    .rr:nth-child(2) .rf { animation-delay: 280ms; }
    .rr:nth-child(3) .rf { animation-delay: 380ms; }
    .rr:nth-child(4) .rf { animation-delay: 480ms; }
    .rr:nth-child(5) .rf { animation-delay: 580ms; }

    /* ── MAP MARKER PULSE — applied to Scattergeo marker elements ── */
    /* Plotly renders markers as <path> inside SVG; we target the
       scattergeo layer's circle markers via the known class */
    .scattergeo .point path {
      animation: sc-pulse 3.2s ease-in-out infinite;
    }

    /* ── ORANGE HERO CARD SHEEN — applied inside the components.html
       iframe so defined there; this rule covers the map card sheen
       if we ever add one at the parent level ── */
    .sc-sheen {
      position:absolute; inset:0; pointer-events:none; z-index:1;
      background: linear-gradient(
        118deg,
        transparent 20%,
        rgba(255,255,255,.06) 48%,
        transparent 76%
      );
      background-size:220% 100%;
      animation: sc-sheenMove 10s ease-in-out infinite;
    }

    /* ── FLOATING RING ── */
    .sc-ring-float {
      animation: sc-floatRing 10s ease-in-out infinite;
    }

    /* ═══════════════════════════════════════════════════════════════════════
       REDUCED MOTION — disable all non-essential motion
    ═══════════════════════════════════════════════════════════════════════ */
    @media (prefers-reduced-motion: reduce) {
      .sc-enter, .sc-enter-down {
        animation: none !important;
        transform: none !important;
      }
      .rf {
        animation: none !important;
        width: var(--w) !important;
      }
      .sc-sheen, .sc-ring-float,
      .scattergeo .point path {
        animation: none !important;
      }
      .sc-card, .kpi-card,
      button[data-testid='stDownloadButton'] {
        transition-duration: 0ms !important;
      }
    }
  `;
  var el = document.createElement('style');
  el.id = 'sensecap-global';
  el.textContent = css;
  var target = window.parent ? window.parent.document.head : document.head;
  // remove any previous injection to avoid duplicates on rerun
  var prev = (window.parent||window).document.getElementById('sensecap-global');
  if(prev) prev.remove();
  target.appendChild(el);

  // Directly set padding on the main block container via style attribute.
  // Reads window.parent.innerWidth so the inline style always matches the
  // CSS breakpoint ladder defined above. Fires on load and on resize.
  function applyMargins() {
    var doc = window.parent ? window.parent.document : document;
    var win = window.parent ? window.parent : window;
    var el  = doc.querySelector('[data-testid="stMainBlockContainer"]');
    if (!el) return;
    var w = win.innerWidth || 1920;
    var px;
    if      (w > 1440) px = '60px';
    else if (w > 1280) px = '48px';
    else if (w > 1024) px = '36px';
    else if (w >  768) px = '24px';
    else if (w >  480) px = '20px';
    else if (w >  390) px = '16px';
    else               px = '12px';
    el.style.setProperty('max-width', '1680px', 'important');
    el.style.setProperty('margin',    '0 auto',  'important');
    el.style.setProperty('padding-left',  px, 'important');
    el.style.setProperty('padding-right', px, 'important');
  }
  applyMargins();
  var _doc = window.parent ? window.parent.document : document;
  var _win = window.parent ? window.parent : window;
  // Re-apply on every resize so inline padding tracks the viewport
  _win.addEventListener('resize', applyMargins);
  // MutationObserver catches Streamlit re-renders that reset inline styles
  var _obs = new MutationObserver(applyMargins);
  _obs.observe(_doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style','class'] });
  setTimeout(function(){ _obs.disconnect(); }, 30000);

  // ── ENTRANCE ANIMATION — retry until sc-header exists, then fire once ──
  var _entranceDone = false;
  function applyEntrance() {
    if (_entranceDone) return;
    var d = _doc;
    var hdr = d.getElementById('sc-header');
    if (!hdr) return;  // DOM not ready yet — caller will retry
    _entranceDone = true;
    hdr.style.opacity = '0';
    hdr.style.setProperty('--sc-dy','-6px');
    hdr.style.setProperty('--sc-delay','0ms');
    hdr.style.setProperty('--sc-dur','480ms');
    hdr.classList.add('sc-enter-down');
    d.querySelectorAll('.title-row').forEach(function(el) {
      el.style.opacity = '0';
      el.style.setProperty('--sc-dy','8px');
      el.style.setProperty('--sc-delay','60ms');
      el.style.setProperty('--sc-dur','520ms');
      el.classList.add('sc-enter');
    });
    var kpiDelays = [100, 140, 180, 220];
    d.querySelectorAll('[data-testid="stCustomComponentV1"]').forEach(function(fr, i) {
      fr.style.opacity = '0';
      fr.style.setProperty('--sc-dy','12px');
      fr.style.setProperty('--sc-delay', kpiDelays[Math.min(i, kpiDelays.length-1)] + 'ms');
      fr.style.setProperty('--sc-dur','540ms');
      fr.classList.add('sc-enter');
    });
    var mainDelays = [280, 320, 360, 360, 360];
    d.querySelectorAll('[data-testid="stColumn"]').forEach(function(col, i) {
      col.style.opacity = '0';
      col.style.setProperty('--sc-dy','8px');
      col.style.setProperty('--sc-delay', mainDelays[Math.min(i, mainDelays.length-1)] + 'ms');
      col.style.setProperty('--sc-dur','560ms');
      col.classList.add('sc-enter');
    });
  }
  // Poll until sc-header is in the DOM (handles slow paints)
  var _entranceIv = setInterval(function() {
    applyEntrance();
    if (_entranceDone) clearInterval(_entranceIv);
  }, 80);
  setTimeout(function() { clearInterval(_entranceIv); }, 5000);  // give up after 5s

  // ── PILL NAV ──
  // Tab 3 label resolved after csmode attribute is set (may arrive slightly later)
  function getTab3Label() {
    return _doc.body.dataset.csmode === '1' ? 'Topic Analysis' : 'ROI Analysis';
  }
  var NAV_LABELS = ['Dashboard', 'Trends', null, 'Reports'];  // null = resolved at build time
  function buildNav() {
    var pill = _doc.getElementById('sc-nav-pill');
    var nativeTabs = _doc.querySelectorAll('button[data-baseweb="tab"]');
    if (!pill || nativeTabs.length < 4) return false;
    if (pill.dataset.built) return true;
    pill.innerHTML = '';
    NAV_LABELS.forEach(function(label, i) {
      var btn = _doc.createElement('button');
      btn.className = 'sc-tab' + (i === 0 ? ' sc-active' : '');
      btn.textContent = label !== null ? label : getTab3Label();
      btn.addEventListener('click', function() {
        _doc.querySelectorAll('#sc-nav-pill .sc-tab').forEach(function(b){ b.classList.remove('sc-active'); });
        btn.classList.add('sc-active');
        nativeTabs[i].click();
      });
      pill.appendChild(btn);
    });
    // Keep pill in sync when native tabs are clicked directly
    nativeTabs.forEach(function(tab, i) {
      tab.addEventListener('click', function() {
        _doc.querySelectorAll('#sc-nav-pill .sc-tab').forEach(function(b){ b.classList.remove('sc-active'); });
        var pillBtns = _doc.querySelectorAll('#sc-nav-pill .sc-tab');
        if (pillBtns[i]) pillBtns[i].classList.add('sc-active');
      });
    });
    pill.dataset.built = '1';
    return true;
  }
  var _navAttempts = 0;
  var _navIv = setInterval(function(){
    if (buildNav() || ++_navAttempts > 40) clearInterval(_navIv);
  }, 150);
})();
</script>
""", height=1, scrolling=False)
# pass cs_mode flag into the injector iframe via a data attribute on body
if cs_mode:
    st.components.v1.html("""
<script>
  if (window.parent) window.parent.document.body.dataset.csmode = '1';
</script>
""", height=0)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def fmt_k(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return f"{int(n):,}"


def _strip_plotly_size(h):
    """Replace Plotly's outer wrapper div inline height so CSS controls it."""
    return _re.sub(r'(<div) style="height:\d+px; width:100%;"', r'\1 style="width:100%;height:100%;"', h)


# Design-system colours used across all charts
_SC = dict(
    positive = "#F47A20",
    neutral  = "#C9C3BB",
    negative = "#3A3734",
    blue     = "#78A8D7",
    green    = "#55A88B",
    yellow   = "#E7B545",
    grid     = "#EEE9E2",
    axis_txt = "#756E66",
    font     = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif",
)
SENTIMENT_COLORS = {"Positive": _SC["positive"], "Neutral": _SC["neutral"], "Negative": _SC["negative"]}


def style_plotly(
    fig,
    height       = 320,
    margin       = None,
    show_legend  = False,
    legend_cfg   = None,
    hovermode    = "closest",
    xgrid        = False,
    ygrid        = True,
    xangle       = 0,
    xtickfmt     = None,
    ytickfmt     = None,
    xtickpfx     = "",
    ytickpfx     = "",
    x_title      = "",
    y_title      = "",
    x_range      = None,
    bargap       = None,
):
    """Apply the Sensecap design-system style to any Plotly figure.

    All charts share: transparent backgrounds, Inter font, muted axis labels,
    #EEE9E2 gridlines at 0.6px, no zero-lines, no axis borders, no modebar.
    Chart-specific overrides (height, margins, legend, axis formats) are
    passed as arguments so every call site stays minimal.
    """
    m = margin or dict(l=40, r=16, t=8, b=44)

    # ── base layout ──────────────────────────────────────────────────────────
    fig.update_layout(
        height           = height,
        margin           = m,
        paper_bgcolor    = "rgba(0,0,0,0)",
        plot_bgcolor     = "rgba(0,0,0,0)",
        font             = dict(family=_SC["font"], size=11, color=_SC["axis_txt"]),
        showlegend       = show_legend,
        hovermode        = hovermode,
        hoverlabel       = dict(
            bgcolor      = "#fff",
            bordercolor  = "#E9E3DA",
            font_size    = 12,
            font_family  = _SC["font"],
            font_color   = "#26221F",
        ),
        **(dict(bargap=bargap) if bargap is not None else {}),
    )
    if show_legend and legend_cfg:
        fig.update_layout(legend=legend_cfg)
    elif show_legend:
        fig.update_layout(legend=dict(
            orientation  = "h",
            y            = 1.08,
            x            = 0,
            xanchor      = "left",
            title_text   = "",
            font         = dict(size=11, color=_SC["axis_txt"]),
            tracegroupgap= 0,
            itemsizing   = "constant",
            bgcolor      = "rgba(0,0,0,0)",
            borderwidth  = 0,
        ))

    # ── x-axis ───────────────────────────────────────────────────────────────
    xkw = dict(
        showgrid      = xgrid,
        gridcolor     = _SC["grid"],
        gridwidth     = 0.6,
        zeroline      = False,
        showline      = False,
        tickfont      = dict(size=10, color=_SC["axis_txt"]),
        title_text    = x_title,
        title_font    = dict(size=11, color=_SC["axis_txt"]),
        tickangle     = xangle,
        tickprefix    = xtickpfx,
        automargin    = True,
    )
    if xtickfmt: xkw["tickformat"] = xtickfmt
    if x_range:  xkw["range"]      = x_range
    fig.update_xaxes(**xkw)

    # ── y-axis ───────────────────────────────────────────────────────────────
    ykw = dict(
        showgrid      = ygrid,
        gridcolor     = _SC["grid"],
        gridwidth     = 0.6,
        zeroline      = False,
        showline      = False,
        tickfont      = dict(size=10, color=_SC["axis_txt"]),
        title_text    = y_title,
        title_font    = dict(size=11, color=_SC["axis_txt"]),
        tickprefix    = ytickpfx,
        automargin    = True,
    )
    if ytickfmt: ykw["tickformat"] = ytickfmt
    fig.update_yaxes(**ykw)

    return fig


# -----------------------------------------------------------------------------
# Top header — brand left, custom pill nav centre, avatars + icons right
# -----------------------------------------------------------------------------
# Static header CSS — plain string, no f-prefix, no brace-escaping needed
st.markdown("""
<style>
#sc-header {
  display: flex; align-items: center; justify-content: space-between;
  height: 64px; padding: 0; border-bottom: 1px solid #E9E3DA;
  margin-bottom: 20px; min-width: 0; gap: 8px;
}
.sc-hd-brand { display: flex; align-items: center; gap: 10px; flex-shrink: 0; min-width: 0; }
.sc-hd-brand-name { font-size: 20px; font-weight: 740; letter-spacing: -.45px; color: #D85E16; white-space: nowrap; }
.sc-hd-nav-wrap { flex: 1 1 auto; min-width: 0; display: flex; justify-content: center; overflow: hidden; }
#sc-nav-pill {
  display: flex; align-items: center; background: #ECE9E4; border-radius: 999px;
  padding: 3px; gap: 2px; overflow-x: auto; -webkit-overflow-scrolling: touch;
  scrollbar-width: none; max-width: 100%;
}
#sc-nav-pill::-webkit-scrollbar { display: none; }
.sc-hd-right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.sc-hd-avatars { display: flex; align-items: center; }
.sc-hd-bell {
  margin-left: 8px; width: 34px; height: 34px; border-radius: 50%; background: #3A3734;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0;
}
.sc-hd-menu {
  width: 34px; height: 34px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0;
}
@media(max-width:1024px) { .sc-hd-brand-name { font-size: 17px; } #sc-header { height: 56px; } }
@media(max-width:768px) {
  .sc-hd-avatars { display: none !important; }
  .sc-hd-brand-name { font-size: 16px; letter-spacing: -.3px; }
  #sc-header { height: 52px; margin-bottom: 12px; }
  .sc-hd-bell { margin-left: 4px; }
}
@media(max-width:480px) { .sc-hd-bell { display: none !important; } .sc-hd-brand-name { font-size: 15px; } #sc-header { height: 48px; } }
@media(max-width:390px) { .sc-hd-brand-name { font-size: 14px; letter-spacing: -.2px; } #sc-header { height: 46px; gap: 6px; } }
</style>
""", unsafe_allow_html=True)

# Header HTML — f-string only for the dynamic badge expression
st.markdown(f"""
<div id="sc-header">
  <div class="sc-hd-brand">
    <span style="width:28px;height:28px;border-radius:50%;background:#F47A20;display:inline-flex;align-items:center;justify-content:center;box-shadow:0 2px 10px rgba(244,122,32,.32);flex-shrink:0;">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><circle cx="5" cy="5" r="3.5" stroke="white" stroke-width="2"/></svg>
    </span>
    <span class="sc-hd-brand-name">Sensecap</span>
  </div>
  {'<div style="display:flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;background:#EEF6FF;border:1px solid #BDD7F5;font-size:11px;font-weight:600;color:#2563EB;flex-shrink:0;white-space:nowrap;"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> Powered by ClipSense</div>' if cs_mode else ''}
  <div class="sc-hd-nav-wrap"><div id="sc-nav-pill"></div></div>
  <div class="sc-hd-right">
    <div class="sc-hd-avatars">
      <span style="width:30px;height:30px;border-radius:50%;background:#E8E2DB;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#615A52;border:2px solid #F8F6F1;z-index:4;">AR</span>
      <span style="width:30px;height:30px;border-radius:50%;background:#D8E0E7;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#615A52;border:2px solid #F8F6F1;margin-left:-7px;z-index:3;">SK</span>
      <span style="width:30px;height:30px;border-radius:50%;background:#E6D6C8;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#615A52;border:2px solid #F8F6F1;margin-left:-7px;z-index:2;">MN</span>
      <span style="width:30px;height:30px;border-radius:50%;background:#F47A20;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;border:2px solid #F8F6F1;margin-left:-7px;z-index:1;">+2</span>
    </div>
    <span class="sc-hd-bell">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
    </span>
    <span class="sc-hd-menu">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5F5850" stroke-width="2" stroke-linecap="round">
        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# Tabs rendered by Streamlit (must be a widget, not HTML)
tabs = st.tabs(["  Dashboard  ", "  Trends  ", "  ROI Analysis  ", "  Reports  "])


# Filter bar hidden — filtering handled per-chart via Plotly interactivity
platforms = sorted(df["platform"].dropna().unique())
regions   = sorted(df["region"].dropna().unique())
themes    = sorted(df["theme"].dropna().unique())
dmin, dmax = df["timestamp"].min().date(), df["timestamp"].max().date()
selected_platforms = platforms
selected_regions   = regions
selected_themes    = themes
date_range         = (dmin, dmax)

mask = df["platform"].isin(selected_platforms) & df["region"].isin(selected_regions) & df["theme"].isin(selected_themes)
if isinstance(date_range, tuple) and len(date_range) == 2:
    mask &= (df["timestamp"].dt.date >= date_range[0]) & (df["timestamp"].dt.date <= date_range[1])
fdf = df[mask].copy()
if fdf.empty:
    st.warning("No mentions match the current filters.")
    st.stop()

# -----------------------------------------------------------------------------
# DASHBOARD TAB
# -----------------------------------------------------------------------------
with tabs[0]:
    total          = len(fdf)
    positive       = (fdf["sentiment_label"] == "Positive").mean() * 100
    active_regions = fdf["country"].nunique()
    engagement     = fdf["engagement"].sum()

    # Page title
    st.markdown(
        f"""
        <div class='title-row'>
          <div>
            <div class='pg-title'>Customer Sentiment</div>
            <div class='pg-sub'>Across connected social media accounts</div>
          </div>
          <div class='pg-badge'>Updated {datetime.now().strftime('%b %d, %Y')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI strip — single components.html for full styling control ─────────
    num_platforms = fdf["platform"].nunique()
    _pos_raw = positive
    _tot_raw = total
    _icon_sentiment = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>'
    _icon_mentions  = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    if cs_mode:
        _kpi3_label = "Video Segments"
        _kpi3_raw   = total
        _kpi3_fmt   = "function(v){ return Math.round(v).toString(); }"
        _kpi3_meta  = "Feedback segments analysed"
        _kpi3_icon  = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>'
        avg_conf    = float(fdf["confidence"].mean()) * 100 if "confidence" in fdf.columns else 0.0
        _kpi4_label = "Avg Confidence"
        _kpi4_raw   = avg_conf
        _kpi4_fmt   = "function(v){ return v.toFixed(1) + '%'; }"
        _kpi4_meta  = "Model confidence score"
        _kpi4_icon  = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
    else:
        _kpi3_label = "Active Regions"
        _kpi3_raw   = active_regions
        _kpi3_fmt   = "function(v){ return Math.round(v).toString(); }"
        _kpi3_meta  = "Global coverage"
        _kpi3_icon  = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
        _kpi4_label = "Total Engagement"
        _kpi4_raw   = int(engagement)
        _kpi4_fmt   = "function(v){ v=Math.round(v); if(v>=1000000) return (v/1000000).toFixed(1)+'M'; if(v>=1000) return (v/1000).toFixed(1)+'K'; return v.toLocaleString(); }"
        _kpi4_meta  = "Likes + shares + replies"
        _kpi4_icon  = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8C0B8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>'

    components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:transparent;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden;height:auto}}

  /* ── 4-column grid — default (1024+) ── */
  .strip{{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:16px;
  }}
  .kc{{
    background:#fff;
    border:1px solid #E9E3DA;
    border-radius:15px;
    padding:20px 22px 18px;
    min-height:108px;
    box-shadow:0 2px 8px rgba(50,40,30,.035);
    display:flex;
    flex-direction:column;
    justify-content:space-between;
    transition:box-shadow 220ms ease;
    cursor:default;
  }}
  .kc:hover{{
    box-shadow:0 6px 20px rgba(50,40,30,.09);
  }}
  .kc-top{{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
  }}
  .kc-label{{
    font-size:10px;
    font-weight:600;
    letter-spacing:.65px;
    text-transform:uppercase;
    color:#91887E;
    line-height:1;
  }}
  .kc-icon{{
    flex-shrink:0;
    opacity:.85;
    margin-top:-1px;
  }}
  .kc-value{{
    font-size:34px;
    font-weight:720;
    letter-spacing:-1.2px;
    line-height:1;
    color:#26221F;
    margin-top:10px;
  }}
  .kc-value.accent{{ color:#F47A20; }}
  .kc-meta{{
    font-size:11px;
    font-weight:400;
    color:#91887E;
    margin-top:6px;
    line-height:1.4;
  }}
  .kc-meta .up{{ color:#55A88B; font-weight:600; }}

  /* ── ≤1280 : tighten card padding slightly ── */
  @media(max-width:1280px){{
    .strip{{ gap:12px; }}
    .kc{{ padding:17px 18px 15px; min-height:100px; }}
    .kc-value{{ font-size:30px; }}
  }}

  /* ── ≤1024 : 2×2 grid ── */
  @media(max-width:1024px){{
    .strip{{
      grid-template-columns:repeat(2,1fr);
      gap:12px;
    }}
    .kc{{ padding:16px 18px 14px; min-height:96px; }}
    .kc-value{{ font-size:28px; letter-spacing:-1px; }}
  }}

  /* ── ≤768 : 2×2 grid, reduced sizes ── */
  @media(max-width:768px){{
    .strip{{
      grid-template-columns:repeat(2,1fr);
      gap:10px;
    }}
    .kc{{ padding:14px 15px 12px; min-height:88px; border-radius:12px; }}
    .kc-value{{ font-size:26px; letter-spacing:-.9px; margin-top:8px; }}
    .kc-label{{ font-size:9.5px; letter-spacing:.5px; }}
    .kc-meta{{ font-size:10px; margin-top:5px; }}
  }}

  /* ── ≤480 : 2×2 grid, compact ── */
  @media(max-width:480px){{
    .strip{{ gap:8px; }}
    .kc{{ padding:12px 13px 10px; min-height:80px; border-radius:11px; }}
    .kc-value{{ font-size:24px; letter-spacing:-.8px; }}
    .kc-label{{ font-size:9px; letter-spacing:.4px; }}
    .kc-meta{{ font-size:9.5px; }}
    .kc-icon{{ display:none; }}
  }}

  /* ── ≤390 : 2×2 grid, minimum ── */
  @media(max-width:390px){{
    .strip{{ gap:7px; }}
    .kc{{ padding:11px 12px 9px; min-height:74px; border-radius:10px; }}
    .kc-value{{ font-size:22px; letter-spacing:-.7px; }}
    .kc-meta{{ display:none; }}
  }}
</style>

<div class="strip">

  <!-- Overall Sentiment -->
  <div class="kc">
    <div class="kc-top">
      <div class="kc-label">Overall Sentiment</div>
      <div class="kc-icon">{_icon_sentiment}</div>
    </div>
    <div class="kc-value accent" id="v0">—</div>
    <div class="kc-meta"><span class="up">↑ 4.8%</span> vs previous period</div>
  </div>

  <!-- Total Mentions / Segments -->
  <div class="kc">
    <div class="kc-top">
      <div class="kc-label">{'Feedback Segments' if cs_mode else 'Total Mentions'}</div>
      <div class="kc-icon">{_icon_mentions}</div>
    </div>
    <div class="kc-value" id="v1">—</div>
    <div class="kc-meta">{'From ClipSense analysis' if cs_mode else f'Across {num_platforms} platform{"s" if num_platforms != 1 else ""}'}</div>
  </div>

  <!-- KPI 3 -->
  <div class="kc">
    <div class="kc-top">
      <div class="kc-label">{_kpi3_label}</div>
      <div class="kc-icon">{_kpi3_icon}</div>
    </div>
    <div class="kc-value" id="v2">—</div>
    <div class="kc-meta">{_kpi3_meta}</div>
  </div>

  <!-- KPI 4 -->
  <div class="kc">
    <div class="kc-top">
      <div class="kc-label">{_kpi4_label}</div>
      <div class="kc-icon">{_kpi4_icon}</div>
    </div>
    <div class="kc-value" id="v3">—</div>
    <div class="kc-meta">{_kpi4_meta}</div>
  </div>

</div>

<script>
(function(){{
  var DURATION = 900;
  var cards = [
    {{ el: document.getElementById('v0'), end: {_pos_raw:.1f}, fmt: function(v){{ return v.toFixed(1) + '%'; }} }},
    {{ el: document.getElementById('v1'), end: {_tot_raw},     fmt: function(v){{
      v = Math.round(v);
      if(v>=1000000) return (v/1000000).toFixed(1)+'M';
      if(v>=1000)    return (v/1000).toFixed(1)+'K';
      return v.toLocaleString();
    }} }},
    {{ el: document.getElementById('v2'), end: {_kpi3_raw}, fmt: {_kpi3_fmt} }},
    {{ el: document.getElementById('v3'), end: {_kpi4_raw}, fmt: {_kpi4_fmt} }},
  ];
  var start = null;
  function ease(t){{ return t<.5 ? 2*t*t : -1+(4-2*t)*t; }}
  function step(ts){{
    if(!start) start = ts;
    var p = Math.min((ts-start)/DURATION, 1);
    var e = ease(p);
    cards.forEach(function(c){{ c.el.textContent = c.fmt(e * c.end); }});
    if(p < 1) requestAnimationFrame(step);
  }}
  requestAnimationFrame(step);
}})();
</script>
<script>
  function fitHeight() {{
    var h = document.body.scrollHeight;
    if (window.parent && window.frameElement) {{
      window.frameElement.style.height = h + 'px';
    }}
  }}
  setTimeout(fitHeight, 950);
  window.addEventListener('resize', fitHeight);
  fitHeight();
</script>
    """, height=240, scrolling=False)

    # ── Hero row: map card (left) + AI insight card (right) ──────────────────
    left, right = st.columns([2.2, 1.0], gap="medium")

    # geographic aggregation
    for _geo_col, _geo_val in [("lat", 0.0), ("lon", 0.0)]:
        if _geo_col not in fdf.columns:
            fdf[_geo_col] = _geo_val
    reg = (
        fdf.groupby(["country", "country_code", "lat", "lon"], dropna=False)
        .agg(
            mentions=("sentiment_label", "size"),
            positive=("sentiment_label", lambda s: (s == "Positive").mean() * 100),
        )
        .reset_index()
    )
    reg["country_code"] = reg["country_code"].astype(str).str.upper().str.strip()
    reg = reg[reg["country_code"].str.fullmatch(r"[A-Z]{3}")].copy()
    reg["lat"] = pd.to_numeric(reg["lat"], errors="coerce")
    reg["lon"] = pd.to_numeric(reg["lon"], errors="coerce")
    reg = reg.dropna(subset=["lat", "lon"])

    region_stats = (
        fdf.groupby("region")
        .agg(mentions=("sentiment_label", "size"),
             positive=("sentiment_label", lambda s: (s == "Positive").mean() * 100))
        .reset_index()
        .sort_values(["positive", "mentions"], ascending=[False, False])
    )
    top_regions = region_stats.head(5)

    # map figure — premium editorial treatment
    fig_map = go.Figure()
    if not reg.empty:
        fig_map.add_trace(go.Choropleth(
            locations=reg["country_code"], z=reg["positive"],
            locationmode="ISO-3",
            colorscale=[
                [0.0,  "#C2622A"],
                [0.25, "#D06B28"],
                [0.50, "#E07820"],
                [0.75, "#EF8B1A"],
                [1.0,  "#FAA012"],
            ],
            zmin=0, zmax=100, showscale=False,
            marker_line_color="rgba(180,80,10,.55)", marker_line_width=0.5,
            customdata=reg[["country","mentions","positive"]].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]:,} mentions<br>"
                "%{customdata[2]:.1f}% positive"
                "<extra></extra>"
            ),
        ))
        fig_map.add_trace(go.Scattergeo(
            lon=reg["lon"], lat=reg["lat"], mode="markers",
            marker=dict(
                size=np.clip(np.sqrt(reg["mentions"]) * 1.1, 5, 13),
                color="rgba(255,255,255,.92)",
                line=dict(color="rgba(255,200,120,.6)", width=1.5),
                symbol="circle",
            ),
            customdata=reg[["country","mentions","positive"]].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]:,} mentions<br>"
                "%{customdata[2]:.1f}% positive"
                "<extra></extra>"
            ),
            showlegend=False,
        ))
    fig_map.update_geos(
        scope="world", projection_type="natural earth", showframe=False,
        showcoastlines=False,
        showcountries=True, countrycolor="rgba(160,65,8,.45)",
        showland=True, landcolor="#B85A18",
        showocean=True, oceancolor="#C05510",
        showlakes=False, bgcolor="rgba(0,0,0,0)",
        lonaxis=dict(showgrid=False, range=[-160, 175]),
        lataxis=dict(showgrid=False, range=[-55, 80]),
    )
    fig_map.update_layout(
        height=310, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        geo=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(
            bgcolor="#fff", bordercolor="#E9E3DA",
            font_size=12, font_family=_SC["font"], font_color="#26221F",
        ),
    )
    map_html = fig_map.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "scrollZoom": False, "responsive": True}
    )

    top_region_html = "".join(
        f"<div class='rr'>"
        f"<span class='rn'>{html.escape(str(r.region))}</span>"
        f"<div class='rb-wrap'><div class='rb'><div class='rf' style='--w:{max(3,min(100,float(r.positive))):.1f}%'></div></div></div>"
        f"<span class='rpct'>{r.positive:.0f}%</span></div>"
        for r in top_regions.itertuples(index=False)
    )

    pos_count = int((fdf["sentiment_label"] == "Positive").sum())

    with left:
        st.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:transparent;font-family:Inter,-apple-system,sans-serif;color:#fff;overflow:hidden}}

  .card{{
    min-height:600px;
    border-radius:20px;
    overflow:hidden;
    position:relative;
    padding:24px 26px 22px;
    background:
      radial-gradient(ellipse at 15% 0%,   rgba(255,180,80,.18) 0, transparent 45%),
      radial-gradient(ellipse at 90% 85%,  rgba(160,40,0,.35)   0, transparent 50%),
      linear-gradient(158deg, #F68A22 0%, #F47A20 38%, #E06018 68%, #C85010 100%);
    box-shadow: 0 8px 32px rgba(180,70,10,.18), 0 1px 0 rgba(255,200,100,.12) inset;
    display:flex;
    flex-direction:column;
  }}

  /* subtle dot-grid texture — removed, adds noise without information */

  /* header */
  .head{{position:relative;z-index:3;flex-shrink:0}}
  .kicker{{
    font-size:10px;font-weight:600;letter-spacing:1.2px;
    text-transform:uppercase;opacity:.72;
  }}
  .ttl{{
    font-size:21px;font-weight:700;margin-top:4px;letter-spacing:-.45px;line-height:1.1;
  }}
  .meta{{
    font-size:11px;font-weight:400;opacity:.65;margin-top:4px;
  }}

  /* map container */
  .mapwrap{{
    position:relative;z-index:2;
    flex:1;min-height:0;
    margin:14px -6px 0;
    border-radius:12px;
    overflow:hidden;
  }}
  .mapwrap .js-plotly-plot,
  .mapwrap .plot-container{{
    width:100%!important;
    height:100%!important;
  }}

  /* pulse rings on scatter markers — CSS only, fires once */
  @keyframes pulse{{
    0%  {{ transform:scale(1);   opacity:.7 }}
    60% {{ transform:scale(2.4); opacity:0  }}
    100%{{ transform:scale(2.4); opacity:0  }}
  }}
  .marker-pulse{{
    position:absolute;
    width:10px;height:10px;
    border-radius:50%;
    background:rgba(255,255,255,.55);
    animation:pulse 3s ease-out infinite;
    pointer-events:none;
  }}

  /* divider */
  .sep{{height:1px;background:rgba(255,255,255,.14);margin:14px 0 10px;flex-shrink:0;position:relative;z-index:3}}

  /* region rows */
  .regions{{position:relative;z-index:3;flex-shrink:0}}
  .rr{{
    display:grid;
    grid-template-columns:110px 1fr 42px;
    align-items:center;
    gap:10px;
    padding:5px 0;
  }}
  .rr+.rr{{border-top:1px solid rgba(255,255,255,.09)}}
  .rn{{font-size:11px;font-weight:500;opacity:.9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .rb-wrap{{position:relative}}
  .rb{{
    height:5px;border-radius:5px;
    background:rgba(255,255,255,.16);
    overflow:hidden;
  }}
  .rf{{
    height:100%;border-radius:5px;
    background:rgba(255,255,255,.88);
    width:0;
    animation:barGrow 900ms cubic-bezier(.22,.61,.36,1) forwards;
    animation-delay:200ms;
  }}
  @keyframes barGrow{{to{{width:var(--w)}}}}
  .rpct{{font-size:11px;font-weight:640;text-align:right;opacity:.95}}

  /* ── ≤1280 : slightly shorter card ── */
  @media(max-width:1280px){{
    .card{{min-height:480px;padding:20px 22px 18px}}
  }}

  /* ── ≤1024 : compact card, narrow region label ── */
  @media(max-width:1024px){{
    .card{{min-height:400px;padding:18px 18px 16px}}
    .rr{{grid-template-columns:80px 1fr 38px;gap:8px}}
    .ttl{{font-size:18px}}
  }}

  /* ── ≤768 : stacked full-width, restore comfortable height ── */
  @media(max-width:768px){{
    .card{{min-height:360px;padding:16px 16px 14px}}
    .rr{{grid-template-columns:80px 1fr 36px;gap:7px}}
    .ttl{{font-size:17px}}
    .meta{{font-size:10px}}
  }}
</style>

<div class='card'>
  <div class='head'>
    <div class='kicker'>Global Sentiment</div>
    <div class='ttl'>Top regions by sentiment</div>
    <div class='meta'>{active_regions} active regions &nbsp;·&nbsp; {pos_count:,} positive mentions</div>
  </div>

  <div class='mapwrap'>{map_html}</div>

  <div class='sep'></div>

  <div class='regions'>{top_region_html}</div>
</div>
        """)

    with right:
        # ── dynamic insight values ────────────────────────────────────────────
        top_theme    = fdf["theme"].value_counts().idxmax()
        top_platform = fdf["platform"].value_counts().idxmax()
        if positive >= 65:
            headline = "Sentiment is rising."
        elif positive >= 45:
            headline = "Sentiment is mixed."
        else:
            headline = "Sentiment is declining."
        sub_line = (
            f"{positive:.1f}% positive across {fmt_k(total)} mentions."
        )
        st.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    background:transparent;
    font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    overflow:hidden;
  }}

  /* ── card shell ── */
  .card{{
    min-height:600px;
    border-radius:20px;
    overflow:hidden;
    position:relative;
    color:#fff;
    padding:26px 24px 24px;
    background:linear-gradient(135deg,#F7A33C 0%,#F16D27 52%,#D9573D 100%);
    box-shadow:0 8px 28px rgba(200,70,20,.20), 0 1px 0 rgba(255,210,130,.14) inset;
    display:flex;
    flex-direction:column;
    transition:transform 260ms ease, box-shadow 260ms ease;
    cursor:default;
  }}
  .card:hover{{
    box-shadow:0 12px 36px rgba(200,70,20,.26), 0 1px 0 rgba(255,210,130,.14) inset;
  }}

  /* ── dot-grid texture removed — adds noise without information —— */

  /* ── rings: static, no animation — structural depth only ── */
  .ring1{{
    position:absolute;
    top:-70px; right:-70px;
    width:260px; height:260px;
    border-radius:50%;
    border:1px solid rgba(255,255,255,.10);
    pointer-events:none;
    z-index:0;
  }}

  /* ── ring 2 (bottom-left) ── */
  .ring2{{
    position:absolute;
    bottom:-90px; left:-60px;
    width:200px; height:200px;
    border-radius:50%;
    border:1px solid rgba(255,255,255,.06);
    pointer-events:none;
    z-index:0;
  }}

  /* ── content layers ── */
  .z{{position:relative;z-index:2}}

  .kicker{{
    font-size:10px;font-weight:600;
    letter-spacing:1.2px;text-transform:uppercase;
    opacity:.72;
  }}

  .spacer{{flex:1;min-height:20px}}

  .headline{{
    font-size:30px;font-weight:740;
    line-height:1.05;letter-spacing:-.8px;
    margin-top:0;
  }}

  .subline{{
    font-size:12px;font-weight:400;
    line-height:1.6;opacity:.88;
    margin-top:10px;
  }}

  .detail-block{{
    margin-top:14px;
    display:flex;flex-direction:column;gap:6px;
  }}
  .detail-row{{
    display:flex;align-items:baseline;gap:6px;
    font-size:11px;font-weight:400;opacity:.82;
  }}
  .detail-label{{
    opacity:.65;white-space:nowrap;
  }}
  .detail-val{{
    font-weight:640;opacity:1;
  }}

  .sep{{
    height:1px;
    background:rgba(255,255,255,.18);
    margin:18px 0 16px;
    flex-shrink:0;
  }}

  .stat-row{{
    display:flex;gap:0;flex-shrink:0;
  }}
  .stat{{
    flex:1;
    display:flex;flex-direction:column;gap:3px;
  }}
  .stat+.stat{{
    border-left:1px solid rgba(255,255,255,.15);
    padding-left:14px;
  }}
  .stat-val{{
    font-size:22px;font-weight:720;letter-spacing:-.6px;line-height:1;
  }}
  .stat-lbl{{
    font-size:9px;font-weight:600;
    letter-spacing:.5px;text-transform:uppercase;
    opacity:.65;margin-top:3px;
  }}

  .cta{{
    margin-top:18px;
    display:inline-flex;align-items:center;gap:8px;
    align-self:flex-start;
    border:1px solid rgba(255,255,255,.38);
    border-radius:999px;
    padding:9px 18px;
    font-size:11px;font-weight:600;
    background:rgba(255,255,255,.09);
    cursor:pointer;
    transition:background 240ms ease, border-color 240ms ease;
    flex-shrink:0;
  }}
  .cta:hover{{
    background:rgba(255,255,255,.18);
    border-color:rgba(255,255,255,.55);
  }}

  /* ── ≤1280 : slightly shorter card ── */
  @media(max-width:1280px){{
    .card{{min-height:480px;padding:22px 20px 20px}}
    .headline{{font-size:24px;letter-spacing:-.6px}}
  }}

  /* ── ≤1024 : compact card ── */
  @media(max-width:1024px){{
    .card{{min-height:400px;padding:18px 18px 16px}}
    .headline{{font-size:20px;letter-spacing:-.4px}}
    .subline{{font-size:11px;margin-top:8px}}
    .stat-val{{font-size:19px}}
  }}

  /* ── ≤768 : stacked full-width ── */
  @media(max-width:768px){{
    .card{{min-height:340px;padding:16px 16px 14px}}
    .headline{{font-size:20px}}
    .sep{{margin:14px 0 12px}}
  }}
</style>

<div class='card'>
  <div class='ring1'></div>
  <div class='ring2'></div>

  <div class='kicker z'>AI Overall Analysis</div>

  <div class='spacer'></div>

  <div class='headline z'>{html.escape(headline)}</div>
  <div class='subline z'>{html.escape(sub_line)}</div>

  <div class='detail-block z'>
    <div class='detail-row'>
      <span class='detail-label'>Most discussed aspect</span>
      <span class='detail-val'>{html.escape(str(top_theme))}</span>
    </div>
    <div class='detail-row'>
      <span class='detail-label'>Busiest platform</span>
      <span class='detail-val'>{html.escape(str(top_platform))}</span>
    </div>
  </div>

  <div class='sep z'></div>

  <div class='stat-row z'>
    <div class='stat'>
      <div class='stat-val'>{fmt_k(total)}</div>
      <div class='stat-lbl'>Mentions</div>
    </div>
    <div class='stat'>
      <div class='stat-val'>{active_regions}</div>
      <div class='stat-lbl'>Regions</div>
    </div>
    <div class='stat'>
      <div class='stat-val'>{positive:.0f}%</div>
      <div class='stat-lbl'>Positive</div>
    </div>
  </div>

  <div class='cta z'>View detailed analysis &rarr;</div>
</div>
        """)

    st.markdown("<div style='height:20px;line-height:0'>&nbsp;</div>", unsafe_allow_html=True)

    # ── Bottom 3 cards ───────────────────────────────────────────────────────
    # ── Build bottom card data before rendering ──────────────────────────────
    for _col, _val in [("roi_driver", "Brand Value"), ("roi_value_usd", 0.0)]:
        if _col not in fdf.columns:
            fdf[_col] = _val
    roi_df    = fdf.groupby("roi_driver")["roi_value_usd"].sum().reset_index().sort_values("roi_value_usd", ascending=False)
    total_roi = fdf["roi_value_usd"].sum()
    donut_colors = [_SC["positive"], _SC["blue"], _SC["green"], _SC["yellow"]]

    # Donut chart HTML
    fig_roi = go.Figure(go.Pie(
        labels=roi_df["roi_driver"], values=roi_df["roi_value_usd"],
        hole=0.68,
        marker=dict(colors=donut_colors[:len(roi_df)], line=dict(color="#fff", width=2)),
        textposition="none",
        hovertemplate="<b>%{label}</b><br>$%{value:,.0f} &nbsp;·&nbsp; %{percent}<extra></extra>",
        sort=False,
    ))
    center_label = fmt_k(total_roi) if total_roi >= 1000 else f"${total_roi:,.0f}"
    fig_roi.update_layout(
        height=220, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="#fff", bordercolor="#E9E3DA",
                        font_size=12, font_family=_SC["font"], font_color="#26221F"),
        annotations=[dict(
            text=f"<b>{center_label}</b><br><span style='font-size:10px'>Projected impact</span>",
            x=0.5, y=0.5, showarrow=False, align="center",
            font=dict(size=14, color=TEXT, family=_SC["font"]),
        )],
    )
    donut_html = _strip_plotly_size(fig_roi.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True}
    ))

    # Donut legend rows
    donut_leg = ""
    for i, row in roi_df.iterrows():
        pct   = row["roi_value_usd"] / total_roi * 100 if total_roi else 0
        color = donut_colors[int(i) % 4]
        donut_leg += (
            f"<div class='leg-row'>"
            f"<span class='leg-left'><span class='leg-dot' style='background:{color}'></span>"
            f"{html.escape(str(row['roi_driver']))}</span>"
            f"<span><b>${row['roi_value_usd']:,.0f}</b> "
            f"<span class='leg-pct'>({pct:.0f}%)</span></span></div>"
        )

    # Word cloud — render to base64 PNG
    text_blob = " ".join(fdf["text"].astype(str))
    wc_b64 = ""
    if text_blob.strip():
        wc_img = WordCloud(
            width=1200, height=480, background_color=None, mode="RGBA",
            stopwords=STOPWORDS,
            color_func=lambda *a, **kw: np.random.choice(
                ["#F47A20","#D85E16","#F68A22","#3A3734","#BDB8B1","#E07020"]
            ),
            prefer_horizontal=0.82, random_state=42, max_words=140,
            margin=2, collocations=False,
        ).generate(text_blob)
        figw, ax = plt.subplots(figsize=(12, 4.8), dpi=110)
        figw.patch.set_alpha(0)
        ax.imshow(wc_img, interpolation="bilinear")
        ax.axis("off")
        figw.subplots_adjust(0, 0, 1, 1)
        buf = io.BytesIO()
        figw.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.02)
        plt.close(figw)
        wc_b64 = base64.b64encode(buf.getvalue()).decode()

    # Weekly mentions chart HTML
    tmp = fdf.copy()
    tmp["week"] = tmp["timestamp"].dt.to_period("W").apply(lambda p: p.start_time)
    weekly = tmp.groupby(["week", "sentiment_label"]).size().reset_index(name="count")
    fig_week = px.bar(weekly, x="week", y="count",
                      color="sentiment_label", barmode="stack",
                      color_discrete_map=SENTIMENT_COLORS)
    style_plotly(fig_week, height=240, margin=dict(l=36, r=8, t=4, b=48),
                 hovermode="x unified", xangle=-30, bargap=0.22)
    week_html = _strip_plotly_size(fig_week.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True}
    ))

    # Weekly legend
    week_leg = ""
    for lbl, col in [("Positive", ORANGE), ("Neutral", GRAY), ("Negative", DARK)]:
        n = int((fdf["sentiment_label"] == lbl).sum())
        week_leg += (
            f"<span class='wleg-item'>"
            f"<span class='wleg-dot' style='background:{col}'></span>"
            f"{lbl} <b>{fmt_k(n)}</b></span>"
        )

    # ── Shared card CSS ───────────────────────────────────────────────────────
    _card_css = f"""
      *{{box-sizing:border-box;margin:0;padding:0}}
      html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
      .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
             padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);
             display:flex;flex-direction:column;overflow:hidden;}}
      .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
      .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
      .divider{{height:1px;background:{BORDER};margin:12px 0 10px;flex-shrink:0}}
      .plot-wrap{{width:100%;height:240px;overflow:hidden;flex-shrink:0}}
      .plot-wrap>div{{width:100%!important;height:100%!important;}}
      @media(max-width:1024px){{.plot-wrap{{height:200px;}}}}
      @media(max-width:768px){{.plot-wrap{{height:180px;}}}}
      @media(max-width:480px){{.plot-wrap{{height:160px;}}}}
    """

    b1, b2, b3 = st.columns(3, gap="medium")

    # ── ROI BREAKDOWN ────────────────────────────────────────────────────────
    with b1:
        components.html(f"""
<style>
  {_card_css}
  .leg-row{{display:flex;align-items:center;justify-content:space-between;
            font-size:11px;color:{MUTED};padding:5px 0;border-top:1px solid {BORDER};}}
  .leg-left{{display:flex;align-items:center;gap:7px;}}
  .leg-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
  .leg-row b{{color:{TEXT};}}
  .leg-pct{{color:{MUTED};}}
</style>
<div class="card">
  <div class="title">ROI Breakdown</div>
  <div class="sub">Estimated contribution by driver</div>
  <div class="divider"></div>
  <div class="plot-wrap">{donut_html}</div>
  {donut_leg}
</div>""", height=520, scrolling=False)

    # ── WORD CLOUD ───────────────────────────────────────────────────────────
    with b2:
        wc_content = (
            f"<img src='data:image/png;base64,{wc_b64}' "
            f"style='width:100%;height:auto;display:block;border-radius:8px;' alt='Word cloud'>"
            if wc_b64 else
            f"<div style='height:200px;display:flex;align-items:center;"
            f"justify-content:center;color:{MUTED};font-size:13px;'>Not enough text data</div>"
        )
        components.html(f"""
<style>
  {_card_css}
  .img-wrap{{width:100%;overflow:hidden;border-radius:8px;}}
</style>
<div class="card">
  <div class="title">Word Cloud</div>
  <div class="sub">Most frequent audience language</div>
  <div class="divider"></div>
  <div class="img-wrap">{wc_content}</div>
</div>""", height=520, scrolling=False)

    # ── WEEKLY MENTIONS ──────────────────────────────────────────────────────
    with b3:
        components.html(f"""
<style>
  {_card_css}
  .wleg{{display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;}}
  .wleg-item{{display:flex;align-items:center;gap:5px;font-size:11px;color:{MUTED};}}
  .wleg-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
  .wleg-item b{{color:{TEXT};}}
</style>
<div class="card">
  <div class="title">Weekly Mentions</div>
  <div class="sub">Stacked by sentiment</div>
  <div class="divider"></div>
  <div class="plot-wrap">{week_html}</div>
  <div class="wleg">{week_leg}</div>
</div>""", height=520, scrolling=False)

# -----------------------------------------------------------------------------
# TRENDS TAB
# -----------------------------------------------------------------------------
with tabs[1]:
    st.markdown(
        "<div class='title-row'><div><div class='pg-title'>Trends</div>"
        "<div class='pg-sub'>How audience sentiment changes over time</div></div></div>",
        unsafe_allow_html=True,
    )
    t1, t2 = st.columns([1.5, 1], gap="medium")
    with t1:
        day = fdf.copy()
        day["date"] = day["timestamp"].dt.date
        trend_df = day.groupby(["date", "sentiment_label"]).size().reset_index(name="mentions")
        fig_area = px.area(trend_df, x="date", y="mentions",
                           color="sentiment_label", color_discrete_map=SENTIMENT_COLORS)
        fig_area.update_traces(line_width=1.5)
        style_plotly(
            fig_area,
            height      = 420,
            margin      = dict(l=44, r=16, t=52, b=44),
            show_legend = True,
            hovermode   = "x unified",
            xangle      = -25,
        )
        area_html = fig_area.to_html(full_html=False, include_plotlyjs="cdn",
                                     config={"displayModeBar": False, "responsive": True})
        area_html = _strip_plotly_size(area_html)
        components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
  .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
         padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);overflow:hidden;}}
  .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
  .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
  .divider{{height:1px;background:{BORDER};margin:12px 0}}
  .plot-wrap{{width:100%;height:380px;overflow:hidden;background:#fff;}}
  .plot-wrap>div{{width:100%!important;height:100%!important;}}
  @media(max-width:1024px){{.plot-wrap{{height:300px;}}}}
  @media(max-width:768px){{.plot-wrap{{height:260px;}}}}
  @media(max-width:480px){{.plot-wrap{{height:220px;}}}}
</style>
<div class="card">
  <div class="title">Daily Sentiment Volume</div>
  <div class="sub">Hover to inspect — drag to zoom — double-click to reset</div>
  <div class="divider"></div>
  <div class="plot-wrap">{area_html}</div>
</div>""", height=560, scrolling=False)
    with t2:
        theme_sent = pd.crosstab(fdf["theme"], fdf["sentiment_label"], normalize="index").reset_index()
        for c in ["Positive", "Neutral", "Negative"]:
            if c not in theme_sent:
                theme_sent[c] = 0
        theme_long = theme_sent.melt(
            id_vars=["theme"], value_vars=["Positive", "Neutral", "Negative"],
            var_name="sentiment_label", value_name="share",
        )
        order = (
            theme_long[theme_long["sentiment_label"] == "Positive"]
            .sort_values("share", ascending=True)["theme"].tolist()
        )
        fig_theme = px.bar(
            theme_long, x="share", y="theme", orientation="h", barmode="stack",
            color="sentiment_label", color_discrete_map=SENTIMENT_COLORS,
            category_orders={"theme": order},
        )
        style_plotly(
            fig_theme,
            height   = 420,
            margin   = dict(l=120, r=16, t=8, b=40),
            xgrid    = True,
            ygrid    = False,
            xtickfmt = ".0%",
            x_range  = [0, 1],
        )
        fig_theme.update_yaxes(automargin=True)
        theme_html = fig_theme.to_html(full_html=False, include_plotlyjs="cdn",
                                       config={"displayModeBar": False, "responsive": True})
        theme_html = _strip_plotly_size(theme_html)
        legend_html = "".join(
            f"<span style='display:flex;align-items:center;gap:6px;font-size:11px;color:{MUTED};'>"
            f"<span style='width:8px;height:8px;border-radius:50%;background:{c};flex-shrink:0'></span>{l}</span>"
            for l, c in [("Positive", ORANGE), ("Neutral", GRAY), ("Negative", DARK)]
        )
        components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
  .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
         padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);overflow:hidden;}}
  .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
  .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
  .divider{{height:1px;background:{BORDER};margin:12px 0}}
  .legend{{display:flex;gap:18px;margin-top:8px}}
  .plot-wrap{{width:100%;height:380px;overflow:hidden;background:#fff;}}
  .plot-wrap>div{{width:100%!important;height:100%!important;}}
  @media(max-width:1024px){{.plot-wrap{{height:300px;}}}}
  @media(max-width:768px){{.plot-wrap{{height:260px;}}}}
  @media(max-width:480px){{.plot-wrap{{height:220px;}}}}
</style>
<div class="card">
  <div class="title">Sentiment Mix by Theme</div>
  <div class="sub">Share of positive / neutral / negative within each topic</div>
  <div class="divider"></div>
  <div class="plot-wrap">{theme_html}</div>
  <div class="legend">{legend_html}</div>
</div>""", height=560, scrolling=False)

# -----------------------------------------------------------------------------
# ROI / TOPIC ANALYSIS TAB
# -----------------------------------------------------------------------------
with tabs[2]:
    if cs_mode:
        # ── ClipSense mode: Topic Analysis ───────────────────────────────────
        st.markdown(
            "<div class='title-row'><div><div class='pg-title'>Topic Analysis</div>"
            "<div class='pg-sub'>Sentiment breakdown by topic across video segments</div></div></div>",
            unsafe_allow_html=True,
        )
        theme_col = "theme" if "theme" in fdf.columns else None
        if theme_col:
            ta1, ta2 = st.columns(2, gap="medium")
            topic_counts = fdf[theme_col].value_counts().reset_index()
            topic_counts.columns = ["topic", "count"]
            fig_tc = px.bar(topic_counts, x="count", y="topic", orientation="h",
                            color="count",
                            color_continuous_scale=[[0,"#FFF0E3"],[1,"#F47A20"]],
                            text="count")
            fig_tc.update_traces(textposition="outside", cliponaxis=False,
                                 textfont=dict(size=11, color=TEXT),
                                 hovertemplate="<b>%{y}</b><br>%{x} segments<extra></extra>")
            fig_tc.update_coloraxes(showscale=False)
            style_plotly(fig_tc, height=360, margin=dict(l=130,r=60,t=8,b=36),
                         xgrid=True, ygrid=False)
            fig_tc.update_yaxes(automargin=True, categoryorder="total ascending")
            tc_html = _strip_plotly_size(fig_tc.to_html(
                full_html=False, include_plotlyjs="cdn",
                config={"displayModeBar": False, "responsive": True}))
            ts = pd.crosstab(fdf[theme_col], fdf["sentiment_label"], normalize="index").reset_index()
            for c in ["Positive", "Neutral", "Negative"]:
                if c not in ts: ts[c] = 0
            ts_long = ts.melt(id_vars=[theme_col],
                              value_vars=["Positive","Neutral","Negative"],
                              var_name="sentiment_label", value_name="share")
            ts_order = (ts_long[ts_long["sentiment_label"]=="Positive"]
                        .sort_values("share", ascending=True)[theme_col].tolist())
            fig_ts = px.bar(ts_long, x="share", y=theme_col, orientation="h", barmode="stack",
                            color="sentiment_label", color_discrete_map=SENTIMENT_COLORS,
                            category_orders={theme_col: ts_order})
            style_plotly(fig_ts, height=360, margin=dict(l=130,r=16,t=8,b=40),
                         xgrid=True, ygrid=False, xtickfmt=".0%", x_range=[0,1])
            fig_ts.update_yaxes(automargin=True)
            ts_html = _strip_plotly_size(fig_ts.to_html(
                full_html=False, include_plotlyjs="cdn",
                config={"displayModeBar": False, "responsive": True}))
            _card_ta = f"""
              *{{box-sizing:border-box;margin:0;padding:0}}
              html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
              .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
                     padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);overflow:hidden;}}
              .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
              .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
              .divider{{height:1px;background:{BORDER};margin:12px 0 10px;flex-shrink:0}}
              .plot-wrap{{width:100%;height:340px;overflow:hidden;}}
              .plot-wrap>div{{width:100%!important;height:100%!important;}}
              .leg{{display:flex;gap:16px;margin-top:8px;flex-wrap:wrap;}}
              .li{{display:flex;align-items:center;gap:5px;font-size:11px;color:{MUTED};}}
              .dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
            """
            _ts_leg = "".join(
                f"<span class='li'><span class='dot' style='background:{c}'></span>{l}</span>"
                for l, c in [("Positive",ORANGE),("Neutral",GRAY),("Negative",DARK)]
            )
            with ta1:
                components.html(f"""<style>{_card_ta}</style>
<div class="card">
  <div class="title">Topic Mentions</div>
  <div class="sub">Segment count per topic</div>
  <div class="divider"></div>
  <div class="plot-wrap">{tc_html}</div>
</div>""", height=520, scrolling=False)
            with ta2:
                components.html(f"""<style>{_card_ta}</style>
<div class="card">
  <div class="title">Sentiment Mix by Topic</div>
  <div class="sub">Share of positive / neutral / negative per topic</div>
  <div class="divider"></div>
  <div class="plot-wrap">{ts_html}</div>
  <div class="leg">{_ts_leg}</div>
</div>""", height=520, scrolling=False)
        else:
            st.info("No topic/theme data available in this dataset.")

        # ── Audience Preferences panel ────────────────────────────────────────
        _ap_liked       = audience_prefs.get("liked", [])
        _ap_disliked    = audience_prefs.get("disliked", [])
        _ap_requests    = audience_prefs.get("recurring_requests", [])
        _ap_complaints  = audience_prefs.get("recurring_complaints", [])
        _ap_praise      = audience_prefs.get("recurring_praise", [])
        _has_ap = any([_ap_liked, _ap_disliked, _ap_requests, _ap_complaints, _ap_praise])

        if _has_ap:
            st.markdown("<div style='height:20px;line-height:0'>&nbsp;</div>", unsafe_allow_html=True)

            def _ap_items_html(items, dot_color):
                if not items:
                    return f"<div style='font-size:12px;color:{MUTED};font-style:italic;'>None detected</div>"
                return "".join(
                    f"<div style='display:flex;align-items:flex-start;gap:8px;padding:6px 0;"
                    f"border-top:1px solid {BORDER};font-size:12px;color:{TEXT};line-height:1.5;'>"
                    f"<span style='width:7px;height:7px;border-radius:50%;background:{dot_color};"
                    f"flex-shrink:0;margin-top:4px;'></span>"
                    f"<span>{html.escape(str(item))}</span></div>"
                    for item in items
                )

            _ap_sections = [
                ("What Audiences Liked",       _ap_liked,      ORANGE),
                ("What Audiences Disliked",     _ap_disliked,   DARK),
                ("Recurring Requests",          _ap_requests,   BLUE),
                ("Recurring Complaints",        _ap_complaints, "#E7B545"),
                ("Recurring Praise",            _ap_praise,     GREEN),
            ]

            ap_cols = st.columns(len(_ap_sections), gap="medium")
            for col, (title, items, dot_color) in zip(ap_cols, _ap_sections):
                with col:
                    components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
  .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
         padding:20px 20px 16px;box-shadow:0 2px 12px rgba(50,40,30,.07);
         display:flex;flex-direction:column;}}
  .title{{font-size:12px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
  .divider{{height:1px;background:{BORDER};margin:10px 0 6px;flex-shrink:0}}
</style>
<div class="card">
  <div class="title">{html.escape(title)}</div>
  <div class="divider"></div>
  {_ap_items_html(items, dot_color)}
</div>""", height=max(120, 60 + len(items) * 38), scrolling=False)
    else:
        # ── Normal mode: ROI Analysis ─────────────────────────────────────────
        st.markdown(
            "<div class='title-row'><div><div class='pg-title'>ROI Analysis</div>"
            "<div class='pg-sub'>Estimated contribution from audience response</div></div></div>",
            unsafe_allow_html=True,
        )
        roi_tab = (
            fdf.groupby("roi_driver")
            .agg(roi=("roi_value_usd", "sum"), mentions=("text", "size"),
                 engagement=("engagement", "sum"))
            .reset_index().sort_values("roi", ascending=False)
        )
        r1, r2 = st.columns(2, gap="medium")
        with r1:
            fig_rbar = px.bar(
                roi_tab, x="roi", y="roi_driver", orientation="h",
                color="roi_driver",
                color_discrete_sequence=[_SC["positive"], _SC["blue"], _SC["green"], _SC["yellow"]],
                text=roi_tab["roi"].apply(lambda v: f"${v:,.0f}"),
            )
            fig_rbar.update_traces(
                textposition="outside", cliponaxis=False,
                textfont=dict(size=11, color=TEXT),
                hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
            )
            style_plotly(fig_rbar, height=360, margin=dict(l=120,r=80,t=8,b=36),
                         xgrid=True, ygrid=False, xtickpfx="$")
            fig_rbar.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
            fig_rbar.update_yaxes(tickfont=dict(size=11, color=TEXT), automargin=True)
            rbar_html = _strip_plotly_size(fig_rbar.to_html(
                full_html=False, include_plotlyjs="cdn",
                config={"displayModeBar": False, "responsive": True}))
            components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
  .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
         padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);overflow:hidden;}}
  .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
  .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
  .divider{{height:1px;background:{BORDER};margin:12px 0}}
  .plot-wrap{{width:100%;height:340px;overflow:hidden;background:#fff;}}
  .plot-wrap>div{{width:100%!important;height:100%!important;}}
</style>
<div class="card">
  <div class="title">ROI Contribution by Driver</div>
  <div class="sub">Total estimated value generated per driver</div>
  <div class="divider"></div>
  <div class="plot-wrap">{rbar_html}</div>
</div>""", height=520, scrolling=False)
        with r2:
            fig_scat = px.scatter(
                roi_tab, x="engagement", y="roi", size="mentions",
                color="roi_driver",
                color_discrete_sequence=[_SC["positive"], _SC["blue"], _SC["green"], _SC["yellow"]],
                hover_name="roi_driver", size_max=48,
            )
            fig_scat.update_traces(
                marker=dict(opacity=0.82, line=dict(width=1.5, color="#fff")),
                hovertemplate="<b>%{hovertext}</b><br>Engagement: %{x:,}<br>ROI: $%{y:,.0f}<extra></extra>",
            )
            style_plotly(fig_scat, height=360, margin=dict(l=64,r=16,t=8,b=48),
                         xgrid=True, x_title="Engagement", y_title="Estimated ROI", ytickpfx="$")
            scat_html = _strip_plotly_size(fig_scat.to_html(
                full_html=False, include_plotlyjs="cdn",
                config={"displayModeBar": False, "responsive": True}))
            scat_legend = "".join(
                f"<span style='display:flex;align-items:center;gap:6px;font-size:11px;color:{MUTED};'>"
                f"<span style='width:8px;height:8px;border-radius:50%;background:{c};flex-shrink:0'></span>"
                f"{row['roi_driver']}</span>"
                for (_, row), c in zip(roi_tab.iterrows(), [ORANGE, BLUE, GREEN, YELLOW])
            )
            components.html(f"""
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:transparent;font-family:Inter,-apple-system,sans-serif;overflow:hidden}}
  .card{{background:#fff;border:1px solid {BORDER};border-radius:16px;
         padding:22px 24px 18px;box-shadow:0 2px 12px rgba(50,40,30,.07);overflow:hidden;}}
  .title{{font-size:13px;font-weight:680;color:{TEXT};letter-spacing:-.1px}}
  .sub{{font-size:11px;font-weight:400;color:{MUTED};margin-top:3px;line-height:1.5}}
  .divider{{height:1px;background:{BORDER};margin:12px 0}}
  .legend{{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px}}
  .plot-wrap{{width:100%;height:340px;overflow:hidden;background:#fff;}}
  .plot-wrap>div{{width:100%!important;height:100%!important;}}
</style>
<div class="card">
  <div class="title">Engagement vs. Estimated ROI</div>
  <div class="sub">Bubble size = mention volume</div>
  <div class="divider"></div>
  <div class="plot-wrap">{scat_html}</div>
  <div class="legend">{scat_legend}</div>
</div>""", height=520, scrolling=False)
with tabs[3]:
    st.markdown(
        "<div class='title-row'><div><div class='pg-title'>Reports</div>"
        "<div class='pg-sub'>Export the filtered audience intelligence dataset</div></div></div>",
        unsafe_allow_html=True,
    )
    # ClipSense mode: surface video_timestamp, hide geo/ROI fabricated columns
    if cs_mode:
        _preferred = ["video_timestamp", "timestamp", "theme", "sentiment_label",
                      "sentiment_score", "confidence", "text", "source", "dataset_name"]
        _exclude   = {"lat", "lon", "country_code", "roi_driver", "roi_value_usd",
                      "likes", "shares", "replies", "engagement", "region", "country",
                      "language", "campaign", "content_type"}
    else:
        _preferred = ["comment_id", "platform", "region", "country", "theme",
                      "sentiment_label", "sentiment_score", "likes", "shares",
                      "replies", "engagement", "timestamp", "text"]
        _exclude   = set()

    report_cols = [c for c in _preferred if c in fdf.columns and c not in _exclude]
    # append any remaining columns not already included and not excluded
    for c in fdf.columns:
        if c not in report_cols and c not in _exclude:
            report_cols.append(c)

    sort_col = "video_timestamp" if (cs_mode and "video_timestamp" in fdf.columns) else "timestamp"
    report = fdf[report_cols].sort_values(sort_col, ascending=True if cs_mode else False)
    csv = report.to_csv(index=False).encode("utf-8")

    c1, c2 = st.columns([1, 3], gap="medium")
    with c1:
        _date_lbl = "Segments" if cs_mode else "Date range"
        _date_val = (
            f"{report['video_timestamp'].iloc[0]} – {report['video_timestamp'].iloc[-1]}"
            if cs_mode and "video_timestamp" in report.columns and len(report) > 0
            else f"{report['timestamp'].min().strftime('%b %d')} – {report['timestamp'].max().strftime('%b %d, %Y')}"
        )
        st.markdown(
            f"""
            <div class='sc-card'>
              <div class='sc-card-title'>Export</div>
              <div class='sc-card-sub'>{len(report):,} records ready</div>
              <div class='sc-card-divider'></div>
              {''.join(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"font-size:12px;padding:7px 0;border-top:1px solid {BORDER};'>"
                f"<span style='color:{MUTED};'>{lbl}</span>"
                f"<span style='font-weight:600;color:{TEXT};'>{val}</span></div>"
                for lbl, val in [
                    ('Total rows', f"{len(report):,}"),
                    ('Columns',    str(len(report_cols))),
                    (_date_lbl,    _date_val),
                    ('Source',     'ClipSense' if cs_mode else str(fdf['platform'].nunique()) + ' platforms'),
                ]
              )}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:8px;line-height:0'>&nbsp;</div>", unsafe_allow_html=True)
        st.download_button(
            "⬇️  Download CSV", csv,
            "sensecap_report.csv", "text/csv",
            use_container_width=True,
        )
    with c2:
        st.markdown(
            "<div class='sc-card'>"
            f"<div class='sc-card-title'>{'Segment Feedback' if cs_mode else 'Audience Comments'}</div>"
            "<div class='sc-card-sub'>Sortable — click any column header to sort</div>"
            "<div class='sc-card-divider'></div>"
            "</div>",
            unsafe_allow_html=True,
        )
        col_cfg = {
            "sentiment_score": st.column_config.ProgressColumn(
                "Score", min_value=-1, max_value=1, format="%.2f",
            ),
            "confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0, max_value=1, format="%.2f",
            ),
            "timestamp": st.column_config.DatetimeColumn("Date", format="MMM DD, YYYY"),
        }
        if not cs_mode:
            col_cfg["engagement"] = st.column_config.NumberColumn("Engagement", format="%d")
        st.dataframe(
            report, use_container_width=True, height=480, hide_index=True,
            column_config=col_cfg,
        )
