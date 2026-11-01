"""Tema paleti ve Kontrol Odası CSS dili."""
from __future__ import annotations

from typing import Dict

THEMES: Dict[str, Dict[str, str]] = {
    "standart": {
        "label": "🎛️ Kontrol Odası (Standart)",
        "bg": "#06080c", "s1": "#0c1017", "s2": "#10151e", "s3": "#151b26",
        "inset": "#080b10", "line": "rgba(151,167,195,.13)", "line2": "rgba(151,167,195,.24)",
        "text": "#edf1f7", "t2": "#b9c3d4", "muted": "#7d889d",
        "accent": "#ff4d5e", "accent2": "#ff6b7a", "soft": "rgba(255,77,94,.12)",
        "ok": "#3ddc97", "ok_soft": "rgba(61,220,151,.11)",
        "warn": "#ffc247", "warn_soft": "rgba(255,194,71,.11)",
        "info": "#6ea8ff", "info_soft": "rgba(110,168,255,.11)",
        "purple": "#c47bff", "purple_soft": "rgba(196,123,255,.10)",
        "sidebar_bg": "#080b11", "card": "#0c1017",
    },
    "aydinlik": {
        "label": "☀️ Aydınlık Stüdyo",
        "bg": "#f5f6f8", "s1": "#ffffff", "s2": "#eef0f4", "s3": "#e4e8ee",
        "inset": "#ffffff", "line": "rgba(20,30,50,.10)", "line2": "rgba(20,30,50,.20)",
        "text": "#141821", "t2": "#3c4657", "muted": "#6b7688",
        "accent": "#e11d48", "accent2": "#f43f5e", "soft": "rgba(225,29,72,.10)",
        "ok": "#0a9b64", "ok_soft": "rgba(10,155,100,.10)",
        "warn": "#b45309", "warn_soft": "rgba(180,83,9,.10)",
        "info": "#2563eb", "info_soft": "rgba(37,99,235,.10)",
        "purple": "#7c3aed", "purple_soft": "rgba(124,58,237,.10)",
        "sidebar_bg": "#ffffff", "card": "#ffffff",
    },
    "okyanus": {
        "label": "🌊 Okyanus",
        "bg": "#050a12", "s1": "#0a1220", "s2": "#0e1828", "s3": "#132034",
        "inset": "#04080f", "line": "rgba(120,170,220,.13)", "line2": "rgba(120,170,220,.26)",
        "text": "#e9f1fa", "t2": "#aec4da", "muted": "#6f85a0",
        "accent": "#4da3ff", "accent2": "#79bcff", "soft": "rgba(77,163,255,.13)",
        "ok": "#34d399", "ok_soft": "rgba(52,211,153,.11)",
        "warn": "#fbbf24", "warn_soft": "rgba(251,191,36,.11)",
        "info": "#38bdf8", "info_soft": "rgba(56,189,248,.11)",
        "purple": "#a78bfa", "purple_soft": "rgba(167,139,250,.10)",
        "sidebar_bg": "#060c17", "card": "#0a1220",
    },
    "orman": {
        "label": "🌿 Orman",
        "bg": "#060b09", "s1": "#0b1410", "s2": "#0f1a15", "s3": "#14211b",
        "inset": "#040806", "line": "rgba(130,190,160,.13)", "line2": "rgba(130,190,160,.26)",
        "text": "#eaf4ee", "t2": "#b2c8bc", "muted": "#75897d",
        "accent": "#2dd4a0", "accent2": "#5fe3ba", "soft": "rgba(45,212,160,.12)",
        "ok": "#2dd4a0", "ok_soft": "rgba(45,212,160,.12)",
        "warn": "#fbbf24", "warn_soft": "rgba(251,191,36,.11)",
        "info": "#5eead4", "info_soft": "rgba(94,234,212,.10)",
        "purple": "#c4b5fd", "purple_soft": "rgba(196,181,253,.10)",
        "sidebar_bg": "#070e0b", "card": "#0b1410",
    },
}


_CSS_TEMPLATE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
  --bg: __BG__; --s1: __S1__; --s2: __S2__; --s3: __S3__; --inset: __INSET__;
  --line: __LINE__; --line2: __LINE2__;
  --text: __TEXT__; --t2: __T2__; --muted: __MUTED__;
  --accent: __ACCENT__; --accent2: __ACCENT2__; --soft: __SOFT__;
  --ok: __OK__; --ok-soft: __OK_SOFT__; --warn: __WARN__; --warn-soft: __WARN_SOFT__;
  --info: __INFO__; --info-soft: __INFO_SOFT__; --purple: __PURPLE__; --purple-soft: __PURPLE_SOFT__;
  --sans: "Inter", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "Cascadia Mono", monospace;
}

.stApp { background: var(--bg); color: var(--text); font-family: var(--sans); }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { visibility: hidden !important; }

/* Kenar çubuğu aç/kapa kontrolleri — her durumda görünür */
[data-testid="stExpandSidebarButton"] {
  visibility: visible !important; display: flex !important; opacity: 1 !important;
  z-index: 100100 !important;
  background: var(--s2) !important; border: 1px solid var(--line2) !important;
  border-radius: 9px !important; color: var(--t2) !important;
  box-shadow: 0 6px 18px rgba(0,0,0,.25) !important;
}
[data-testid="stExpandSidebarButton"]:hover { border-color: var(--accent) !important; color: var(--accent) !important; }
[data-testid="stExpandSidebarButton"] svg { stroke: currentColor !important; fill: currentColor !important; }
[data-testid="stSidebarCollapseButton"] {
  visibility: visible !important; opacity: 1 !important; color: var(--t2) !important;
}
[data-testid="stSidebarCollapseButton"]:hover { color: var(--accent) !important; }
.block-container { padding: 2.4rem 2.6rem 4rem !important; max-width: 1480px; }

h1, h2, h3, h4 { color: var(--text) !important; font-family: var(--sans) !important; letter-spacing: -0.02em; }
h1 { font-weight: 800 !important; font-size: 1.72rem !important; }
h2 { font-weight: 700 !important; font-size: 1.22rem !important; }
h3 { font-weight: 600 !important; font-size: 1.02rem !important; }
p, span, label { color: var(--t2); }
hr { border-color: var(--line) !important; }
a { color: var(--accent); }

/* Sol panel */
section[data-testid="stSidebar"] {
  background: var(--sidebar-bg) !important;
  border-right: 1px solid var(--line) !important;
}
section[data-testid="stSidebar"] .block-container { padding: 1.6rem 1.2rem 2rem !important; }

/* Navigasyon (radio → menü öğesi) */
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] label {
  background: transparent; border: 1px solid transparent; border-radius: 9px;
  padding: 7px 12px !important; margin: 0 !important; width: 100%;
  transition: background .15s ease, border-color .15s ease;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: var(--s3); }
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none; }
section[data-testid="stSidebar"] div[role="radiogroup"] label { color: var(--t2); font-size: .93rem; font-weight: 500; }
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
  background: var(--soft) !important; border-color: var(--accent) !important; color: var(--text) !important;
}

/* Butonlar */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 9px !important; font-weight: 600 !important; font-family: var(--sans) !important;
  border: 1px solid var(--line2) !important;
  background: var(--s2) !important; color: var(--text) !important;
  transition: all .15s ease !important;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--accent) !important; color: var(--accent) !important; }
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  background: var(--accent) !important; color: #fff !important; border-color: var(--accent) !important;
}
.stButton > button[kind="primary"]:hover { background: var(--accent2) !important; }

/* Form öğeleri */
.stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input, .stTimeInput input {
  background: var(--s2) !important; color: var(--text) !important;
  border: 1px solid var(--line2) !important; border-radius: 9px !important;
  font-family: var(--sans) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--soft) !important; }
div[data-baseweb="select"] > div {
  background: var(--s2) !important; color: var(--text) !important;
  border: 1px solid var(--line2) !important; border-radius: 9px !important;
}
div[data-baseweb="popover"] > div { background: var(--s2) !important; border: 1px solid var(--line2) !important; }
.stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label, .stCheckbox label { color: var(--t2) !important; font-size: .88rem !important; }

/* Sekme benzeri açılır paneller */
details[data-testid="stExpander"] {
  background: var(--s1) !important; border: 1px solid var(--line) !important;
  border-radius: 11px !important; overflow: hidden;
}
details[data-testid="stExpander"] summary { color: var(--text) !important; font-weight: 600; }

/* Uyarı kutuları */
div[data-testid="stAlert"] { background: var(--s2) !important; border: 1px solid var(--line2) !important; border-radius: 10px !important; }
div[data-testid="stAlert"] p { color: var(--t2) !important; }

/* Tablo */
.stDataFrame { border: 1px solid var(--line) !important; border-radius: 11px !important; overflow: hidden !important; }
div[data-testid="stDataFrame"] { border-radius: 11px !important; }

/* Serbest içerik tipografisi */
.stMarkdown { font-family: var(--sans); }

/* Kaydırma çubuğu */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--s3); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: var(--line2); }

/* Panel bileşenleri */
.cd-kpi {
  background: var(--card); border: 1px solid var(--line); border-radius: 13px;
  padding: 18px 20px; position: relative; overflow: hidden;
}
.cd-kpi::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: var(--kc, var(--accent));
}
.cd-kpi .cd-kpi-label {
  font-family: var(--mono); font-size: .72rem; font-weight: 600;
  letter-spacing: .09em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px;
}
.cd-kpi .cd-kpi-value { font-size: 1.85rem; font-weight: 800; color: var(--text); line-height: 1.1; }
.cd-kpi .cd-kpi-sub { font-size: .8rem; color: var(--muted); margin-top: 6px; }

.cd-panel {
  background: var(--card); border: 1px solid var(--line); border-radius: 13px; padding: 20px 22px;
}
.cd-panel-title {
  font-family: var(--mono); font-size: .74rem; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 12px;
  display: flex; align-items: center; gap: 8px;
}
.cd-panel-title::before { content: ""; width: 7px; height: 7px; border-radius: 2px; background: var(--accent); }

.cd-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--mono); font-size: .72rem; font-weight: 600;
  padding: 3px 10px; border-radius: 999px; border: 1px solid var(--bc, var(--line2));
  background: var(--bsoft, var(--s2)); color: var(--bcolor, var(--t2));
}
.cd-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--bcolor, var(--muted)); }

.cd-agent {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px;
  transition: border-color .15s ease;
}
.cd-agent:hover { border-color: var(--line2); }
.cd-agent .cd-agent-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.cd-agent .cd-agent-icon {
  width: 34px; height: 34px; border-radius: 9px; display: flex; align-items: center; justify-content: center;
  background: var(--soft); font-size: 1.05rem; border: 1px solid var(--line2);
}
.cd-agent .cd-agent-name { font-weight: 700; font-size: .95rem; color: var(--text); }
.cd-agent .cd-agent-role { font-family: var(--mono); font-size: .7rem; color: var(--muted); letter-spacing: .06em; }
.cd-agent .cd-agent-desc { font-size: .82rem; color: var(--t2); line-height: 1.45; }

/* İçerik ajanı paneli */
.cd-agent-panel {
  background: linear-gradient(135deg, var(--soft) 0%, transparent 48%), var(--card);
  border: 1px solid var(--line2); border-radius: 14px; padding: 18px 20px;
}
.cd-agent-panel-head { display: flex; align-items: center; gap: 12px; }
.cd-agent-panel-icon {
  width: 42px; height: 42px; border-radius: 11px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 1.3rem;
  background: var(--soft); border: 1px solid var(--line2);
}
.cd-agent-panel-name { font-weight: 800; font-size: 1.02rem; color: var(--text); }
.cd-agent-panel-role {
  font-family: var(--mono); font-size: .66rem; color: var(--muted);
  letter-spacing: .1em; text-transform: uppercase;
}
.cd-agent-panel-desc { color: var(--t2); font-size: .87rem; line-height: 1.6; margin-top: 11px; }

/* Ajan öneri kartı */
.cd-proposal {
  background: var(--card); border: 1px solid var(--line2); border-radius: 14px;
  padding: 22px 24px; position: relative; overflow: hidden;
}
.cd-proposal::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: linear-gradient(var(--accent), var(--purple));
}
.cd-proposal-kicker {
  font-family: var(--mono); font-size: .68rem; font-weight: 600; letter-spacing: .12em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 7px;
}
.cd-proposal-name { font-size: 1.2rem; font-weight: 800; color: var(--text); letter-spacing: -.01em; }
.cd-proposal-title { font-family: var(--mono); font-size: .8rem; color: var(--info); margin-top: 5px; }
.cd-hook {
  margin-top: 15px; padding: 12px 15px; border-radius: 10px;
  background: var(--s1); border: 1px solid var(--line);
  color: var(--t2); font-size: .9rem; line-height: 1.6; font-style: italic;
}
.cd-scenes { margin-top: 14px; }
.cd-scene {
  display: flex; gap: 14px; padding: 9px 0; border-bottom: 1px dashed var(--line);
  font-size: .86rem; color: var(--t2); line-height: 1.5;
}
.cd-scene:last-child { border-bottom: none; padding-bottom: 0; }
.cd-scene-time {
  font-family: var(--mono); font-size: .68rem; font-weight: 600;
  color: var(--accent); min-width: 58px; padding-top: 2px;
}
.cd-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px; }
.cd-meta { background: var(--s1); border: 1px solid var(--line); border-radius: 10px; padding: 11px 13px; }
.cd-meta-label {
  font-family: var(--mono); font-size: .63rem; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 5px;
}
.cd-meta-value { font-size: .82rem; color: var(--t2); line-height: 1.45; }

/* ViewMade bağlantı ve önizleme kartları */
.cd-conn {
  background: linear-gradient(135deg, var(--ok-soft) 0%, transparent 55%), var(--card);
  border: 1px solid var(--line2); border-radius: 14px; padding: 18px 20px;
}
.cd-conn.is-warn { background: linear-gradient(135deg, var(--warn-soft) 0%, transparent 55%), var(--card); }
.cd-conn-head { display: flex; align-items: center; gap: 12px; }
.cd-conn-icon {
  width: 42px; height: 42px; border-radius: 11px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 1.25rem;
  background: var(--ok-soft); border: 1px solid var(--ok);
}
.cd-conn.is-warn .cd-conn-icon { background: var(--warn-soft); border-color: var(--warn); }
.cd-conn-name { font-weight: 800; font-size: 1rem; color: var(--text); }
.cd-conn-sub { font-family: var(--mono); font-size: .67rem; color: var(--muted); letter-spacing: .08em; }
.cd-conn-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.cd-conn-stat { background: var(--s1); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.cd-conn-label {
  font-family: var(--mono); font-size: .62rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 4px;
}
.cd-conn-value { font-size: .84rem; font-weight: 600; color: var(--text); }
.cd-video-card {
  background: var(--card); border: 1px solid var(--line); border-radius: 13px;
  padding: 16px 18px;
}
.cd-video-title { font-weight: 700; font-size: .94rem; color: var(--text); line-height: 1.35; }
.cd-video-sub {
  font-family: var(--mono); font-size: .68rem; color: var(--muted);
  margin-top: 5px; letter-spacing: .03em;
}
.cd-publish-note {
  background: var(--s1); border: 1px solid var(--line2); border-left: 3px solid var(--warn);
  border-radius: 0 10px 10px 0; padding: 12px 14px; color: var(--t2);
  font-size: .84rem; line-height: 1.55;
}

/* Üretim masası — görünüm seçici */
div[data-testid="stSegmentedControl"] { margin: 2px 0 18px; }
div[data-testid="stSegmentedControl"] button {
  font-family: var(--mono); font-size: .74rem; letter-spacing: .03em;
}

/* ViewMade üretim künyesi */
.cd-prod-info {
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 20px 22px; margin-top: 4px;
}
.cd-prod-kicker {
  font-family: var(--mono); font-size: .64rem; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 7px;
}
.cd-prod-title { font-size: 1.18rem; font-weight: 800; color: var(--text); line-height: 1.35; }
.cd-prod-sub {
  font-family: var(--mono); font-size: .69rem; color: var(--muted);
  letter-spacing: .03em; margin-top: 6px;
}
.cd-prod-desc { color: var(--t2); font-size: .88rem; line-height: 1.65; margin-top: 13px; }
.cd-chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 13px; }
.cd-chip {
  display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 999px;
  background: var(--s1); border: 1px solid var(--line2);
  font-family: var(--mono); font-size: .66rem; color: var(--t2);
}
.cd-spec-grid {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px; margin-top: 15px;
}
.cd-spec {
  background: var(--s1); border: 1px solid var(--line); border-radius: 10px;
  padding: 9px 11px; min-width: 0;
}
.cd-spec-label {
  font-family: var(--mono); font-size: .59rem; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 4px;
}
.cd-spec-value {
  font-size: .8rem; font-weight: 650; color: var(--text); line-height: 1.35;
  overflow-wrap: anywhere;
}
.cd-info-section {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 16px 18px; margin-top: 10px;
}
.cd-info-section-title {
  font-family: var(--mono); font-size: .65rem; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 10px;
}
.cd-source-item {
  display: flex; gap: 10px; padding: 7px 0; border-bottom: 1px dashed var(--line);
  font-size: .81rem; line-height: 1.5;
}
.cd-source-item:last-child { border-bottom: none; padding-bottom: 0; }
.cd-source-index {
  font-family: var(--mono); font-size: .63rem; color: var(--accent);
  min-width: 22px; padding-top: 2px;
}
.cd-source-item a { color: var(--t2); text-decoration: none; }
.cd-source-item a:hover { color: var(--text); text-decoration: underline; }
.cd-source-url {
  display: block; font-family: var(--mono); font-size: .62rem;
  color: var(--muted); margin-top: 2px; overflow-wrap: anywhere;
}
.cd-attr {
  font-size: .79rem; color: var(--t2); line-height: 1.55; padding: 6px 0;
  border-bottom: 1px dashed var(--line);
}
.cd-attr:last-child { border-bottom: none; padding-bottom: 0; }
.cd-subject-note {
  background: var(--info-soft); border: 1px solid var(--info); border-radius: 11px;
  padding: 13px 15px; margin-top: 10px; color: var(--t2);
  font-size: .82rem; line-height: 1.6;
}
.cd-subject-note b {
  display: block; font-family: var(--mono); font-size: .62rem; letter-spacing: .1em;
  text-transform: uppercase; color: var(--info); margin-bottom: 5px;
}
@media (max-width: 900px) {
  .cd-conn-stats { grid-template-columns: 1fr 1fr; }
  .cd-meta-grid { grid-template-columns: 1fr; }
  .cd-spec-grid { grid-template-columns: 1fr 1fr; }
}

.cd-stage {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 8px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--s1);
}
.cd-stage.cd-stage-done { border-color: var(--ok); background: var(--ok-soft); }
.cd-stage.cd-stage-active { border-color: var(--accent); background: var(--soft); }
.cd-stage .cd-stage-icon { font-size: 1.25rem; }
.cd-stage .cd-stage-name { font-size: .78rem; font-weight: 600; color: var(--text); }
.cd-stage .cd-stage-state { font-family: var(--mono); font-size: .66rem; color: var(--muted); }

.cd-log {
  font-family: var(--mono); font-size: .78rem; padding: 8px 12px;
  border-left: 2px solid var(--line2); margin-bottom: 6px; background: var(--s1); border-radius: 0 8px 8px 0;
}
.cd-log .cd-log-ts { color: var(--muted); margin-right: 10px; }
.cd-log.cd-log-ok { border-left-color: var(--ok); }
.cd-log.cd-log-warn { border-left-color: var(--warn); }
.cd-log.cd-log-err { border-left-color: var(--accent); }

.cd-brand { display: flex; align-items: center; gap: 11px; margin-bottom: 18px; }
.cd-brand-mark {
  width: 38px; height: 38px; border-radius: 10px; background: var(--accent);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.cd-brand-name { font-weight: 800; font-size: .98rem; color: var(--text); line-height: 1.15; }
.cd-brand-sub { font-family: var(--mono); font-size: .64rem; color: var(--muted); letter-spacing: .14em; text-transform: uppercase; }

.cd-hero {
  background: linear-gradient(135deg, var(--soft) 0%, transparent 55%), var(--card);
  border: 1px solid var(--line); border-radius: 16px; padding: 26px 30px; margin-bottom: 22px;
}
.cd-hero h1 { margin: 0 0 6px 0 !important; }
.cd-hero p { margin: 0; color: var(--t2); font-size: .92rem; }
.cd-hero.cd-hero-compact { padding: 20px 24px; margin-bottom: 16px; }
.cd-page-kicker {
  font-family: var(--mono); font-size: .66rem; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 7px;
}
.cd-hero .cd-chip-row { margin-top: 12px; }

/* Odak kartları — "şimdi ne yapmalıyım" kuyruğu */
.cd-focus {
  background: var(--card); border: 1px solid var(--line); border-radius: 13px;
  padding: 16px 18px; min-height: 128px; position: relative; overflow: hidden;
}
.cd-focus::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: var(--fc, var(--accent));
}
.cd-focus.focus-warn { --fc: var(--warn); }
.cd-focus.focus-ok { --fc: var(--ok); }
.cd-focus.focus-info { --fc: var(--info); }
.cd-focus.focus-muted { --fc: var(--muted); }
.cd-focus.is-idle { opacity: .66; }
.cd-focus-kicker {
  font-family: var(--mono); font-size: .62rem; font-weight: 700; letter-spacing: .11em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 7px;
}
.cd-focus-title { font-size: .98rem; font-weight: 750; color: var(--text); line-height: 1.35; }
.cd-focus-meta { font-size: .78rem; color: var(--muted); line-height: 1.5; margin-top: 6px; }

/* Beş aşamalı yaşam döngüsü */
.cd-lifecycle { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.cd-lc {
  background: var(--s1); border: 1px solid var(--line); border-radius: 11px; padding: 13px 14px;
}
.cd-lc.is-bottleneck { border-color: var(--warn); background: var(--warn-soft); }
.cd-lc.is-zero { opacity: .55; }
.cd-lc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cd-lc-icon { font-size: 1rem; }
.cd-lc-count { font-family: var(--mono); font-size: 1.12rem; font-weight: 700; color: var(--text); }
.cd-lc-label { font-weight: 650; font-size: .8rem; color: var(--text); margin-top: 6px; }
.cd-lc-meta {
  font-family: var(--mono); font-size: .61rem; color: var(--muted);
  letter-spacing: .05em; margin-top: 2px;
}

/* Adım şeridi — yayın sihirbazı ve otomasyon döngüsü */
.cd-stepbar {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0;
  border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
  margin-bottom: 14px; background: var(--card);
}
.cd-stepbar.cd-stepbar-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.cd-step {
  display: flex; align-items: center; gap: 10px; padding: 12px 14px;
  border-right: 1px solid var(--line);
}
.cd-step:last-child { border-right: none; }
.cd-step-num {
  width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-family: var(--mono); font-size: .7rem; font-weight: 700;
  border: 1px solid var(--line2); color: var(--muted); background: var(--s1); flex-shrink: 0;
}
.cd-step.is-done .cd-step-num { background: var(--ok-soft); border-color: var(--ok); color: var(--ok); }
.cd-step.is-active .cd-step-num { background: var(--accent); border-color: var(--accent); color: #fff; }
.cd-step-label { font-size: .81rem; font-weight: 650; color: var(--text); }
.cd-step-meta { font-family: var(--mono); font-size: .61rem; color: var(--muted); letter-spacing: .04em; }

/* Yayın kapıları */
.cd-gates { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin: 12px 0; }
.cd-gate {
  display: flex; align-items: flex-start; gap: 10px; padding: 9px 14px;
  border-bottom: 1px solid var(--line); background: var(--card);
}
.cd-gate:last-child { border-bottom: none; }
.cd-gate-icon { font-family: var(--mono); font-size: .72rem; font-weight: 700; width: 18px; text-align: center; }
.cd-gate.is-ok .cd-gate-icon { color: var(--ok); }
.cd-gate.is-no .cd-gate-icon { color: var(--warn); }
.cd-gate-label { font-size: .81rem; font-weight: 650; color: var(--text); }
.cd-gate-detail { font-size: .73rem; color: var(--muted); margin-top: 1px; }

/* Boş durum */
.cd-empty { background: var(--s1); border: 1px dashed var(--line2); border-radius: 12px; padding: 18px 20px; }
.cd-empty-title { font-weight: 700; color: var(--text); font-size: .9rem; }
.cd-empty-body { color: var(--t2); font-size: .82rem; line-height: 1.6; margin-top: 4px; }

/* Sistem mini paneli (kenar çubuğu) */
.cd-sys { border: 1px solid var(--line); border-radius: 11px; background: var(--s1); padding: 10px 12px; margin: 4px 0 12px; }
.cd-sys-row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 4px 0; font-size: .76rem;
}
.cd-sys-label {
  color: var(--muted); font-family: var(--mono); font-size: .63rem;
  letter-spacing: .06em; text-transform: uppercase;
}
.cd-sys-value { color: var(--text); font-weight: 600; }
.cd-sys-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 5px; background: var(--ok); }
.cd-sys-dot.is-warn { background: var(--warn); }
.cd-sys-dot.is-off { background: var(--muted); }

/* Ajan aşama haritası */
.cd-agentmap { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
.cd-agentmap .cd-stage {
  align-items: flex-start; padding: 10px 12px;
  background: var(--s1); border-color: var(--line);
}
.cd-agentmap .cd-stage.is-off { opacity: .55; }
.cd-agentmap .cd-stage-name { font-size: .74rem; }
.cd-agentmap .cd-stage-state { font-size: .64rem; text-align: left; line-height: 1.45; }

/* Tema önizleme kartları */
.cd-theme { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 13px 14px; }
.cd-theme.is-active { border-color: var(--accent); background: var(--soft); }
.cd-theme-sw { display: flex; gap: 5px; margin-bottom: 9px; }
.cd-theme-sw span {
  width: 18px; height: 18px; border-radius: 5px;
  border: 1px solid rgba(127,127,127,.25);
}
.cd-theme-name { font-weight: 700; font-size: .82rem; color: var(--text); }
.cd-theme-state {
  font-family: var(--mono); font-size: .6rem; letter-spacing: .09em;
  color: var(--muted); margin-top: 3px;
}

/* Yayındaki içerik satırları */
.cd-pub-row {
  display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
  padding: 8px 0; border-bottom: 1px dashed var(--line); font-size: .82rem;
}
.cd-pub-row:last-child { border-bottom: none; padding-bottom: 0; }
.cd-pub-row a { color: var(--t2); text-decoration: none; }
.cd-pub-row a:hover { color: var(--text); text-decoration: underline; }
.cd-pub-date { font-family: var(--mono); font-size: .63rem; color: var(--muted); white-space: nowrap; }

@media (max-width: 1100px) {
  .cd-lifecycle { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .cd-agentmap { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .cd-stepbar, .cd-stepbar.cd-stepbar-4 { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 760px) {
  .cd-lifecycle, .cd-agentmap { grid-template-columns: 1fr 1fr; }
  .cd-stepbar, .cd-stepbar.cd-stepbar-4 { grid-template-columns: 1fr; }
  .cd-step { border-right: none; border-bottom: 1px solid var(--line); }
}

/* ============================================================
   Erişilebilirlik — görünür klavye odağı ve hareket duyarlılığı
   ============================================================ */
:focus-visible {
  outline: 2px solid var(--accent) !important;
  outline-offset: 2px !important;
}
.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible,
.stLinkButton > a:focus-visible,
section[data-testid="stSidebar"] button:focus-visible,
div[data-testid="stSegmentedControl"] button:focus-visible,
div[data-baseweb="select"] div:focus-visible,
.stTextInput input:focus-visible,
.stTextArea textarea:focus-visible {
  outline: 2px solid var(--accent) !important;
  outline-offset: 2px !important;
}
div[data-testid="stExpander"] summary:focus-visible { outline-offset: -2px !important; }
.cd-pub-row a:focus-visible,
.cd-source-item a:focus-visible { outline-offset: 1px !important; }

/* Durum her zaman yalnızca renkle anlatılmaz: nokta + metin + simge birlikte */
.cd-badge .cd-dot { box-shadow: 0 0 0 2px var(--bsoft, transparent); }
.cd-gate-icon { font-weight: 800; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition: none !important;
    animation: none !important;
  }
}

/* ============================================================
   Duyarlı yerleşim — 1100 px altında sütunlar sarar
   ============================================================ */
div[data-testid="stVideo"] video { max-width: 100%; height: auto; }

@media (max-width: 1100px) {
  .block-container { padding: 1.7rem 1.3rem 3rem !important; }
  section[data-testid="stSidebar"] .block-container { padding: 1.2rem .9rem 1.6rem !important; }
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; row-gap: 10px !important; }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 250px !important;
    flex: 1 1 250px !important;
  }
  .cd-hero { padding: 22px 20px; }
  .cd-conn-stats { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 760px) {
  .block-container { padding: 1rem .7rem 2.4rem !important; }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  .cd-hero, .cd-hero.cd-hero-compact { padding: 18px 16px; }
  .cd-kpi { padding: 14px 16px; }
  .cd-kpi .cd-kpi-value { font-size: 1.45rem; }
  .cd-panel, .cd-video-card, .cd-prod-info { padding: 15px 14px; }
  .cd-spec-grid, .cd-meta-grid { grid-template-columns: 1fr; }
}
</style>
"""


def theme_css(theme: Dict[str, str]) -> str:
    css = _CSS_TEMPLATE
    replacements = {
        "__BG__": theme["bg"], "__S1__": theme["s1"], "__S2__": theme["s2"],
        "__S3__": theme["s3"], "__INSET__": theme["inset"], "__LINE__": theme["line"],
        "__LINE2__": theme["line2"], "__TEXT__": theme["text"], "__T2__": theme["t2"],
        "__MUTED__": theme["muted"], "__ACCENT__": theme["accent"], "__ACCENT2__": theme["accent2"],
        "__SOFT__": theme["soft"], "__OK__": theme["ok"], "__OK_SOFT__": theme["ok_soft"],
        "__WARN__": theme["warn"], "__WARN_SOFT__": theme["warn_soft"],
        "__INFO__": theme["info"], "__INFO_SOFT__": theme["info_soft"],
        "__PURPLE__": theme["purple"], "__PURPLE_SOFT__": theme["purple_soft"],
    }
    for key, value in replacements.items():
        css = css.replace(key, value)
    return css
