"""SIP Discovery Engine dashboard.

Reads the local files in this folder and re-tags nothing. The only network call is on the
"Ask the evidence" page, which sends up to 25 matching tagged posts to the Groq API.
The API key is read from the environment (or a local .env file) or st.secrets, never from code.
Run:  py -m streamlit run app.py
"""

import html
import json
import math
import os
import re
import textwrap
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="SIP Discovery Engine", page_icon="📊", layout="wide")

HERE = Path(__file__).parent
MIN_N = 30  # below this, no chart and no shares: counts only

# ---------------------------------------------------------------------------
# Palette: use ONLY these. Colour-blind safe; no red/green anywhere.
# Meaning is always also carried by a printed label or axis category.
# ---------------------------------------------------------------------------
INK = "#16202B"
MUTED = "#6F8197"
FAINT = "#8FA0B5"
LINE = "#E4E8EC"
GRID = "#EEF1F4"
PAGE_BG = "#FAFAF9"
ACCENT = "#B4530A"  # everything that is not involuntary / voluntary
NAV_ACCENT = "#E8903F"
INVOLUNTARY = "#1C6F6A"  # teal
VOLUNTARY = "#7B4A9C"  # purple
BODY = "#44566B"

# Tile / card kinds: (top border, tinted background)
KINDS = {
    "neutral": (INK, "#F2F4F6"),
    "inv": (INVOLUNTARY, "#EAF3F2"),
    "vol": (VOLUNTARY, "#F3EDF7"),
    "warn": (ACCENT, "#FBF0E6"),
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
  font-family: 'IBM Plex Sans', sans-serif;
}}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ visibility: hidden; height: 0; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: {PAGE_BG}; }}

.block-container, [data-testid="stMainBlockContainer"] {{
  max-width: 1100px; margin: 0 auto; padding-top: 2.2rem;
}}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {{ background: {INK}; }}
section[data-testid="stSidebar"] > div {{ background: {INK}; }}
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg {{ color: {FAINT}; }}
section[data-testid="stSidebar"] .sb-title {{ color: #FFFFFF; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.01em; }}
section[data-testid="stSidebar"] .sb-sub {{ color: {FAINT}; font-size: 13px; line-height: 1.45; margin: 4px 0 22px 0; }}
section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 2px; width: 100%; }}
section[data-testid="stSidebar"] label[data-baseweb="radio"] {{
  width: 100%; margin: 0; padding: 9px 12px; border-left: 3px solid transparent;
  border-radius: 0 6px 6px 0; cursor: pointer;
}}
section[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] label[data-baseweb="radio"] p {{ color: #FFFFFF; font-size: 14.5px; }}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {{ background: rgba(255,255,255,0.04); }}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {{
  border-left-color: {NAV_ACCENT}; background: rgba(255,255,255,0.08);
}}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p {{ font-weight: 600; }}
section[data-testid="stSidebar"] .sb-foot {{
  position: fixed; bottom: 18px; max-width: 250px; color: {FAINT}; font-size: 11px; line-height: 1.5;
}}

/* ---------- Text ---------- */
.page-title {{
  font-size: 30px; font-weight: 700; letter-spacing: -0.02em; color: {INK};
  line-height: 1.2; margin: 0 0 6px 0;
}}
.page-lede {{ color: {BODY}; font-size: 15px; line-height: 1.55; margin-bottom: 18px; }}
.section {{
  display: flex; align-items: center; gap: 10px;
  font-size: 19px; font-weight: 600; color: {INK}; margin: 30px 0 12px 0; letter-spacing: -0.01em;
}}
.section::before {{
  content: ""; flex: 0 0 4px; width: 4px; height: 20px; background: {ACCENT}; border-radius: 1px;
}}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{
  color: {BODY}; font-size: 15px; line-height: 1.55;
}}
.cap {{ color: {FAINT}; font-size: 11px; line-height: 1.5; margin: 4px 0 10px 0; font-weight: 400; }}
.finding {{ color: {INK}; font-size: 14px; font-weight: 600; margin: 6px 0 8px 0; line-height: 1.4; }}
.small {{ color: {MUTED}; font-size: 13px; line-height: 1.5; }}

/* ---------- Cards ---------- */
.card {{
  background: #FFFFFF; border: 1px solid {LINE}; border-top: 3px solid var(--c, {ACCENT});
  border-radius: 10px; padding: 16px 18px; height: 100%; margin-bottom: 8px;
}}
.card h4 {{ margin: 0 0 6px 0; font-size: 15px; font-weight: 600; color: {INK}; line-height: 1.35; }}
.card p {{ margin: 0; color: {BODY}; font-size: 14px; line-height: 1.5; }}
.card .row {{ display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: {BODY};
  border-top: 1px solid {LINE}; padding: 6px 0 0 0; margin-top: 6px; }}
.card .row .k {{ color: {MUTED}; }}
.card .row .v {{ font-family: 'IBM Plex Mono', monospace; color: {INK}; text-align: right; }}
.card .meta {{ font-size: 12.5px; color: {MUTED}; display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; }}
.card .meta b {{ color: {INK}; font-weight: 600; }}
.card .meta .id {{ font-family: 'IBM Plex Mono', monospace; }}
.card .vq {{ color: {INK}; font-size: 14.5px; line-height: 1.5; margin-bottom: 6px; }}
.card .noq {{ color: {MUTED}; font-size: 13px; font-style: italic; margin-bottom: 6px; }}
.card .tags {{ font-size: 12px; color: {MUTED}; }}
.card .gap-h {{ font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: {MUTED}; margin-bottom: 4px; }}

.strip {{ display: flex; gap: 0; border: 1px solid {LINE}; border-radius: 10px; overflow: hidden; }}
.strip .step {{ flex: 1; padding: 12px 14px; background: #FFFFFF; border-right: 1px solid {LINE}; }}
.strip .step:last-child {{ border-right: none; }}
.strip .step .n {{ font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: {ACCENT}; font-weight: 600; }}
.strip .step .h {{ font-size: 14px; font-weight: 600; color: {INK}; margin: 2px 0; }}
.strip .step .d {{ font-size: 12.5px; color: {BODY}; line-height: 1.4; }}

/* ---------- Metric tiles ---------- */
.tile {{
  background: var(--bg); border-top: 3px solid var(--c); border-radius: 8px; padding: 14px 16px 12px 16px;
}}
.tile .num {{
  font-family: 'IBM Plex Mono', monospace; font-size: 28px; font-weight: 600; color: {INK}; line-height: 1.15;
}}
.tile .lbl {{
  font-size: 12px; color: {MUTED}; margin-top: 6px; line-height: 1.35;
  text-transform: uppercase; letter-spacing: 0.06em;
}}

/* ---------- Ask the evidence ---------- */
.st-key-ask_box [data-baseweb="input"] {{
  height: 56px; border-radius: 10px; border: 1px solid #CBD3DB; background: #FFFFFF;
}}
.st-key-ask_box [data-baseweb="input"]:focus-within {{ border-color: {ACCENT}; }}
.st-key-ask_box input {{ height: 56px; font-size: 16px; padding: 0 18px; color: {INK}; }}
.st-key-ask_go button {{ height: 50px; font-size: 16px; font-weight: 600; border-radius: 10px; }}
.ask-note {{ color: {FAINT}; font-size: 12px; line-height: 1.5; margin: 2px 0 6px 0; }}

[class*="st-key-qcard_"] button {{
  width: 100%; min-height: 128px; background: #FFFFFF; border: 1px solid {LINE};
  border-top: 3px solid {ACCENT}; border-radius: 10px; padding: 16px 18px;
  display: flex; align-items: flex-start; justify-content: flex-start; text-align: left;
}}
[class*="st-key-qcard_"] button:hover {{ border-color: {ACCENT}; background: #FFFCF9; }}
[class*="st-key-qcard_"] button:focus:not(:active) {{ border-color: {ACCENT}; box-shadow: none; }}
[class*="st-key-qcard_"] button > div {{ justify-content: flex-start; text-align: left; width: 100%; }}
[class*="st-key-qcard_"] button p {{ color: {INK}; font-size: 14.5px; font-weight: 500; line-height: 1.45; text-align: left; }}
[class*="st-key-qcard_"] button p span {{ color: {FAINT} !important; font-size: 12px; font-weight: 400; }}

.st-key-answer_box {{
  background: #FFFFFF; border: 1px solid {LINE}; border-top: 3px solid {ACCENT};
  border-radius: 10px; padding: 16px 18px;
}}
.st-key-answer_box [data-testid="stMarkdownContainer"] p,
.st-key-answer_box [data-testid="stMarkdownContainer"] li {{ color: {INK}; font-size: 15.5px; }}

.foot {{
  border-top: 1px solid {LINE}; margin-top: 36px; padding-top: 12px; color: {MUTED};
  font-size: 12.5px; line-height: 1.5;
}}
</style>
"""

SOURCE_LABELS = {
    "play_store": "Play Store",
    "app_store": "App Store",
    "youtube": "YouTube",
    "reddit_comment": "Reddit comments",
    "reddit_post": "Reddit posts",
    "tradingqna": "TradingQnA",
}
TRIGGER_LABELS = {
    "app_problem": "App problem",
    "payment_failure": "Payment failure",
    "market_drop": "Market drop",
    "trust_or_fees": "Trust or fees",
    "money_needed": "Money needed",
    "didnt_understand": "Didn't understand",
    "returns_disappointing": "Returns disappointing",
    "unclear": "Problem, cause unclear",
    "none": "No problem described",
}
NAMED_TRIGGERS = [t for t in TRIGGER_LABELS if t not in ("none", "unclear")]
LAPSE_LABELS = {"none": "No lapse", "unclear": "Unclear", "involuntary": "Involuntary", "voluntary": "Voluntary"}
LAPSE_COLORS = {"involuntary": INVOLUNTARY, "voluntary": VOLUNTARY}
STATUS_LABELS = {"active": "Active", "unclear": "Unclear", "never_started": "Never started", "lapsed": "Lapsed"}
STAGE_LABELS = {
    "pre_start": "Before starting",
    "month_0_3": "Months 0–3",
    "month_3_6": "Months 3–6",
    "month_6_12": "Months 6–12",
    "after_stopping": "After stopping",
    "unclear": "Unclear",
}
FIELD_LABELS = {
    "relevant": "Relevant",
    "stage": "Stage",
    "sip_status": "SIP status",
    "lapse_type": "Lapse type",
    "trigger": "Trigger",
    "first_time": "First-time",
}

# How the PARSE_FAIL bug was fixed is not recorded in the data files.
# Fill this in (plain text) and it will appear on the trust page.
PARSE_FAIL_FIX_NOTE = None


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data
def load_findings():
    return json.loads((HERE / "findings.json").read_text(encoding="utf-8"))


_HANDLE_RE = re.compile(r"(@[\w.\-]+|\bu/[\w\-]+)")


def mask_handles(text):
    if not isinstance(text, str):
        return ""
    return _HANDLE_RE.sub("[user]", text)


def date_label(raw, precision):
    """'12 Oct 2026' for exact dates; 'approx. Oct 2024' when the source only gave a relative date."""
    d = pd.to_datetime(raw, errors="coerce", format="mixed")
    if pd.isna(d):
        return "date not recorded"
    if str(precision).strip().lower() == "exact":
        return f"{d.day} {d:%b %Y}"
    return f"approx. {d:%b %Y}"


@st.cache_data
def load_tagged():
    """All tagged rows, with PARSE_FAIL rows split off (they are failed API responses, not judgements)."""
    df = pd.read_csv(HERE / "tagged_items.csv")
    df["period"] = df["recency"].astype(str).str.startswith("current").map({True: "current", False: "before"})
    fails = df[df["relevant"] == "PARSE_FAIL"].copy()
    df = df[df["relevant"] != "PARSE_FAIL"].copy()  # excluded from every count
    df["text"] = df["text"].map(mask_handles)
    df["quote"] = df["quote"].map(mask_handles)
    df["quote_verified"] = df["quote_verified"].astype(bool)
    df["date_label"] = [date_label(d, p) for d, p in zip(df["date"], df["date_precision"])]
    return df, fails


@st.cache_data
def load_source_table():
    """Per-source facts computable from corpus_sip.csv. No post text is displayed."""
    c = pd.read_csv(HERE / "corpus_sip.csv", usecols=["source", "channel", "date"])
    c["d"] = pd.to_datetime(c["date"], errors="coerce", utc=True, format="mixed")
    out = []
    for s, g in c.groupby("source"):
        ch = g["channel"].nunique()
        what = {
            "play_store": "Google Play Store reviews",
            "app_store": "Apple App Store reviews",
            "youtube": f"Comments on {ch} YouTube videos",
            "reddit_comment": f"Comments across {ch} subreddits",
            "reddit_post": f"Posts across {ch} subreddits",
            "tradingqna": f"Posts across {ch} TradingQnA threads",
        }.get(s, s)
        if g["d"].notna().any():
            dr = f"{g['d'].min():%b %Y} – {g['d'].max():%b %Y}"
        else:
            dr = "Not recorded"
        out.append({"source": s, "what": what, "kept": len(g), "dates": dr})
    return pd.DataFrame(out)


@st.cache_data
def corpus_ids():
    return set(pd.read_csv(HERE / "corpus_sip.csv", usecols=["id"])["id"].astype(str))


# findings.json is used ONLY for numbers that cannot be recomputed from the files in this folder:
# the raw collection total and the validation results. Every other count is computed from tagged_items.csv.
F = load_findings()
V = F["validation"]
ALL_TAGGED, ALL_FAILS = load_tagged()
N_SIP_RELATED = len(corpus_ids())  # rows in corpus_sip.csv (first scrape)
N_ALL_TAGGED = len(ALL_TAGGED) + len(ALL_FAILS)
# Tagged rows that are not in corpus_sip.csv came from the later top-up collection.
N_TOPUP = int((~pd.concat([ALL_TAGGED["id"], ALL_FAILS["id"]]).astype(str).isin(corpus_ids())).sum())
N_PLATFORMS = len({SOURCE_LABELS.get(s, s).split()[0] for s in ALL_TAGGED["source"].unique()})  # Reddit posts + comments = 1

PERIODS = {
    "current": "Current (2024 onwards)",
    "all": "All years",
    "before": "Before 2024 only",
}
PERIOD_SHORT = {"current": "2024 onwards", "all": "all years", "before": "before 2024"}

# Set by apply_period() before any page is drawn.
PERIOD = "current"
TAGGED = RELEVANT = FAILS = None
N_FAIL = N_REL = 0
N_BY_SOURCE = {}
EXCL = ""


def in_period(df, period):
    return df if period == "all" else df[df["period"] == period]


def apply_period(period):
    """Every count, chart and caption on every page is drawn from these period-filtered frames."""
    global PERIOD, TAGGED, RELEVANT, FAILS, N_FAIL, N_REL, N_BY_SOURCE, EXCL
    PERIOD = period
    TAGGED = in_period(ALL_TAGGED, period)
    FAILS = in_period(ALL_FAILS, period)
    RELEVANT = TAGGED[TAGGED["relevant"] == "yes"]
    N_FAIL = len(FAILS)
    N_REL = len(RELEVANT)
    N_BY_SOURCE = RELEVANT["source"].value_counts().to_dict()
    EXCL = f"{PERIOD_SHORT[period]} · excludes {N_FAIL} PARSE_FAIL"


def n_threads(df):
    return int(df["thread_id"].nunique())


def indep(df):
    """'57 items from 45 independent sources' (a source = one distinct thread, video, review or post)."""
    n, t = len(df), n_threads(df)
    return f"{n} item{'s' if n != 1 else ''} from {t} independent source{'s' if t != 1 else ''}"


def lapsed(df):
    """Voluntary / involuntary lapses are counted only for people whose SIP has stopped."""
    return df[(df["sip_status"] == "lapsed") & df["lapse_type"].isin(["involuntary", "voluntary"])]


def missed_but_active(df):
    """Active SIPs that still carry a lapse type: a missed instalment, but the person kept investing."""
    return df[(df["sip_status"] == "active") & df["lapse_type"].isin(["involuntary", "voluntary"])]


def pct(x, n):
    return f"{x / n:.0%}" if n else "–"


def cnt_pct(x, n):
    return f"{x} of {n} ({x / n:.0%})" if n else f"{x}"


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
def page_title(text, lede=None, toggle_key=None):
    """Page heading. With toggle_key, a 'Show underlying numbers' toggle sits top right
    and its value is returned (True = show tables instead of charts)."""
    show_tables = False
    if toggle_key:
        left, right = st.columns([5, 1.45], vertical_alignment="top")
        with right:
            show_tables = st.toggle("Show underlying numbers", key=toggle_key)
        target = left
    else:
        target = st.container()
    with target:
        st.markdown(f'<div class="page-title">{esc(text)}</div>', unsafe_allow_html=True)
        if lede:
            st.markdown(f'<div class="page-lede">{lede}</div>', unsafe_allow_html=True)
    return show_tables


def section(text):
    st.markdown(f'<div class="section">{esc(text)}</div>', unsafe_allow_html=True)


def tiles(items):
    """items: (number, label, kind) with kind in KINDS."""
    cols = st.columns(len(items))
    for col, (num, label, kind) in zip(cols, items):
        c, bg = KINDS[kind]
        col.markdown(
            f'<div class="tile" style="--c:{c};--bg:{bg}"><div class="num">{esc(num)}</div>'
            f'<div class="lbl">{esc(label)}</div></div>',
            unsafe_allow_html=True,
        )


def card_html(inner, color=ACCENT):
    return f'<div class="card" style="--c:{color}">{inner}</div>'


def gap_box(text, head="Not answerable from public text"):
    st.markdown(card_html(f'<div class="gap-h">{esc(head)}</div><p>{esc(text)}</p>', ACCENT), unsafe_allow_html=True)


def note(text):
    st.markdown(f'<div class="cap">{esc(text)}</div>', unsafe_allow_html=True)


def caption(n, what, excl=None):
    """Global caption format: n = <count> records · <what> · <period> · <exclusion>"""
    note(f"n = {n:,} records · {what} · {excl or EXCL}")


def lapse_label(r):
    lt = r["lapse_type"]
    if lt in ("involuntary", "voluntary") and r["sip_status"] == "active":
        return f"Missed an instalment ({lt}), still investing"
    return LAPSE_LABELS.get(lt, lt)


def lapse_color(r):
    return LAPSE_COLORS.get(r["lapse_type"], ACCENT) if r["sip_status"] == "lapsed" else ACCENT


def source_link(url):
    url = str(url or "")
    if not url.startswith(("https://", "http://")):
        return ""
    return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">View source</a>'


def evidence_card(r, prefix="", extra_tags=""):
    """One quote / evidence card: source, date, View source link, quote, tags."""
    quote = (
        f'<div class="vq">“{esc(r["quote"])}”</div>'
        if r["quote_verified"] and r["quote"]
        else '<div class="noq">No verified quote for this record.</div>'
    )
    link = source_link(r.get("url"))
    st.markdown(
        card_html(
            f'<div class="meta"><span><b>{esc(prefix)}{esc(SOURCE_LABELS.get(r["source"], r["source"]))}</b></span>'
            f'<span>{esc(r["date_label"])}</span>'
            f'{f"<span>{link}</span>" if link else ""}'
            f'<span class="id">id {esc(r["id"])}</span></div>{quote}'
            f'<div class="tags">Trigger: {esc(TRIGGER_LABELS.get(r["trigger"], r["trigger"]))} · '
            f'Lapse: {esc(lapse_label(r))}{extra_tags}</div>',
            lapse_color(r),
        ),
        unsafe_allow_html=True,
    )


def table(df):
    st.dataframe(df, hide_index=True, use_container_width=True, height=min(36 * (len(df) + 1) + 4, 420))


def finding(text):
    """The chart title, shown above a table when charts are switched to tables."""
    st.markdown(f'<div class="finding">{esc(text)}</div>', unsafe_allow_html=True)


def insufficient(n, counts: pd.DataFrame):
    gap_box(
        f"Insufficient evidence - only {n} records. Shown as a count, not a share.",
        head="Insufficient evidence",
    )
    table(counts)


def footer():
    st.markdown(
        f'<div class="foot"><b>Not investment advice.</b> This dashboard describes what public posts say; '
        f"it does not recommend any fund, stock or action. Built from public data only. No usernames or "
        f"personal data are shown (handles in post text are replaced with [user]). {N_FAIL} tagged records "
        f"from this evidence period that failed to parse (PARSE_FAIL) are excluded from every count.</div>",
        unsafe_allow_html=True,
    )


def period_control():
    """The one global control: which years of evidence every page uses."""
    period = st.radio(
        "Evidence period", list(PERIODS), format_func=PERIODS.get, horizontal=True, key="period",
    )
    apply_period(period)
    rel_all = ALL_TAGGED[ALL_TAGGED["relevant"] == "yes"]
    hidden = len(rel_all) - N_REL
    if period == "current":
        line = f"Showing {N_REL:,} items. {hidden:,} items from before 2024 are hidden."
    elif period == "before":
        line = f"Showing {N_REL:,} items. {hidden:,} items from 2024 onwards are hidden."
    else:
        line = f"Showing all {N_REL:,} items, from every year."
    st.markdown(f'<div class="small">{esc(line)} Items = relevant tagged records.</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Charts: horizontal bars, sorted descending, value label at the end of each bar
# ---------------------------------------------------------------------------
def _title(text, width=58):
    return alt.TitleParams(
        textwrap.wrap(text, width), anchor="start", fontSize=14, fontWeight=600,
        color=INK, font="IBM Plex Sans", offset=10,
    )


def _x_axis(title):
    return alt.Axis(grid=True, gridColor=GRID, gridOpacity=1, labelColor=MUTED, titleColor=MUTED,
                    titleFontWeight=400, titleFontSize=12, domain=False, ticks=False, tickCount=4)


def _y_axis(label_width):
    return alt.Axis(labelLimit=label_width, labelColor=MUTED, labelFontSize=12.5, ticks=False,
                    domain=False, labelPadding=8, grid=False)


def _finish(chart):
    return chart.configure_view(strokeWidth=0).configure(font="IBM Plex Sans", background="transparent")


# Even vertical gaps between bars; chart height grows with the number of categories.
Y_BAND = alt.Scale(paddingInner=0.35, paddingOuter=0.25)


def hbar(df, title, x_title="Records", max_x=None, label_width=190):
    """df columns: label, value, text, [color]. Sorted descending by value."""
    df = df.copy().sort_values("value", ascending=False)
    if "color" not in df:
        df["color"] = ACCENT
    # Leave room for the value label at the end of the longest bar (longer labels need more room).
    pad = 1.35 if df["text"].str.len().max() <= 12 else 2.1
    top = max_x if max_x is not None else (df["value"].max() * pad or 1)
    base = alt.Chart(df).encode(
        y=alt.Y("label:N", sort=df["label"].tolist(), title=None, axis=_y_axis(label_width), scale=Y_BAND),
        x=alt.X("value:Q", title=x_title, scale=alt.Scale(domain=[0, top]), axis=_x_axis(x_title)),
        tooltip=[alt.Tooltip("label:N", title=" "), alt.Tooltip("text:N", title="Value")],
    )
    bars = base.mark_bar(stroke=INK, strokeWidth=1.2, cornerRadius=0).encode(color=alt.Color("color:N", scale=None, legend=None))
    labels = base.mark_text(align="left", dx=6, color=INK, font="IBM Plex Mono", fontSize=12).encode(text="text:N")
    return _finish((bars + labels).properties(width="container", height=alt.Step(34), title=_title(title)))


def show(chart):
    st.altair_chart(chart, use_container_width=True, theme=None)


def split_df(data: pd.DataFrame, col: str, labels: dict, colors=None, sources=False):
    """Counts of a categorical column -> chart frame with 'share (count)' labels.
    With sources=True the label also gives the number of independent sources (distinct thread_id)."""
    n = len(data)
    rows = []
    for k, g in data.groupby(col):
        v, t = len(g), n_threads(g)
        rows.append({
            "label": labels.get(k, k),
            "value": int(v),
            "threads": t,
            "text": f"{v / n:.0%} ({v} from {t} sources)" if sources else f"{v / n:.0%} ({v})",
            "color": (colors or {}).get(k, ACCENT),
        })
    return pd.DataFrame(rows, columns=["label", "value", "threads", "text", "color"]).sort_values("value", ascending=False)


def split_block(data, col, labels, title_fn, what, colors=None, excl=None, tables=False, sources=False):
    """Chart (or table) + caption, or an insufficient-evidence box when n < MIN_N."""
    n = len(data)
    df = split_df(data, col, labels, colors, sources)
    cols = ["Category", "Records"] + (["Independent sources"] if sources else [])
    tbl = df.rename(columns={"label": "Category", "value": "Records", "threads": "Independent sources"})[cols]
    if sources:
        what += " · independent sources = distinct threads, videos, reviews or posts"
    if n < MIN_N:
        insufficient(n, tbl)
        caption(n, what, excl)
        return
    tbl["Share"] = (tbl["Records"] / n).map(lambda v: f"{v:.0%}")
    top = df.sort_values("value", ascending=False).iloc[0]
    title = title_fn(top, n)
    if tables:
        finding(title)
        table(tbl)
    else:
        show(hbar(df, title))
    caption(n, what, excl)


# ---------------------------------------------------------------------------
# PAGE 1 - Overview
# ---------------------------------------------------------------------------
def evidence_strength(sub: pd.DataFrame):
    """Rule shown on the page:
    Strong   = 50+ records from 3+ sources, no single source above 75%.
    Moderate = 30+ records, or 50+ records dominated by one source.
    Weak     = fewer than 30 records."""
    n = len(sub)
    vc = sub["source"].value_counts()
    top_share = vc.iloc[0] / n if n else 1
    if n < MIN_N:
        return "Weak"
    if n >= 50 and len(vc) >= 3 and top_share <= 0.75:
        return "Strong"
    return "Moderate"


OPPORTUNITY_TITLES = {
    "payment_failure": ("Payment and mandate failures that end SIPs without the investor choosing to", INVOLUNTARY),
    "app_problem": ("App problems that block SIP actions: bugs, broken flows, support", ACCENT),
    "market_drop": ("Reactions to market falls", VOLUNTARY),
    "trust_or_fees": ("Doubts about trust, charges or fees", VOLUNTARY),
    "money_needed": ("Needing the money for something else", VOLUNTARY),
    "didnt_understand": ("Not understanding how SIPs or the app work", VOLUNTARY),
    "returns_disappointing": ("Returns lower than expected", VOLUNTARY),
}


def opportunity_card(title, sub, color):
    n = len(sub)
    vc = sub["source"].value_counts()
    srcs = ", ".join(f"{SOURCE_LABELS[s]} {c}" for s, c in vc.items())
    strength = evidence_strength(sub)
    st.markdown(
        card_html(
            f"<h4>{esc(title)}</h4>"
            f'<div class="row"><span class="k">Records</span><span class="v">{esc(indep(sub))}</span></div>'
            f'<div class="row"><span class="k">Share of relevant</span><span class="v">{cnt_pct(n, N_REL)}</span></div>'
            f'<div class="row"><span class="k">Sources</span><span class="v">{esc(srcs)}</span></div>'
            f'<div class="row"><span class="k">Evidence strength</span><span class="v"><b>{strength}</b> · unverified</span></div>',
            color,
        ),
        unsafe_allow_html=True,
    )


def page_overview():
    ap_pf = RELEVANT[RELEVANT["trigger"].isin(["app_problem", "payment_failure"])]
    named_n = int(RELEVANT["trigger"].isin(NAMED_TRIGGERS).sum())
    ps = int((ap_pf["source"] == "play_store").sum())
    tables = page_title(
        f"App problems and payment failures are {len(ap_pf)} of the {named_n} named reasons SIPs break, "
        f"and {ps} of those {len(ap_pf)} come from Play Store reviews",
        "A discovery engine over public conversations about SIPs (monthly mutual fund investments) in India, "
        "built to understand why first-time investors stop within 12 months. The product studied is Groww.",
        toggle_key="tables_overview",
    )
    n_tagged = len(TAGGED) + N_FAIL
    tiles(
        [
            (f"{F['collected']:,}", "posts collected (all years, first scrape)", "neutral"),
            (f"{N_SIP_RELATED:,}", "SIP-related after filtering (all years, first scrape)", "neutral"),
            (f"{n_tagged:,}", f"tagged by the model ({PERIOD_SHORT[PERIOD]})", "neutral"),
            (f"{N_REL}", f"confirmed relevant ({PERIOD_SHORT[PERIOD]})", "neutral"),
            (f"{N_FAIL}", f"excluded as PARSE_FAIL ({PERIOD_SHORT[PERIOD]})", "warn"),
        ]
    )
    note(
        "The first two tiles describe the whole first collection and are not split by year. "
        "The other three follow the evidence period."
    )

    section("How the evidence was built")
    steps = [
        ("Collect", f"{F['collected']:,} public posts from {N_PLATFORMS} sources"),
        ("Filter", f"{N_SIP_RELATED:,} SIP-related posts kept"),
        ("Tag", f"{N_ALL_TAGGED:,} labelled against a fixed codebook, incl. {N_TOPUP} from a later top-up"),
        ("Verify quotes", "Each quote checked word-for-word against its post"),
        ("Validate", f"{V['golden_set_n']}-item blind human golden set, plus repeat runs"),
        ("Compare", "Every finding split by source before it is ranked"),
    ]
    st.markdown(
        '<div class="strip">'
        + "".join(
            f'<div class="step"><div class="n">{i:02d}</div><div class="h">{esc(h)}</div><div class="d">{esc(d)}</div></div>'
            for i, (h, d) in enumerate(steps, 1)
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    section("Top opportunities")
    st.markdown(
        "The three most-named causes of a problem. Evidence strength is a rule applied to the tagged data, "
        "not a test with users, so every label is marked <i>unverified</i>.",
        unsafe_allow_html=True,
    )
    r = RELEVANT
    top3 = r[r["trigger"].isin(NAMED_TRIGGERS)]["trigger"].value_counts().head(3).index.tolist()
    cards = [(OPPORTUNITY_TITLES[t][0], r[r["trigger"] == t], OPPORTUNITY_TITLES[t][1]) for t in top3]
    if not cards:
        gap_box("No named trigger in this evidence period.", head="No records")
    elif tables:
        table(
            pd.DataFrame(
                [
                    {
                        "Opportunity": t,
                        "Records": len(s),
                        "Independent sources": n_threads(s),
                        "Share of relevant": pct(len(s), N_REL),
                        "Largest source": f"{SOURCE_LABELS[s['source'].value_counts().index[0]]} ({s['source'].value_counts().iloc[0]})",
                        "Sources": s["source"].nunique(),
                        "Evidence strength": f"{evidence_strength(s)} · unverified",
                    }
                    for t, s, _ in cards
                ]
            )
        )
    else:
        cols = st.columns(3)
        for col, (title, sub, color) in zip(cols, cards):
            with col:
                opportunity_card(title, sub, color)
    caption(N_REL, "relevant records; each card counts records with that trigger")
    note(
        "Independent sources = distinct threads, videos, reviews or posts; several comments in one thread "
        "count as one source. "
        "Evidence strength rule: Strong = 50+ records from 3+ sources with no single source above 75%. "
        "Moderate = 30+ records, or 50+ dominated by one source. Weak = fewer than 30 records. "
        "Top border: teal = involuntary-related, purple = voluntary-related, amber = other."
    )
    footer()


# ---------------------------------------------------------------------------
# PAGE 2 - What investors do
# ---------------------------------------------------------------------------
BEHAVIOURS = {
    "Payment failure named": (lambda d: d["trigger"] == "payment_failure", INVOLUNTARY),
    "App problem named": (lambda d: d["trigger"] == "app_problem", ACCENT),
    "No problem described": (lambda d: d["trigger"] == "none", ACCENT),
    "SIP has lapsed": (lambda d: d["sip_status"] == "lapsed", ACCENT),
    # Lapse types count only for people whose SIP has stopped.
    "Involuntary lapse": (lambda d: (d["sip_status"] == "lapsed") & (d["lapse_type"] == "involuntary"), INVOLUNTARY),
    "Voluntary lapse": (lambda d: (d["sip_status"] == "lapsed") & (d["lapse_type"] == "voluntary"), VOLUNTARY),
}


def lapse_block(lap, excl, tables):
    """Lapses by trigger, stacked involuntary / voluntary. `lap` holds lapsed SIPs only."""
    n = len(lap)
    ct = lap.groupby(["trigger", "lapse_type"]).size().reset_index(name="n")
    ct["label"] = ct["trigger"].map(TRIGGER_LABELS)
    ct["type"] = ct["lapse_type"].map({"involuntary": "Involuntary", "voluntary": "Voluntary"})
    threads = lap.groupby("trigger")["thread_id"].nunique()
    tbl = ct.pivot_table(index="trigger", columns="type", values="n", fill_value=0).reset_index()
    for c in ("Involuntary", "Voluntary"):
        if c not in tbl:
            tbl[c] = 0
    tbl["Total"] = tbl["Involuntary"] + tbl["Voluntary"]
    tbl["Independent sources"] = tbl["trigger"].map(threads).fillna(0).astype(int)
    tbl["Trigger"] = tbl["trigger"].map(TRIGGER_LABELS)
    tbl = tbl.sort_values("Total", ascending=False)[["Trigger", "Involuntary", "Voluntary", "Total", "Independent sources"]]
    what = ("relevant records whose SIP has lapsed, voluntary or involuntary, by trigger · "
            "independent sources = distinct threads, videos, reviews or posts")
    if n < MIN_N:
        insufficient(n, tbl)
        caption(n, what, excl)
        return
    inv = lap[lap["lapse_type"] == "involuntary"]
    vol = lap[lap["lapse_type"] == "voluntary"]
    pf_inv = int((inv["trigger"] == "payment_failure").sum())
    title = (f"Payment failures are {pf_inv} of the {len(inv)} involuntary lapses"
             if len(inv) else "No involuntary lapses in this view")
    if len(vol):
        title += f"; the {len(vol)} voluntary lapses spread across {vol['trigger'].nunique()} triggers"
    title += f" (N={n}, {n_threads(lap)} independent sources)"
    if tables:
        finding(title)
        table(tbl)
        caption(n, what, excl)
        return
    totals = ct.groupby("label")["n"].sum().sort_values(ascending=False)
    tot_df = totals.reset_index().rename(columns={"n": "total"})
    thr_by_label = {TRIGGER_LABELS.get(k, k): v for k, v in threads.items()}
    tot_df["text"] = [f"{t / n:.0%} ({t} from {thr_by_label.get(lb, 0)} sources)"
                      for lb, t in zip(tot_df["label"], tot_df["total"])]
    order = totals.index.tolist()
    y = alt.Y("label:N", sort=order, title=None, axis=_y_axis(170), scale=Y_BAND)
    bars = alt.Chart(ct).mark_bar(stroke=INK, strokeWidth=1.2, cornerRadius=0).encode(
        y=y,
        x=alt.X("n:Q", title="Lapsed SIPs", stack="zero",
                scale=alt.Scale(domain=[0, totals.max() * 2.1]), axis=_x_axis("Lapsed SIPs")),
        color=alt.Color("type:N", scale=alt.Scale(domain=["Involuntary", "Voluntary"], range=[INVOLUNTARY, VOLUNTARY]),
                        legend=alt.Legend(title=None, orient="top", labelColor=MUTED, symbolType="square")),
        order=alt.Order("type:N"),
        tooltip=[alt.Tooltip("label:N", title="Trigger"), alt.Tooltip("type:N", title="Lapse"), alt.Tooltip("n:Q", title="Records")],
    )
    labels = alt.Chart(tot_df).mark_text(align="left", dx=6, color=INK, font="IBM Plex Mono", fontSize=12).encode(
        y=alt.Y("label:N", sort=order, scale=Y_BAND), x="total:Q", text="text:N"
    )
    show(_finish((bars + labels).properties(width="container", height=alt.Step(34), title=_title(title))))
    caption(n, what, excl)


def page_behaviour():
    ss = RELEVANT["sip_status"].value_counts()
    tables = page_title(
        f"{int(ss.get('active', 0))} of {N_REL} relevant records describe an active SIP; "
        f"{int(ss.get('lapsed', 0))} describe one that lapsed",
        "Use the filters to narrow every chart below. Charts drawn on fewer than 30 records are replaced by raw counts.",
        toggle_key="tables_behaviour",
    )
    c1, c2, c3 = st.columns([2, 1, 1])
    srcs = c1.multiselect("Source", list(SOURCE_LABELS), format_func=lambda s: SOURCE_LABELS[s],
                          placeholder="All sources")
    trig = c2.selectbox("Trigger", ["All"] + list(TRIGGER_LABELS), format_func=lambda t: TRIGGER_LABELS.get(t, "All triggers"))
    lap = c3.selectbox("Lapse type", ["All"] + list(LAPSE_LABELS), format_func=lambda t: LAPSE_LABELS.get(t, "All lapse types"))

    df = RELEVANT
    parts = []
    if srcs:
        df = df[df["source"].isin(srcs)]
        parts.append(", ".join(SOURCE_LABELS[s] for s in srcs))
    if trig != "All":
        df = df[df["trigger"] == trig]
        parts.append(f"trigger = {TRIGGER_LABELS[trig]}")
    if lap != "All":
        df = df[df["lapse_type"] == lap]
        parts.append(f"lapse = {LAPSE_LABELS[lap]}")
    flt = ("filtered to " + "; ".join(parts) + " · ") if parts else ""
    excl = f"{flt}{EXCL}"
    n = len(df)
    lap_df = lapsed(df)
    inv_df = lap_df[lap_df["lapse_type"] == "involuntary"]
    vol_df = lap_df[lap_df["lapse_type"] == "voluntary"]
    missed = missed_but_active(df)
    tiles(
        [
            (f"{n}", f"relevant records in view (of {N_REL})", "neutral"),
            (f"{int((df['sip_status'] == 'active').sum())}", "active SIP", "neutral"),
            (f"{int((df['sip_status'] == 'lapsed').sum())}", "lapsed SIP", "neutral"),
            (f"{len(inv_df)}", f"involuntary lapses · {n_threads(inv_df)} independent sources", "inv"),
            (f"{len(vol_df)}", f"voluntary lapses · {n_threads(vol_df)} independent sources", "vol"),
        ]
    )
    st.markdown(
        f"<div class='small'>Missed an instalment but still investing: <b>{len(missed)}</b> "
        f"({esc(indep(missed))}). These active SIPs are not counted as lapses.</div>",
        unsafe_allow_html=True,
    )

    section("SIP status and lapses")
    left, right = st.columns(2)
    with left:
        split_block(
            df, "sip_status", STATUS_LABELS,
            lambda top, n: f"{top['label']} is the most common SIP status (N={n})",
            "relevant records by SIP status", excl=excl, tables=tables,
        )
    with right:
        lapsed_all = df[df["sip_status"] == "lapsed"]
        split_block(
            lapsed_all, "lapse_type", LAPSE_LABELS,
            lambda top, n: f"{top['label']} is the most common lapse type among lapsed SIPs (N={n})",
            "relevant records whose SIP has lapsed, by lapse type", colors=LAPSE_COLORS, excl=excl,
            tables=tables, sources=True,
        )
        st.markdown(
            "<div class='small'>Counted only where the SIP has lapsed. Involuntary (teal) = a payment, mandate "
            "or bank step ended the instalment. Voluntary (purple) = the person chose to pause, reduce or stop. "
            f"Missed an instalment but still investing: {len(missed)}.</div>",
            unsafe_allow_html=True,
        )

    section("What lies behind each lapse")
    lapse_block(lap_df, excl, tables)
    pf = df[df["trigger"] == "payment_failure"]
    pf_ps = int((pf["source"] == "play_store").sum())
    if len(pf):
        st.markdown(
            f"<div class='small'>{pf_ps} of the {len(pf)} payment failures in this view come from Play Store "
            "reviews, so their share here partly reflects where people complain. Compare sources below.</div>",
            unsafe_allow_html=True,
        )

    section("What triggers a problem")
    split_block(
        df, "trigger", TRIGGER_LABELS,
        lambda top, n: f"{top['label']} is the most common trigger (N={n})",
        "relevant records by trigger", colors={"payment_failure": INVOLUNTARY}, excl=excl, tables=tables,
        sources=True,
    )

    section("Behaviour by source")
    st.markdown(
        "Sources attract different kinds of post, so any ranking above partly reflects where people "
        "write. Compare one behaviour across sources here."
    )
    beh = st.selectbox("Behaviour", list(BEHAVIOURS))
    match, color = BEHAVIOURS[beh]
    rows = []
    for s, g in df.groupby("source"):
        hit = g[match(g)]
        rows.append({"source": s, "label": SOURCE_LABELS[s], "n": len(g), "k": len(hit), "t": n_threads(hit)})
    tbl = pd.DataFrame(rows)
    src_col = f"{beh}: independent sources"
    if tbl.empty:
        insufficient(0, pd.DataFrame({"Source": [], "Records": []}))
        caption(0, f"relevant records by source · {beh.lower()}", excl)
    else:
        big = tbl[tbl["n"] >= MIN_N].copy()
        small = tbl[tbl["n"] < MIN_N].copy()
        if len(big):
            big["value"] = big["k"] / big["n"] * 100
            big["text"] = big.apply(lambda r: f"{r['k'] / r['n']:.0%} ({r['k']} from {r['t']} sources)", axis=1)
            big["color"] = color
            hi = big.sort_values("value", ascending=False).iloc[0]
            lo = big.sort_values("value").iloc[0]
            title = (
                f"{beh}: from {hi['k']} of {hi['n']} records ({hi['value']:.0f}%) in {hi['label']} "
                f"to {lo['k']} of {lo['n']} ({lo['value']:.0f}%) in {lo['label']}"
                if len(big) > 1
                else f"{beh}: {hi['k']} of {hi['n']} records in {hi['label']}"
            ) + f" (N={int(big['n'].sum())})"
            if tables:
                finding(title)
                bt = big.sort_values("value", ascending=False).rename(
                    columns={"label": "Source", "n": "Records", "k": beh, "t": src_col})[["Source", "Records", beh, src_col]]
                bt["Share"] = (bt[beh] / bt["Records"]).map(lambda v: f"{v:.0%}")
                table(bt)
            else:
                big["label"] = big.apply(lambda r: f"{r['label']} (n={r['n']})", axis=1)
                show(hbar(big, title, x_title="% of that source's records", label_width=190))
            caption(int(big["n"].sum()), f"relevant records from sources with {MIN_N}+ records · {beh.lower()} · "
                    "independent sources = distinct threads, videos, reviews or posts", excl)
        if len(small):
            insufficient(
                int(small["n"].sum()),
                small.rename(columns={"label": "Source", "n": "Records", "k": beh, "t": src_col})[
                    ["Source", "Records", beh, src_col]],
            )
            caption(int(small["n"].sum()), f"relevant records from sources with fewer than {MIN_N} records", excl)
    footer()


# ---------------------------------------------------------------------------
# PAGE 3 - Ask the evidence
# ---------------------------------------------------------------------------
RESEARCH_QUESTIONS = [
    "Why do people start a SIP, and what do they expect to happen?",
    "What changes in their behaviour in the months after starting?",
    "What leads investors to pause, reduce or stop a SIP?",
    "What do investors check, and how often, once they have started?",
    "What confuses or worries them inside the app?",
    "What do they do outside the app when they feel unsure?",
    "What separates investors who continue from those who quietly drop off?",
    "How do these patterns differ across user segments?",
    "What unmet needs emerge consistently across conversations?",
]
TOP_K = 25
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
NOT_ANSWERABLE = "Not answerable from these posts."
INSTRUCTION = (
    "Answer only from the numbered posts below. Cite the post numbers you used in square brackets. "
    "If the posts do not answer the question, say so plainly and say what kind of evidence would be needed. "
    "Each post has a date. Whenever you cite a post, say when it was written, for example "
    "\"a Play Store review from Oct 2025 [3]\". Put the date in the sentence and keep each citation as just the "
    "post number in square brackets, like [3] or [3, 7]. If a date starts with \"approx.\", say it is approximate. "
    "If the posts you use span several years, say so. "
    "Never give investment advice. Never recommend a fund, scheme, stock or any investment action."
)
FORMAT_NOTE = (
    "Use only what a post states directly. Do not infer anything a post does not say, such as a writer's age, "
    "income, experience level, segment or who influenced them. "
    f"If the posts do not answer the question, begin your reply with the exact sentence \"{NOT_ANSWERABLE}\" "
    "Describe what the posts say in calm, neutral language, in under 220 words. "
    "Do not mention usernames or any personal details."
)

_STOP = set(
    """a an the and or but if of to in on at by for with from as is are was were be been being do does did doing
    done have has had having i me my you your he she it its we our they them their there this that these those
    what which who whom whose why how when where once after before during into out about over under again then
    than so such too very can will just should would could may might must not no nor only own same also any all
    each every some more most other both few many much up down off get got feel feels like one two make
    sip sips investor investors people person someone user users""".split()
)


def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    else:
        for suf in ("ing", "ed", "es", "s", "ly"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
        w = w[:-1]
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def _terms(text):
    words = re.findall(r"[a-z][a-z']+", str(text).lower())
    return {_stem(w.replace("'s", "").replace("'", "")) for w in words if w not in _STOP and len(w) >= 3}


@st.cache_data
def search_index(period):
    """Stemmed term sets for every relevant post in the evidence period, plus inverse document frequency."""
    docs = [(_terms(t) | _terms(q)) for t, q in zip(RELEVANT["text"], RELEVANT["quote"])]
    n = len(docs)
    df = {}
    for d in docs:
        for w in d:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
    return docs, idf


def rank_posts(question):
    """Rank relevant posts by keyword overlap with the question (IDF-weighted).
    Returns (all matching rows sorted best first, number of matching rows)."""
    docs, idf = search_index(PERIOD)
    q = _terms(question)
    scores = [sum(idf.get(w, 0) for w in q if w in d) for d in docs]
    df = RELEVANT.assign(_score=scores)
    df = df[df["_score"] > 0].sort_values(["_score", "quote_verified", "id"], ascending=[False, False, True])
    return df, len(df)


@st.cache_data
def question_match_counts(period):
    return {q: rank_posts(q)[1] for q in RESEARCH_QUESTIONS}


def _load_dotenv():
    """Read .env into the environment for local runs (never committed; never printed)."""
    p = HERE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def groq_key():
    """st.secrets first (Streamlit Cloud), then the environment (a local .env is loaded into it)."""
    try:
        key = st.secrets.get("GROQ_API_KEY")
    except Exception:  # no secrets.toml locally
        key = None
    if key:
        return key
    _load_dotenv()
    return os.environ.get("GROQ_API_KEY")


def build_posts_block(rows):
    out = []
    for i, (_, r) in enumerate(rows.iterrows(), 1):
        text = re.sub(r"\s+", " ", r["text"]).strip()[:1500]
        out.append(
            f"[{i}] Source: {SOURCE_LABELS.get(r['source'], r['source'])} · Date: {r['date_label']} · URL: {r['url']}\n{text}"
        )
    return "\n\n".join(out)


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def ask_groq(question, posts_block):
    """Call Groq. Raises on failure so errors are not cached."""
    key = groq_key()
    if not key:
        raise RuntimeError(
            "No API key found. Set GROQ_API_KEY in a local .env file, or in the app's Secrets on Streamlit Cloud."
        )
    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.2,
        "max_completion_tokens": 3000,
        "messages": [
            {"role": "system", "content": "You describe what a set of public posts say, for a research dashboard. "
                                          "You never give investment advice."},
            {"role": "user", "content": f"{INSTRUCTION}\n{FORMAT_NOTE}\n\nQuestion: {question}\n\nPosts:\n\n{posts_block}"},
        ],
    }
    resp = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=90)
    if resp.status_code != 200:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        raise RuntimeError(f"The Groq API returned status {resp.status_code}. {msg[:300]}")
    content = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError("The Groq API returned an empty answer. Try again.")
    return content


_BRACKET_RE = re.compile(r"\[([^\[\]]{1,300})\]")
_CITE_BODY_RE = re.compile(r"^(?:posts?\s*)?\d+(?:\s*(?:,|;|–|-|and)\s*\d+)*$", re.I)


def cited_numbers(answer, max_n):
    """Post numbers cited as [3], [3, 7], [3–5] or with dates attached, e.g. [3 (Oct 2025); 7 (Jan 2026)]."""
    found = []
    for raw in _BRACKET_RE.findall(answer):
        grp = re.sub(r"\([^)]*\)", "", raw).strip(" ;,")
        if not _CITE_BODY_RE.match(grp):
            continue
        grp = re.sub(r"^posts?\s*", "", grp, flags=re.I)
        for part in re.split(r"\s*(?:,|;|and)\s*", grp):
            m = re.match(r"(\d+)\s*[–-]\s*(\d+)$", part.strip())
            nums = range(int(m.group(1)), int(m.group(2)) + 1) if m else [int(part)] if part.strip().isdigit() else []
            for k in nums:
                if 1 <= k <= max_n and k not in found:
                    found.append(k)
    return sorted(found)


def _submit_box():
    st.session_state["ask_pending"] = st.session_state.get("ask_box", "").strip()


def _submit_card(q):
    st.session_state["ask_box"] = q
    st.session_state["ask_pending"] = q


def render_answer(question):
    section("Answer")
    st.markdown(f'<div class="finding">{esc(question)}</div>', unsafe_allow_html=True)
    ranked, n_match = rank_posts(question)
    if n_match == 0:
        gap_box(
            "No tagged post shares a keyword with this question, so there is nothing to answer from. "
            "Try different words, or a question about what posts describe.",
            head="No matching posts",
        )
        return
    top = ranked.head(TOP_K)
    with st.spinner(f"Reading the {len(top)} closest posts…"):
        try:
            answer = ask_groq(question, build_posts_block(top))
        except (RuntimeError, requests.RequestException) as e:
            gap_box(str(e), head="Could not get an answer")
            return

    plain = answer.lstrip("*_ #").strip()
    if plain.lower().startswith(NOT_ANSWERABLE.lower().rstrip(".")):
        rest = plain[len(NOT_ANSWERABLE):].lstrip(" *_.:\n")
        gap_box(rest or "The posts do not answer this question.", head="Not answerable from these posts")
    else:
        with st.container(key="answer_box"):
            st.markdown(answer)

    cites = cited_numbers(answer, len(top))
    section("Evidence used")
    if not cites:
        note("The answer did not cite any post.")
    for k in cites:
        evidence_card(top.iloc[k - 1], prefix=f"[{k}] ")
    note(
        f"Answered from {len(top)} tagged posts ({PERIOD_SHORT[PERIOD]}), "
        f"from {n_threads(top)} independent sources. The tagger agrees with a human "
        f"{V['human_agreement_overall']:.0%} of the time."
    )


def page_ask():
    page_title(f"Ask a question and the engine answers from {N_REL} tagged posts")
    st.text_input(
        "Your question", key="ask_box", label_visibility="collapsed", on_change=_submit_box,
        placeholder="Ask anything about why first-time investors start, continue or stop a SIP...",
    )
    st.markdown(
        f'<div class="ask-note">Answers come only from the {N_REL} tagged posts in this corpus. Questions about age, '
        "income or who influenced someone will mostly return 'not answerable' — public posts rarely state these.</div>",
        unsafe_allow_html=True,
    )
    st.button("Search the evidence", key="ask_go", type="primary", use_container_width=True, on_click=_submit_box)

    pending = st.session_state.pop("ask_pending", None)
    if pending:
        st.session_state["ask_current"] = pending
    current = st.session_state.get("ask_current")
    if current:
        render_answer(current)

    section("Or start with one of these")
    counts = question_match_counts(PERIOD)
    for row in range(0, len(RESEARCH_QUESTIONS), 3):
        cols = st.columns(3)
        for i, (col, q) in enumerate(zip(cols, RESEARCH_QUESTIONS[row: row + 3]), row):
            col.button(
                f"{q}  \n:gray[{counts[q]} matching records]",
                key=f"qcard_{i}", on_click=_submit_card, args=(q,), use_container_width=True,
            )
    note(
        f"Matching = the post shares at least one keyword with the question. The {TOP_K} closest matches are sent "
        f"to the model ({GROQ_MODEL} via Groq) · {EXCL}"
    )
    footer()


# ---------------------------------------------------------------------------
# PAGE 4 - Evidence explorer
# ---------------------------------------------------------------------------
PAGE_SIZE = 20


def page_evidence():
    verified = int(RELEVANT["quote_verified"].sum())
    page_title(
        f"{verified} of {N_REL} relevant records carry a quote verified word-for-word against the original post",
        "Search and filter the relevant records. Usernames and handles are removed from all text.",
    )
    vc = RELEVANT["source"].value_counts()
    tiles(
        [
            (f"{N_REL}", "relevant records", "neutral"),
            (f"{verified}", "with a verified quote", "neutral"),
            (f"{N_REL - verified}", "without a verified quote", "warn"),
            (f"{len(vc)}", "sources", "neutral"),
            (f"{N_FAIL}", "excluded as PARSE_FAIL", "warn"),
        ]
    )

    section("Search the evidence")
    q = st.text_input("Keyword", placeholder="Search post text and quotes, e.g. mandate, autopay, NAV")
    c1, c2, c3, c4, c5 = st.columns(5)
    srcs = c1.multiselect("Source", list(SOURCE_LABELS), format_func=lambda s: SOURCE_LABELS[s], placeholder="All")
    trigs = c2.multiselect("Trigger", list(TRIGGER_LABELS), format_func=lambda t: TRIGGER_LABELS[t], placeholder="All")
    lapses = c3.multiselect("Lapse type", list(LAPSE_LABELS), format_func=lambda t: LAPSE_LABELS[t], placeholder="All")
    stats = c4.multiselect("SIP status", list(STATUS_LABELS), format_func=lambda t: STATUS_LABELS[t], placeholder="All")
    stages = c5.multiselect("Stage", list(STAGE_LABELS), format_func=lambda t: STAGE_LABELS[t], placeholder="All")

    df = RELEVANT
    if srcs:
        df = df[df["source"].isin(srcs)]
    if trigs:
        df = df[df["trigger"].isin(trigs)]
    if lapses:
        df = df[df["lapse_type"].isin(lapses)]
    if stats:
        df = df[df["sip_status"].isin(stats)]
    if stages:
        df = df[df["stage"].isin(stages)]
    if q:
        df = df[df["text"].str.contains(q, case=False, regex=False) | df["quote"].str.contains(q, case=False, regex=False)]
    df = df.sort_values(["quote_verified", "source", "id"], ascending=[False, True, True])

    total = len(df)
    pages = max(1, -(-total // PAGE_SIZE))
    top_l, top_r = st.columns([3, 1])
    top_l.markdown(
        f'<div class="finding" style="font-size:16px">{total} of {N_REL} records '
        f'<span class="small">· {total} item{"s" if total != 1 else ""} from {n_threads(df)} independent sources</span></div>',
        unsafe_allow_html=True,
    )
    page = top_r.number_input(f"Page (of {pages})", min_value=1, max_value=pages, value=1, step=1)
    caption(total, "relevant records matching the search and filters", EXCL)

    chunk = df.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    for _, r in chunk.iterrows():
        evidence_card(
            r,
            extra_tags=f' · Status: {esc(STATUS_LABELS.get(r["sip_status"], r["sip_status"]))} · '
                       f'Stage: {esc(STAGE_LABELS.get(r["stage"], r["stage"]))}',
        )
        with st.expander("Full text", expanded=False):
            st.write(r["text"])
    if total:
        note(f"Showing {(page - 1) * PAGE_SIZE + 1}–{min(page * PAGE_SIZE, total)} of {total} records · page {page} of {pages}")
    footer()


# ---------------------------------------------------------------------------
# PAGE 5 - How far this can be trusted
# ---------------------------------------------------------------------------
def page_trust():
    page_title(
        f"Treat these findings as directional: the tagger agreed with a blind human "
        f"{V['human_agreement_overall']:.0%} of the time on {V['golden_set_n']} hand-labelled items"
    )
    tiles(
        [
            (f"{F['collected']:,}", "collected (first scrape, all years)", "neutral"),
            (f"{N_SIP_RELATED:,}", "filtered to SIP-related (first scrape, all years)", "neutral"),
            (f"{len(TAGGED) + N_FAIL:,}", f"tagged ({PERIOD_SHORT[PERIOD]})", "neutral"),
            (f"{N_FAIL}", f"PARSE_FAIL excluded ({PERIOD_SHORT[PERIOD]})", "warn"),
            (f"{N_REL}", f"relevant ({PERIOD_SHORT[PERIOD]})", "neutral"),
        ]
    )

    section("Sources")
    s = load_source_table()
    tagged_by = TAGGED["source"].value_counts()
    s["tagged"] = s["source"].map(tagged_by).fillna(0).astype(int)
    s["relevant"] = s["source"].map(N_BY_SOURCE).fillna(0).astype(int)
    s["threads"] = s["source"].map(RELEVANT.groupby("source")["thread_id"].nunique()).fillna(0).astype(int)
    dates = pd.to_datetime(TAGGED["date"], errors="coerce", format="mixed")
    rng = dates.groupby(TAGGED["source"]).agg(["min", "max"])
    s["dates"] = s["source"].map(
        lambda x: f"{rng.loc[x, 'min']:%b %Y} – {rng.loc[x, 'max']:%b %Y}" if x in rng.index else "No items in this period"
    )
    s["Source"] = s["source"].map(SOURCE_LABELS)
    s = s.sort_values("kept", ascending=False)
    tbl = s.rename(columns={
        "what": "Collected from", "kept": "Kept (SIP-related, first scrape)", "tagged": "Tagged (parsed)",
        "relevant": "Relevant", "threads": "Independent sources", "dates": "Date range (tagged)",
    })[["Source", "Collected from", "Kept (SIP-related, first scrape)", "Tagged (parsed)", "Relevant",
        "Independent sources", "Date range (tagged)"]]
    st.dataframe(
        tbl, hide_index=True, use_container_width=True, height=36 * (len(tbl) + 1) + 4,
        column_config={
            "Collected from": st.column_config.TextColumn(width="large"),
            "Kept (SIP-related, first scrape)": st.column_config.NumberColumn(format="%d"),
            "Tagged (parsed)": st.column_config.NumberColumn(format="%d"),
            "Relevant": st.column_config.NumberColumn(format="%d"),
            "Independent sources": st.column_config.NumberColumn(format="%d"),
        },
    )
    caption(
        N_SIP_RELATED, "SIP-related records by source (first scrape, all years)",
        f"tagged, relevant and date columns follow the evidence period ({PERIOD_SHORT[PERIOD]}) "
        f"and exclude {N_FAIL} PARSE_FAIL",
    )
    st.markdown(
        f"<div class='small'>Raw counts per source before filtering are not recorded in the "
        f"data files (only the {F['collected']:,} total), so they are not shown. {N_TOPUP} of the "
        f"{N_ALL_TAGGED:,} tagged items come from a later top-up collection that is not part of "
        "corpus_sip.csv, so the Kept column does not include them. YouTube only shows relative dates "
        "(\"2 years ago\"), so YouTube dates are approximate to the month.</div>",
        unsafe_allow_html=True,
    )

    section("Validation against a human")
    bf = V["by_field"]
    gs = V["golden_set_n"]
    st.markdown(
        f"A golden set of {gs} items was labelled by hand, blind, before any model output was seen. "
        f"Across all fields the tagger agreed with the human **{V['human_agreement_overall']:.0%}** of the time "
        f"({gs} items × {len(bf)} fields = {gs * len(bf)} field judgements)."
    )
    by_field = pd.DataFrame(
        [{"Field": FIELD_LABELS.get(k, k), "Items agreed": round(v * gs), "Of": gs, "Agreement": f"{v:.0%}"}
         for k, v in sorted(bf.items(), key=lambda kv: -kv[1])]
    )
    insufficient(gs, by_field)
    caption(gs, "golden-set items labelled blind by a human, agreement by field", "golden set drawn from tagged records")

    section("Model agreement with itself")
    st.markdown(
        f"The same records were tagged twice. Across all fields the two runs agreed **{V['self_consistency_two_runs']:.0%}** "
        f"of the time, but only **{V['self_consistency_trigger']:.0%}** on trigger alone. Taking a majority vote across "
        f"three runs raised trigger agreement to **{V['trigger_after_majority_vote']:.0%}**."
    )
    sc = pd.DataFrame(
        [
            {"Measure": "All fields, run 1 vs run 2", "Agreement": f"{V['self_consistency_two_runs']:.0%}"},
            {"Measure": "Trigger only, run 1 vs run 2", "Agreement": f"{V['self_consistency_trigger']:.0%}"},
            {"Measure": "Trigger, majority of 3 runs", "Agreement": f"{V['trigger_after_majority_vote']:.0%}"},
        ]
    )
    sc["Records compared"] = "not recorded in findings.json"
    st.dataframe(sc, hide_index=True, use_container_width=True, height=36 * 4 + 4)
    note("n = not recorded · model self-agreement across repeat runs · the number of records compared is not in the data files")

    section("Quotes and parse failures")
    good = int(TAGGED["quote_verified"].sum())
    n_tagged = len(TAGGED) + N_FAIL
    st.markdown(
        f"**{good} of {len(TAGGED)}** parsed records ({pct(good, len(TAGGED))}) have a quote that appears word-for-word "
        f"in the post ({PERIOD_SHORT[PERIOD]}). PARSE_FAIL rows have no quote and are left out of this count."
    )
    st.markdown(
        f"**{N_FAIL} of {n_tagged}** tagging responses ({PERIOD_SHORT[PERIOD]}) could not be parsed, so every field "
        "was recorded as `PARSE_FAIL`. These are failed API responses, not judgements, and are excluded from every "
        "count here."
    )
    if PARSE_FAIL_FIX_NOTE:
        st.markdown(f"**How it was fixed:** {PARSE_FAIL_FIX_NOTE}")

    section("How to read this dataset")

    def pf_share(src):
        g = RELEVANT[RELEVANT["source"] == src]
        k = int((g["trigger"] == "payment_failure").sum())
        return f"{pct(k, len(g))} of {SOURCE_LABELS[src]} records ({k} of {len(g)})" if len(g) else             f"not measurable for {SOURCE_LABELS[src]} (no records in this period)"

    st.markdown(
        f"""
- **Selection bias.** Public reviews over-represent people with problems. Nothing here measures how common a
  behaviour is among all investors.
- **Source mix.** Payment failures are {pf_share('play_store')} and {pf_share('youtube')}
  ({PERIOD_SHORT[PERIOD]}). Any overall ranking reflects where people complain, not why investors stop.
- **Sampling.** {N_ALL_TAGGED - N_TOPUP} of {N_SIP_RELATED:,} SIP-related records from the first scrape were
  tagged, plus {N_TOPUP} from a later top-up, weighted toward posts mentioning stopping or failure, so
  stop-related tags are over-represented by design.
- **Independent sources.** Several comments can come from one Reddit thread or YouTube video. Counts of items
  are shown next to the number of distinct threads, videos, reviews or posts they come from.
- **Lapses.** Voluntary and involuntary lapses are counted only where the SIP has lapsed. Active SIPs that
  missed an instalment are shown separately.
- **Segments.** Age, income and who influenced someone are almost never stated in public posts, so segment
  fields are mostly unclear and will be validated by interviews.
- **Model limits.** Tags come from an LLM against a fixed codebook, agreeing with a human
  {V['human_agreement_overall']:.0%} of the time and with itself {V['self_consistency_two_runs']:.0%}.
"""
    )
    footer()


PAGES = {
    "Overview": page_overview,
    "What investors do": page_behaviour,
    "Ask the evidence": page_ask,
    "Evidence explorer": page_evidence,
    "How far this can be trusted": page_trust,
}

st.markdown(CSS, unsafe_allow_html=True)
period_control()  # sets the evidence period for every page; drawn at the top of the main area
with st.sidebar:
    st.markdown(
        '<div class="sb-title">SIP Discovery Engine</div>'
        '<div class="sb-sub">Why first-time SIP investors stop, read from public posts</div>',
        unsafe_allow_html=True,
    )
    choice = st.radio("Page", list(PAGES), label_visibility="collapsed")
    st.markdown(
        f'<div class="sb-foot">{N_REL} relevant records · {N_FAIL} excluded · Not investment advice</div>',
        unsafe_allow_html=True,
    )
PAGES[choice]()
