#!/usr/bin/env python
"""Cats & Dogs Documentary — YouTube Otomasyon Stüdyosu.

Profesyonel yönetim paneli:
  • Genel Bakış        – kanal KPI'ları, kota, hat durumu
  • Video Üretim       – planlama → senaryo → üretim → inceleme → yayın hattı
  • Ajanlar            – 7 uzman otomasyon ajanı
  • İstatistikler      – profesyonel YouTube analitiği
  • Otomasyon          – planlama / uygulama / izleme / geliştirme döngüsü
  • Ayarlar            – yalnızca düzenlenebilir ayarlar (kod görünmez)

Tema sistemi: Standart (Kontrol Odası), Aydınlık Stüdyo, Okyanus, Orman.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "cddocs"))
sys.path.insert(0, str(BASE_DIR / "src"))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from dotenv import load_dotenv

load_dotenv()

from youtube.config import YouTubeConfig
from youtube.token_manager import TokenManager
from youtube.api_client import YouTubeAPIClient
from youtube.upload import UploadManager
from youtube.analytics import AnalyticsReporter
from youtube.oauth_flow import OAuthFlowManager

try:
    from youtube.video_production import VideoProductionManager, VideoProviderError
    PRODUCTION_READY = True
except ImportError:
    PRODUCTION_READY = False

# ============================================================================
# Kalıcı Ayarlar
# ============================================================================
ROOT = BASE_DIR
SETTINGS_FILE = ROOT / "panel_settings.json"
PIPELINE_FILE = ROOT / "production_pipeline.json"
ACTIVITY_FILE = ROOT / "activity_log.json"

# Dikey (9:16) önizlemeler için ideal genişlikler — piksel cinsinden.
PREVIEW_WIDTH = 320
GALLERY_PREVIEW_WIDTH = 220

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "standart",
    "default_privacy": "unlisted",
    "category_id": "15",
    "channel_name": "",
    "channel_desc": "",
    "auto_upload": False,
    "auto_schedule": False,
    "max_daily": 5,
    "preferred_post_time": "14:00",
    "posting_frequency": "Haftada 3",
    "agents_enabled": {
        "strategy": True, "script": True, "seo": True, "thumbnail": True,
        "production": True, "publishing": True, "analytics": True,
    },
    "default_provider": "slideshow",
    "video_duration": 60,
    "aspect_ratio": "16:9",
}


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for key, value in stored.items():
                if key == "agents_enabled" and isinstance(value, dict):
                    merged = dict(DEFAULT_SETTINGS["agents_enabled"])
                    merged.update(value)
                    data[key] = merged
                else:
                    data[key] = value
        except (json.JSONDecodeError, OSError):
            pass
    return data


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load_pipeline() -> List[Dict[str, Any]]:
    if PIPELINE_FILE.exists():
        try:
            return json.loads(PIPELINE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_pipeline(items: List[Dict[str, Any]]) -> None:
    try:
        PIPELINE_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def log_activity(message: str, kind: str = "info") -> None:
    entries: List[Dict[str, Any]] = []
    if ACTIVITY_FILE.exists():
        try:
            entries = json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.insert(0, {"ts": datetime.now().strftime("%d.%m %H:%M"), "msg": message, "kind": kind})
    entries = entries[:200]
    try:
        ACTIVITY_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


SETTINGS = load_settings()

# ============================================================================
# Tema Sistemi
# ============================================================================
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

THEME = THEMES.get(SETTINGS.get("theme", "standart"), THEMES["standart"])

# ============================================================================
# CSS — Kontrol Odası tasarım dili (editoryal, tek vurgu rengi, ince hatlar)
# ============================================================================
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
@media (max-width: 900px) {
  .cd-conn-stats { grid-template-columns: 1fr 1fr; }
  .cd-meta-grid { grid-template-columns: 1fr; }
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
</style>
"""


def theme_css() -> str:
    css = _CSS_TEMPLATE
    replacements = {
        "__BG__": THEME["bg"], "__S1__": THEME["s1"], "__S2__": THEME["s2"],
        "__S3__": THEME["s3"], "__INSET__": THEME["inset"], "__LINE__": THEME["line"],
        "__LINE2__": THEME["line2"], "__TEXT__": THEME["text"], "__T2__": THEME["t2"],
        "__MUTED__": THEME["muted"], "__ACCENT__": THEME["accent"], "__ACCENT2__": THEME["accent2"],
        "__SOFT__": THEME["soft"], "__OK__": THEME["ok"], "__OK_SOFT__": THEME["ok_soft"],
        "__WARN__": THEME["warn"], "__WARN_SOFT__": THEME["warn_soft"],
        "__INFO__": THEME["info"], "__INFO_SOFT__": THEME["info_soft"],
        "__PURPLE__": THEME["purple"], "__PURPLE_SOFT__": THEME["purple_soft"],
    }
    for key, value in replacements.items():
        css = css.replace(key, value)
    return css


st.set_page_config(
    page_title="YouTube Otomasyon Stüdyosu",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(theme_css(), unsafe_allow_html=True)

# ============================================================================
# OAuth dönüşü — Google ?code= ile panele geri dönerse otomatik tamamlama
# ============================================================================
_qp = st.query_params
_ghx_code = _qp.get("code")
if _ghx_code:
    if isinstance(_ghx_code, list):
        _ghx_code = _ghx_code[0] if _ghx_code else None
    _ghx_ok = False
    try:
        _ghx_tokens = OAuthFlowManager(get_config()).exchange_code(_ghx_code or "")
        if _ghx_tokens and get_token_manager().set_credentials_from_oauth(_ghx_tokens[0], _ghx_tokens[1]):
            _ghx_ok = True
            log_activity("OAuth yetkilendirmesi tamamlandı (otomatik)", "ok")
            st.cache_data.clear()
    except Exception:
        _ghx_ok = False
    _qp.clear()
    if _ghx_ok:
        st.rerun()


# ============================================================================
# UI yardımcıları
# ============================================================================
def kpi_card(label: str, value: Any, sub: str = "", color: str = "accent") -> str:
    return f"""
    <div class="cd-kpi" style="--kc: var(--{color});">
      <div class="cd-kpi-label">{label}</div>
      <div class="cd-kpi-value">{value}</div>
      <div class="cd-kpi-sub">{sub}</div>
    </div>"""


def badge(text: str, color: str = "ok", dot: bool = True) -> str:
    color_map = {
        "ok": ("var(--ok)", "var(--ok-soft)"), "warn": ("var(--warn)", "var(--warn-soft)"),
        "err": ("var(--accent)", "var(--soft)"), "info": ("var(--info)", "var(--info-soft)"),
        "muted": ("var(--muted)", "var(--s2)"),
    }
    bc, bsoft = color_map.get(color, color_map["muted"])
    dot_html = '<span class="cd-dot"></span>' if dot else ""
    return (f'<span class="cd-badge" style="--bcolor:{bc}; --bsoft:{bsoft}; --bc:{bc}">'
            f'{dot_html}{text}</span>')


def panel_open(title: str) -> None:
    st.markdown(f'<div class="cd-panel-title">{title}</div>', unsafe_allow_html=True)


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def goto(page: str) -> None:
    """on_click geri çağrısı — widget'a bağlı olmayan düz nav anahtarını günceller."""
    st.session_state["nav"] = page


# ============================================================================
# Ajan Kaydı — youtube-automation-agent mimarisinden
# ============================================================================
AGENTS: List[Dict[str, str]] = [
    {"id": "strategy", "icon": "🧭", "name": "İçerik Stratejisi", "role": "CONTENT-STRATEGY",
     "desc": "Trend analizi, konu keşfi ve içerik takvimi planlaması yapar."},
    {"id": "script", "icon": "📝", "name": "Senaryo Yazarı", "role": "SCRIPT-WRITER",
     "desc": "Konudan bölümlü, anlatı akışı olan yayın senaryoları üretir."},
    {"id": "seo", "icon": "🔍", "name": "SEO Optimize Edici", "role": "SEO-OPTIMIZER",
     "desc": "Başlık, açıklama ve etiketleri arama görünürlüğü için optimize eder."},
    {"id": "thumbnail", "icon": "🖼️", "name": "Kapak Tasarımcısı", "role": "THUMBNAIL-DESIGNER",
     "desc": "Tıklanma oranını artıran kapak görseli konseptleri oluşturur."},
    {"id": "production", "icon": "🎬", "name": "Üretim Yöneticisi", "role": "PRODUCTION-MGMT",
     "desc": "Video üretim hattını yönetir, sağlayıcı seçimi ve render takibi yapar."},
    {"id": "publishing", "icon": "📤", "name": "Yayın Planlayıcı", "role": "PUBLISHING-SCHEDULING",
     "desc": "Yayın takvimini ve zamanlanmış yüklemeleri yönetir."},
    {"id": "analytics", "icon": "📊", "name": "Analitik Optimizasyon", "role": "ANALYTICS-OPTIMIZATION",
     "desc": "Performans verilerini izler, geliştirme önerileri üretir."},
]

PIPELINE_STAGES: List[Dict[str, str]] = [
    {"id": "planlama", "name": "Planlama", "icon": "🧭"},
    {"id": "senaryo", "name": "Senaryo", "icon": "📝"},
    {"id": "uretim", "name": "Üretim", "icon": "🎬"},
    {"id": "inceleme", "name": "İnceleme", "icon": "🔬"},
    {"id": "yayin", "name": "Yayın", "icon": "📤"},
]


def stage_state(stage_index: int, position: int) -> str:
    if stage_index > position:
        return "done"
    if stage_index == position:
        return "active"
    return "pending"


def stage_label(state: str) -> str:
    return {"done": "Tamamlandı", "active": "Sürüyor", "pending": "Bekliyor"}.get(state, state)


def add_project(title: str, topic: str, provider: str, script: str = "") -> Dict[str, Any]:
    project = {
        "id": f"PRJ-{int(time.time())}",
        "title": title,
        "topic": topic,
        "provider": provider,
        "stage_index": 0,
        "script": script,
        "output_path": "",
        "video_id": "",
        "notes": "",
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "updated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    items = load_pipeline()
    items.insert(0, project)
    save_pipeline(items)
    log_activity(f"Yeni proje oluşturuldu: {title}", "ok")
    return project


def advance_project(project_id: str) -> None:
    items = load_pipeline()
    for item in items:
        if item["id"] == project_id and item["stage_index"] < len(PIPELINE_STAGES):
            item["stage_index"] += 1
            item["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            stage_name = PIPELINE_STAGES[min(item["stage_index"], len(PIPELINE_STAGES) - 1)]["name"]
            if item["stage_index"] >= len(PIPELINE_STAGES):
                log_activity(f"Proje tamamlandı ve yayınlandı: {item['title']}", "ok")
            else:
                log_activity(f"Proje ilerledi: {item['title']} → {stage_name}", "info")
            break
    save_pipeline(items)


def delete_project(project_id: str) -> None:
    items = [item for item in load_pipeline() if item["id"] != project_id]
    save_pipeline(items)
    log_activity(f"Proje silindi: {project_id}", "warn")


# ============================================================================
# Servis erişimi
# ============================================================================
@st.cache_resource(show_spinner=False)
def get_config() -> YouTubeConfig:
    return YouTubeConfig()


@st.cache_resource(show_spinner=False)
def get_token_manager() -> TokenManager:
    manager = TokenManager(config=get_config())
    manager.load_credentials()
    return manager


def get_api_client() -> YouTubeAPIClient:
    return YouTubeAPIClient(get_token_manager(), config=get_config())


def get_reporter() -> AnalyticsReporter:
    return AnalyticsReporter(get_token_manager(), config=get_config())


def get_quota_used() -> int:
    try:
        client = get_api_client()
        value = client.quota_used_today
        if callable(value):
            value = value()
        return int(value)
    except Exception:
        return 0


@st.cache_data(ttl=600, show_spinner=False)
def load_channels() -> List[Dict[str, Any]]:
    try:
        return get_api_client().list_accessible_channels()
    except Exception:
        return []


def active_channel() -> Optional[Dict[str, Any]]:
    channels = load_channels()
    if not channels:
        return None
    selected = get_token_manager().get_selected_channel()
    for channel in channels:
        if channel.get("channel_id") == selected:
            return channel
    return channels[0]


# ============================================================================
# ViewMade köprüsü — resmî OAuth + MCP hattı
# ============================================================================
def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def get_viewmade_adapter():
    """Resmî ViewMade adapter'ını proje köküne bağlı olarak döndürür."""
    try:
        from cddocs.config import Project
        from cddocs.viewmade.adapter import ViewMadeAdapter
        return ViewMadeAdapter(Project.open(ROOT))
    except Exception:
        return None


def viewmade_token_info() -> Dict[str, Any]:
    record = _read_json_file(ROOT / "state" / "viewmade-token.json")
    expires_at = record.get("expires_at")
    expiry = None
    days_left = None
    if expires_at:
        try:
            expiry = datetime.fromtimestamp(float(expires_at))
            days_left = max(0, (expiry - datetime.now()).days)
        except (TypeError, ValueError, OSError):
            expiry = None
    return {
        "expires_at": expiry,
        "days_left": days_left,
        "refreshable": bool(record.get("refresh_token")),
        "scope": record.get("scope") or "",
    }


def viewmade_status() -> Dict[str, Any]:
    adapter = get_viewmade_adapter()
    if adapter is None:
        return {"available": False, "authenticated": False, "bound": False,
                "error": "ViewMade modülü yüklenemedi."}
    try:
        status = adapter.status()
    except Exception as exc:
        return {"available": False, "authenticated": False, "bound": False,
                "error": str(exc)[:300]}
    status.update(viewmade_token_info())
    status["available"] = bool(status.get("authenticated") and status.get("bound"))
    return status


@st.cache_data(ttl=180, show_spinner=False)
def list_viewmade_videos() -> Dict[str, Any]:
    """ViewMade hesabındaki üretimleri salt-okuma ile listeler."""
    adapter = get_viewmade_adapter()
    if adapter is None:
        return {"ok": False, "error": "ViewMade adapter yüklenemedi.", "items": []}
    try:
        from cddocs.viewmade.adapter import _tool_payload
        payload = _tool_payload(adapter._call_bound("list_videos", {}))
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return {"ok": False, "error": "ViewMade video listesi okunamadı.", "items": []}
        clean = [item for item in items if isinstance(item, dict)]
        clean.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"ok": True, "items": clean, "error": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400], "items": []}


def find_local_viewmade_video(video_id: str) -> Optional[Path]:
    candidate = ROOT / "renders" / f"viewmade-{video_id}.mp4"
    if candidate.is_file() and candidate.stat().st_size > 100_000:
        return candidate
    packages = ROOT / "content" / "packages"
    if packages.is_dir():
        for request_path in packages.glob("*/viewmade-request.json"):
            request = _read_json_file(request_path)
            if str(request.get("job_id") or "") != video_id:
                continue
            render_path = request.get("render_path")
            if not render_path:
                continue
            local = ROOT / str(render_path)
            if local.is_file():
                return local
    return None


def download_viewmade_preview(video_id: str) -> Dict[str, Any]:
    """ViewMade hazır videosunu indirir, 1080x1920'ye normalize eder ve önizler."""
    adapter = get_viewmade_adapter()
    if adapter is None:
        raise RuntimeError("ViewMade adapter yüklenemedi.")
    from cddocs.viewmade.adapter import _tool_payload

    payload = _tool_payload(adapter._call_bound("download", {"job_id": video_id}))
    if not isinstance(payload, dict):
        raise RuntimeError("ViewMade indirme yanıtı okunamadı.")

    target = ROOT / "renders" / f"viewmade-{video_id}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = False
    if not (target.is_file() and target.stat().st_size > 100_000):
        url = payload.get("video_url") or payload.get("download_url") or payload.get("url")
        file_path = payload.get("path") or payload.get("file") or payload.get("file_path")
        if url:
            adapter._download_url(str(url), target)
        elif file_path and Path(str(file_path)).is_file():
            import shutil
            shutil.copyfile(str(file_path), str(target))
        else:
            raise RuntimeError("ViewMade indirme aracı geçerli bir video adresi döndürmedi.")
        try:
            normalized = bool(adapter._normalize_render(target))
        except Exception:
            normalized = False

    from cddocs.media_probe import validate_file
    info, issues = validate_file(str(target), expect_format="mp4", min_bytes=100_000)
    meta = {
        key: payload.get(key)
        for key in ("id", "title", "description", "tags", "duration", "resolution",
                    "aspect", "scene_count", "sources", "attributions", "view_url",
                    "credits_charged", "net_credits", "created_at", "status",
                    "subject_note")
    }
    meta["job_id"] = payload.get("id") or video_id
    meta.update({
        "local_path": str(target.relative_to(ROOT)).replace("\\", "/"),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        "normalized": normalized,
        "media": info.to_dict() if info else None,
        "issues": issues,
    })
    target.with_suffix(".json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"path": target, "metadata": meta, "issues": issues, "normalized": normalized}


@st.cache_data(ttl=3600, show_spinner=False)
def probe_video(path_text: str, modified: float) -> Dict[str, Any]:
    try:
        from cddocs.media_probe import validate_file
        info, issues = validate_file(path_text, expect_format="mp4", min_bytes=100_000)
        payload = info.to_dict() if info else {}
        payload["issues"] = issues
        return payload
    except Exception:
        return {}


def extract_script_field(script: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}\s*:\s*(.+)$", script or "",
                      flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def default_viewmade_narration(project: Dict[str, Any]) -> str:
    script = str(project.get("script") or "")
    lines: List[str] = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        match = re.match(r"^\[[^\]]+\]\s*(.+)$", line)
        if not match:
            continue
        text = match.group(1).strip()
        text = re.sub(
            r"^(Kanca|Bilim|Detay|Şaşırtıcı gerçek|Kapanış)\s*:\s*", "", text,
            flags=re.IGNORECASE)
        if text:
            lines.append(text)
    if not lines:
        lines = [str(project.get("topic") or project.get("title") or "").strip()]
    return " ".join(part for part in lines if part).strip()


def narration_looks_turkish(text: str) -> bool:
    lowered = str(text or "").lower()
    if re.search(r"[çğıöşü]", lowered):
        return True
    words = set(re.findall(r"[a-z]+", lowered))
    return len(words & {"kedi", "köpek", "neden", "için", "bir", "ve", "bu", "ile"}) >= 2


def _split_narration(narration: str, parts: int = 5) -> List[str]:
    words = str(narration or "").split()
    if not words:
        return [""] * parts
    size = max(1, (len(words) + parts - 1) // parts)
    chunks = [" ".join(words[index:index + size]) for index in range(0, len(words), size)]
    while len(chunks) < parts:
        chunks.append(chunks[-1] if chunks else "")
    return chunks[:parts]


def prepare_viewmade_package(project: Dict[str, Any], narration: str,
                             duration_s: int = 45) -> Dict[str, Any]:
    """Panel projesinden dürüst bir ViewMade istek paketi üretir (render göndermez)."""
    narration = " ".join(str(narration or "").split())
    if not narration:
        raise ValueError("ViewMade anlatım metni boş olamaz.")
    script = str(project.get("script") or "")
    title = extract_script_field(script, "Video başlığı (EN)") or str(
        project.get("title") or "Untitled documentary short")
    tags_text = extract_script_field(script, "Etiketler")
    tags = [part.strip() for part in tags_text.split(",") if part.strip()] or \
        ["cats", "dogs", "documentary"]
    duration_s = max(30, min(60, int(duration_s or 45)))

    digest = hashlib.sha256(f"{title}|{narration}|{duration_s}".encode("utf-8")).hexdigest()[:8]
    project_key = re.sub(r"[^a-z0-9]+", "-", str(project.get("id") or "project").lower()).strip("-")
    slug = f"panel-{project_key}-{digest}"

    folder = ROOT / "content" / "packages" / slug
    folder.mkdir(parents=True, exist_ok=True)
    request_path = folder / "viewmade-request.json"
    existing = _read_json_file(request_path)
    if existing.get("status") in {"SUBMITTED", "RENDERING", "COMPLETE", "STALE"}:
        return {"slug": slug, "path": request_path, "request": existing, "reused": True}

    disclosure = "Real-footage montage using third-party clips for illustration; not documentary footage or scientific evidence."
    config = _read_json_file(ROOT / "config" / "viewmade.json")
    disclosure = str((config.get("render") or {}).get("disclosure") or disclosure)

    chunks = _split_narration(narration, 5)
    scene_duration = round(duration_s / 5, 2)
    scenes = []
    cursor = 0.0
    for index, chunk in enumerate(chunks):
        scenes.append({
            "id": f"s{index + 1}",
            "start_s": round(cursor, 2),
            "duration_s": scene_duration,
            "narration": chunk,
            "visual": {
                "description": "Observational real pet footage illustrating the narration; natural light; calm behavior.",
                "shot_type": "real footage montage",
                "subject": "cats and dogs matching the narration",
                "motion": "gentle documentary pacing",
                "framing": "vertical 9:16, subject centered",
                "continuity": "species-correct animals; no staged distress",
                "avoid": ["text overlays", "watermarks", "distorted animals"],
            },
            "transition": "cut",
        })
        cursor += scene_duration

    now = datetime.now().isoformat(timespec="seconds")
    request_payload = {
        "schema_version": 1,
        "package_id": slug,
        "provider": "viewmade",
        "provider_endpoint": "https://mcp.viewmade.com/mcp",
        "status": "NOT_SUBMITTED",
        "submission_allowed": True,
        "blocked_reason": None,
        "panel_project_id": project.get("id"),
        "panel_project_title": project.get("title"),
        "created_at": now,
        "updated_at": now,
        "preflight": {
            "tool_bindings_complete": True,
            "authentication": "checked_at_render_time",
            "live_authorisation": "required_at_render_time",
        },
        "request": {
            "title": title,
            "provider_topic": title,
            "format": "youtube_shorts",
            "duration_s": duration_s,
            "aspect_ratio": "9:16",
            "resolution": "1080x1920",
            "language": "en",
            "narration": narration,
            "scenes": scenes,
            "captions": {"language": "en", "burned_in": True},
            "disclosure": disclosure,
            "tags": tags,
        },
    }
    request_path.write_text(json.dumps(request_payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    (folder / "script.md").write_text(
        f"# {title}\n\n{narration}\n", encoding="utf-8")
    return {"slug": slug, "path": request_path, "request": request_payload, "reused": False}


def start_viewmade_render(slug: str) -> int:
    """Ücretli ViewMade render işini arka planda başlatır."""
    request_path = ROOT / "content" / "packages" / slug / "viewmade-request.json"
    request = _read_json_file(request_path)
    if not request:
        raise ValueError("ViewMade istek dosyası bulunamadı.")
    if request.get("status") in {"SUBMITTED", "RENDERING", "COMPLETE", "STALE"}:
        raise ValueError("Bu paket için zaten aktif veya tamamlanmış bir render var.")

    log_path = ROOT / "state" / f"dashboard-render-{slug}.log"
    state_path = ROOT / "state" / f"dashboard-render-{slug}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "package_id": slug, "phase": "starting", "started_at": datetime.now().isoformat(timespec="seconds")
    }, indent=2), encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["CDDOCS_LIVE_CONFIRM"] = "YES"
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        with open(log_path, "ab") as log_handle:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts" / "dashboard_viewmade_render.py"),
                 slug, "--poll-interval", "10", "--timeout", "3600"],
                cwd=str(ROOT), env=env, stdout=log_handle, stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
    except OSError as exc:
        state_path.write_text(json.dumps({
            "package_id": slug,
            "phase": "failed",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "error": f"Arka plan işlemi başlatılamadı: {exc}",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    time.sleep(1.0)
    if process.poll() is not None:
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-600:].strip()
        except OSError:
            pass
        message = (f"Arka plan işlemi erken sonlandı (kod {process.returncode}). "
                   f"{tail}".strip())
        state_path.write_text(json.dumps({
            "package_id": slug,
            "phase": "failed",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "error": message,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(message)
    return int(process.pid)


def viewmade_render_state(slug: str) -> Dict[str, Any]:
    dashboard_state = _read_json_file(ROOT / "state" / f"dashboard-render-{slug}.json")
    request = _read_json_file(ROOT / "content" / "packages" / slug / "viewmade-request.json")
    job = _read_json_file(ROOT / "state" / "viewmade-jobs" / f"{slug}.json")
    return {
        "phase": dashboard_state.get("phase") or "",
        "pid": dashboard_state.get("pid"),
        "started_at": dashboard_state.get("started_at") or request.get("created_at"),
        "finished_at": dashboard_state.get("finished_at"),
        "request_status": request.get("status") or "NOT_SUBMITTED",
        "provider_state": request.get("provider_state") or job.get("provider_state"),
        "job_id": request.get("job_id") or job.get("job_id"),
        "render_path": request.get("render_path") or job.get("render_path"),
        "error": dashboard_state.get("error") or request.get("error") or job.get("error"),
        "media": job.get("media"),
    }


def sync_viewmade_projects(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tamamlanan ViewMade çıktısını projeye otomatik bağlar."""
    changed = False
    for item in items:
        slug = item.get("viewmade_package")
        if not slug:
            continue
        state = viewmade_render_state(str(slug))
        if state["request_status"] == "COMPLETE" and state.get("render_path"):
            local = ROOT / str(state["render_path"])
            if local.is_file():
                target = str(local.resolve())
                if item.get("output_path") != target or int(item.get("stage_index", 0)) < 3:
                    item["output_path"] = target
                    item["stage_index"] = max(3, int(item.get("stage_index", 0)))
                    item["video_id"] = state.get("job_id") or item.get("video_id", "")
                    item["viewmade_status"] = "COMPLETE"
                    item["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                    changed = True
        elif state["request_status"] in {"SUBMITTED", "RENDERING", "FAILED", "STALE"}:
            if item.get("viewmade_status") != state["request_status"]:
                item["viewmade_status"] = state["request_status"]
                changed = True
    if changed:
        save_pipeline(items)
    return items


def _provider_meta_for_path(path: Path) -> Dict[str, Any]:
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        return _read_json_file(sidecar)
    packages = ROOT / "content" / "packages"
    if packages.is_dir():
        for request_path in packages.glob("*/viewmade-request.json"):
            request = _read_json_file(request_path)
            render_path = str(request.get("render_path") or "")
            if not render_path:
                continue
            if (ROOT / render_path).resolve() == path.resolve() or \
                    Path(render_path).stem == path.stem or \
                    str(request.get("package_id") or "") == path.stem:
                provider = dict(request.get("provider_package") or {})
                provider.setdefault("status", request.get("status"))
                provider.setdefault("job_id", request.get("job_id"))
                return provider
    return {}


def local_video_entries() -> List[Dict[str, Any]]:
    pipeline = load_pipeline()
    entries: List[Dict[str, Any]] = []
    seen = set()
    for folder, source in ((ROOT / "renders", "ViewMade"), (ROOT / "outputs", "Panel")):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.mp4"):
            if any(marker in path.name for marker in (".invalid.", ".raw.", ".normalized.")):
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            provider = _provider_meta_for_path(path)
            project = next(
                (item for item in pipeline
                 if item.get("output_path") and
                 Path(str(item["output_path"])).resolve() == path.resolve()),
                None,
            )
            project_script = str((project or {}).get("script") or "")
            title = (provider.get("title") or
                     extract_script_field(project_script, "Video başlığı (EN)") or
                     (project or {}).get("title") or path.stem.replace("-", " ").title())
            description = provider.get("description") or str(
                (project or {}).get("topic") or "").strip() or title
            tags = provider.get("tags") or []
            if isinstance(tags, str):
                tags = [part.strip() for part in tags.split(",") if part.strip()]
            if not tags:
                tags_text = extract_script_field(project_script, "Etiketler")
                tags = [part.strip() for part in tags_text.split(",") if part.strip()]
            probe = probe_video(str(path), path.stat().st_mtime)
            entries.append({
                "path": path,
                "name": path.name,
                "source": source,
                "title": title,
                "description": description,
                "tags": list(tags)[:15],
                "sources": provider.get("sources") or [],
                "attributions": provider.get("attributions") or [],
                "subject_note": provider.get("subject_note") or "",
                "provider_status": provider.get("status") or "",
                "view_url": provider.get("view_url") or "",
                "project": project,
                "size_mb": path.stat().st_size / 1_048_576,
                "modified": path.stat().st_mtime,
                "probe": probe,
            })
    entries.sort(key=lambda entry: entry["modified"], reverse=True)
    return entries


def publish_description(entry: Dict[str, Any]) -> str:
    parts = [str(entry.get("description") or "").strip()]
    attributions = entry.get("attributions") or []
    if attributions:
        parts.append("Kaynaklar / Atıf:\n" + "\n".join(f"• {line}" for line in attributions))
    if entry.get("source") == "ViewMade":
        config = _read_json_file(ROOT / "config" / "viewmade.json")
        disclosure = str((config.get("render") or {}).get("disclosure") or "").strip()
        if disclosure:
            parts.append(disclosure)
    return "\n\n".join(part for part in parts if part)[:5000]


def get_upload_manager() -> UploadManager:
    return UploadManager(get_token_manager(), config=get_config(),
                         history_file=str(ROOT / "upload_history.json"))


def upload_history_entries(limit: int = 5) -> List[Dict[str, Any]]:
    history = _read_json_file(ROOT / "upload_history.json")
    rows = []
    for record in history.values():
        if isinstance(record, dict) and record.get("video_id"):
            rows.append(record)
    rows.sort(key=lambda row: str(row.get("uploaded_at") or ""), reverse=True)
    return rows[:limit]


# ============================================================================
# İçerik sicili — ViewMade ↔ YouTube eşleşmesi ve tekrar üretim engeli
# ============================================================================
REGISTRY_FILE = ROOT / "content_registry.json"

_FOLD_MAP = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
    "'": "", "’": "", "“": "", "”": "", "`": "",
})

_REGISTRY_STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "and", "or", "is", "are", "was", "were",
    "why", "how", "your", "you", "it", "its", "this", "that", "these", "those",
    "be", "been", "being", "do", "does", "did", "can", "cant", "cannot", "with",
    "for", "on", "at", "by", "from", "not", "no", "but", "if", "then", "than",
    "bir", "bu", "su", "ve", "ile", "icin", "neden", "nasil", "daha", "cok",
}


def _fold(text: Any) -> str:
    cleaned = str(text or "").replace(",", "").translate(_FOLD_MAP)
    return " ".join(cleaned.lower().split())


def content_tokens(text: Any) -> List[str]:
    words = re.findall(r"[a-z0-9]+", _fold(text))
    return sorted({word for word in words
                   if len(word) > 2 and word not in _REGISTRY_STOPWORDS})


def registry_similarity(left: List[str], right: List[str]) -> float:
    left_set, right_set = set(left or []), set(right or [])
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / min(len(left_set), len(right_set))


def load_registry() -> List[Dict[str, Any]]:
    data = _read_json_file(REGISTRY_FILE)
    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def save_registry(entries: List[Dict[str, Any]]) -> None:
    REGISTRY_FILE.write_text(
        json.dumps({
            "schema_version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "entries": entries,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def registry_texts(entry: Dict[str, Any]) -> List[str]:
    texts = [str(entry.get("title") or "")]
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        texts.extend(str(alias) for alias in aliases)
    return [text for text in texts if text.strip()]


def registry_find(entries: List[Dict[str, Any]], title: Optional[str] = None,
                  *, viewmade_id: Optional[str] = None,
                  youtube_id: Optional[str] = None,
                  min_score: float = 0.85) -> Optional[Dict[str, Any]]:
    if viewmade_id:
        for entry in entries:
            if str(entry.get("viewmade_id") or "") == str(viewmade_id):
                return entry
    if youtube_id:
        for entry in entries:
            if str(entry.get("youtube_id") or "") == str(youtube_id):
                return entry
    tokens = content_tokens(title or "")
    if not tokens:
        return None
    best, best_score = None, 0.0
    for entry in entries:
        score = registry_similarity(tokens, entry.get("tokens") or [])
        if score > best_score:
            best, best_score = entry, score
    return best if best is not None and best_score >= min_score else None


def registry_merge(entries: List[Dict[str, Any]], title: Any, *, source: str,
                   viewmade_id: Optional[str] = None,
                   youtube_id: Optional[str] = None,
                   package: Optional[str] = None,
                   rejected: bool = False,
                   status: Optional[str] = None) -> bool:
    title = " ".join(str(title or "").split())
    tokens = content_tokens(title)
    if not title or not tokens:
        return False
    now = datetime.now().isoformat(timespec="seconds")
    entry = registry_find(entries, title, viewmade_id=viewmade_id,
                          youtube_id=youtube_id)
    if entry is None:
        entries.append({
            "title": title,
            "aliases": [],
            "tokens": tokens,
            "sources": [source],
            "viewmade_id": viewmade_id,
            "youtube_id": youtube_id,
            "package": package,
            "rejected": bool(rejected),
            "status": status or "",
            "first_seen": now,
            "updated_at": now,
        })
        return True

    changed = False
    folded_title = _fold(title)
    known_folded = {_fold(text) for text in registry_texts(entry)}
    if folded_title and folded_title not in known_folded:
        aliases = entry.setdefault("aliases", [])
        if len(aliases) < 8:
            aliases.append(title)
        changed = True
    merged_tokens = sorted(set(entry.get("tokens") or []) | set(tokens))
    if merged_tokens != (entry.get("tokens") or []):
        entry["tokens"] = merged_tokens
        changed = True
    sources = entry.setdefault("sources", [])
    if source and source not in sources:
        sources.append(source)
        changed = True
    if viewmade_id and str(entry.get("viewmade_id") or "") != str(viewmade_id):
        entry["viewmade_id"] = str(viewmade_id)
        changed = True
    if youtube_id and str(entry.get("youtube_id") or "") != str(youtube_id):
        entry["youtube_id"] = str(youtube_id)
        changed = True
    if package and str(entry.get("package") or "") != str(package):
        entry["package"] = str(package)
        changed = True
    if rejected and not entry.get("rejected"):
        entry["rejected"] = True
        changed = True
    if status and str(entry.get("status") or "") != str(status):
        entry["status"] = str(status)
        changed = True
    if changed:
        entry["updated_at"] = now
    return changed


def registry_state(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "new"
    if entry.get("youtube_id"):
        return "published"
    if entry.get("rejected"):
        return "rejected"
    status = str(entry.get("status") or "").lower()
    if entry.get("viewmade_id") and status in {
            "", "ready", "complete", "completed", "rendering", "submitted"}:
        return "produced"
    if status in {"submitted", "rendering", "complete", "completed"}:
        return "produced"
    if entry.get("package"):
        return "planned"
    return "known"


@st.cache_data(ttl=600, show_spinner=False)
def channel_videos_index() -> List[Dict[str, str]]:
    try:
        reporter = get_reporter()
        rows = reporter.get_recent_videos(max_results=50)
    except Exception:
        return []
    clean = []
    for row in rows:
        if isinstance(row, dict) and row.get("title") and row.get("video_id"):
            clean.append({
                "video_id": str(row["video_id"]),
                "title": str(row["title"]),
                "published_at": str(row.get("published_at") or ""),
            })
    return clean


def sync_content_registry() -> List[Dict[str, Any]]:
    """YouTube kanalı, ViewMade üretimleri ve yerel paketleri tek sicilde eşler."""
    entries = load_registry()
    changed = False
    for video in channel_videos_index():
        changed |= registry_merge(entries, video["title"], source="youtube",
                                  youtube_id=video["video_id"], status="youtube")
    vm_list = list_viewmade_videos()
    if vm_list.get("ok"):
        for item in vm_list.get("items", []):
            changed |= registry_merge(
                entries, item.get("title"), source="viewmade",
                viewmade_id=str(item.get("id") or "") or None,
                status=str(item.get("status") or ""),
            )
    packages_dir = ROOT / "content" / "packages"
    if packages_dir.is_dir():
        for request_path in packages_dir.glob("*/viewmade-request.json"):
            request = _read_json_file(request_path)
            body = request.get("request") if isinstance(request.get("request"), dict) else {}
            title = str(body.get("title") or "").strip()
            if not title:
                continue
            package_status = str(request.get("status") or "")
            provider_package = request.get("provider_package")
            rejected = (package_status in {"REJECTED", "STALE"} or
                        bool(isinstance(provider_package, dict)
                             and provider_package.get("rejected")))
            changed |= registry_merge(
                entries, title, source="package",
                package=str(request.get("package_id") or request_path.parent.name),
                viewmade_id=str(request.get("job_id") or "") or None,
                rejected=rejected,
                status=package_status.lower() if package_status else None,
            )
    if changed:
        save_registry(entries)
    return entries


def _idea_matches_text(idea: Dict[str, str], text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    for keyword in idea.get("kw", []):
        if keyword and _fold(keyword) in folded:
            return True
    return registry_similarity(content_tokens(idea.get("t") or ""),
                               content_tokens(text)) >= 0.85


def registry_status_for_idea(idea: Dict[str, str], entries: List[Dict[str, Any]],
                             pipeline_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    soft_match: Optional[Dict[str, Any]] = None
    for entry in entries:
        if not any(_idea_matches_text(idea, text) for text in registry_texts(entry)):
            continue
        state = registry_state(entry)
        if state == "published":
            return {"state": "published", "entry": entry}
        if state == "produced":
            return {"state": "produced", "entry": entry}
        if state in {"rejected", "planned"} and soft_match is None:
            soft_match = {"state": state, "entry": entry}
    for item in pipeline_items:
        script = str(item.get("script") or "")
        english_title = extract_script_field(script, "Video başlığı (EN)")
        if (_idea_matches_text(idea, str(item.get("title") or "")) or
                _idea_matches_text(idea, english_title)):
            return {"state": "pipeline", "title": str(item.get("title") or "")}
    return soft_match


def choose_proposal(cursor: int, entries: List[Dict[str, Any]],
                    pipeline_items: List[Dict[str, Any]]) -> tuple:
    """Havuzdan yayında/üretimde olmayan ilk konuyu seçer."""
    total = len(NICHE_IDEAS)
    for offset in range(total):
        index = (cursor + offset) % total
        idea = NICHE_IDEAS[index]
        status = registry_status_for_idea(idea, entries, pipeline_items)
        if status is None or status.get("state") in {"rejected", "planned"}:
            proposal = build_proposal(index)
            proposal["registry"] = status
            return proposal, index + 1
    return None, cursor


def registry_title_for_item(item: Dict[str, Any]) -> str:
    script = str(item.get("script") or "")
    return (extract_script_field(script, "Video başlığı (EN)") or
            str(item.get("title") or "")).strip()


# ============================================================================
# Sol Panel
# ============================================================================
with st.sidebar:
    st.markdown(
        f"""
        <div class="cd-brand">
          <div class="cd-brand-mark">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M9 7.5v9l7.5-4.5z" fill="white"/>
            </svg>
          </div>
          <div>
            <div class="cd-brand-name">Otomasyon Stüdyosu</div>
            <div class="cd-brand-sub">Cats & Dogs Documentary</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_pages = ["🎛️ Genel Bakış", "🎬 Video Üretim", "🤖 Ajanlar",
                 "📈 İstatistikler", "⚙️ Otomasyon", "🔧 Ayarlar"]
    current_page = st.session_state.get("nav", nav_pages[0])
    for nav_index, nav_page in enumerate(nav_pages):
        st.button(
            nav_page,
            key=f"nav_{nav_index}",
            use_container_width=True,
            type="primary" if nav_page == current_page else "secondary",
            on_click=goto,
            args=(nav_page,),
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Tema seçimi
    theme_keys = list(THEMES.keys())
    theme_labels = [THEMES[key]["label"] for key in theme_keys]
    current_theme = SETTINGS.get("theme", "standart")
    if current_theme not in theme_keys:
        current_theme = "standart"
    chosen_theme = st.selectbox(
        "Tema",
        options=theme_keys,
        index=theme_keys.index(current_theme),
        format_func=lambda key: THEMES[key]["label"],
        key="theme_select",
    )
    if chosen_theme != current_theme:
        SETTINGS["theme"] = chosen_theme
        save_settings(SETTINGS)
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Bağlantı & Yetkilendirme — her koşulda görünür
    manager = get_token_manager()
    try:
        if not manager.is_valid():
            manager.ensure_valid()
    except Exception:
        pass
    token_ok = manager.is_valid()
    with st.expander("🔗 Bağlantı", expanded=not token_ok):
        if token_ok:
            st.markdown(badge("Sistem Çevrimiçi", "ok"), unsafe_allow_html=True)
        else:
            st.markdown(badge("Bağlantı Gerekli", "err"), unsafe_allow_html=True)
        st.caption("Butona basın → Google sayfasında izin verin → panel kendiliğinden tamamlar. "
                   "Otomatik dönüş olmazsa yönlendirme adresindeki kodu aşağıya yapıştırıp "
                   "'Kodla Tamamla'ya basın.")
        try:
            oauth_manager = OAuthFlowManager(get_config())
            auth_url = oauth_manager.get_authorization_url()
        except Exception as exc:
            oauth_manager = None
            auth_url = ""
            st.error(f"Bağlantı oluşturulamadı: {str(exc)[:140]}")
        if auth_url:
            st.link_button("🔑 Google'da Yetkilendir", auth_url,
                           use_container_width=True, type="primary")
        pasted = st.text_input("Geri dönen kod / adres", key="oauth_paste",
                               placeholder="örn: http://localhost:8502/?code=4/0A…")
        if st.button("✅ Kodla Tamamla", use_container_width=True):
            if oauth_manager is None:
                st.error("Önce bağlantı hatasını çözün.")
            elif not pasted.strip():
                st.warning("Kodu/adresi önce yapıştırın.")
            else:
                try:
                    tokens = oauth_manager.exchange_code(pasted)
                    if tokens and manager.set_credentials_from_oauth(tokens[0], tokens[1]):
                        log_activity("OAuth yetkilendirmesi tamamlandı (manuel)", "ok")
                        st.cache_data.clear()
                        st.rerun()
                    st.error("Token kaydedilemedi.")
                except Exception as exc:
                    st.error(f"Tamamlanamadı: {str(exc)[:160]}")

    # Kanal seçimi
    channels = load_channels()
    if channels:
        labels = [
            f"{ch.get('title', 'Kanal')} · {fmt_int(ch.get('subscriber_count', 0))} abone"
            for ch in channels
        ]
        selected = manager.get_selected_channel()
        default_index = 0
        for index, channel in enumerate(channels):
            if channel.get("channel_id") == selected:
                default_index = index
                break
        picked = st.selectbox("Kanal", options=list(range(len(channels))),
                              index=default_index, format_func=lambda i: labels[i],
                              key="channel_pick")
        if channels[picked].get("channel_id") != selected:
            manager.set_selected_channel(channels[picked].get("channel_id"))
            st.cache_data.clear()
            st.rerun()
    elif token_ok:
        st.caption("Kanallar yüklenemedi — sayfayı yenileyin.")

    # Kota
    quota_limit = 10000
    try:
        quota_limit = int(getattr(get_config(), "daily_quota_limit", 10000) or 10000)
    except Exception:
        pass
    quota_used = get_quota_used()
    pct = min(100, int(quota_used / quota_limit * 100)) if quota_limit else 0
    st.markdown(f"""
        <div style="margin-top:14px">
          <div style="display:flex; justify-content:space-between; font-family:var(--mono);
               font-size:.68rem; color:var(--muted); letter-spacing:.08em; margin-bottom:5px">
            <span>API KOTASI</span><span>{quota_used} / {quota_limit}</span>
          </div>
          <div style="height:5px; background:var(--s3); border-radius:4px; overflow:hidden">
            <div style="height:100%; width:{pct}%; background:{'var(--warn)' if pct > 80 else 'var(--accent)'}"></div>
          </div>
        </div>
    """, unsafe_allow_html=True)

    st.caption(f"v2.2 · {datetime.now().strftime('%d.%m.%Y')}")


def render_overview() -> None:
    channel = active_channel()
    pipeline = load_pipeline()
    activity: List[Dict[str, Any]] = []
    if ACTIVITY_FILE.exists():
        try:
            activity = json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            activity = []
    agents_on = sum(1 for agent in AGENTS if SETTINGS.get("agents_enabled", {}).get(agent["id"], True))

    # Hero
    channel_name = channel.get("title", "Kanal") if channel else "Bağlantı Bekleniyor"
    st.markdown(
        f"""
        <div class="cd-hero">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px">
            <div>
              <h1>Genel Bakış</h1>
              <p>{channel_name} · {datetime.now().strftime('%d %B %Y, %A')}</p>
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end">
              {badge(f"{agents_on}/{len(AGENTS)} Ajan Aktif", "info") if agents_on else badge("0 Ajan Aktif", "warn")}
              {badge("Sistem Çevrimiçi", "ok") if get_token_manager().is_valid() else badge("Bağlantı Gerekli", "err")}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPI satırı
    if channel:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card("ABONE", fmt_int(channel.get("subscriber_count", 0)),
                                 "Toplam abone sayısı", "accent"), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("GÖRÜNTÜLENME", fmt_int(channel.get("view_count", 0)),
                                 "Kanal toplamı", "info"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("VİDEO", fmt_int(channel.get("video_count", 0)),
                                 "Yayında", "ok"), unsafe_allow_html=True)
        with c4:
            pending_count = sum(1 for item in pipeline if item["stage_index"] < len(PIPELINE_STAGES))
            st.markdown(kpi_card("HATTA PROJE", str(pending_count),
                                 f"{len(pipeline)} proje toplam", "purple"), unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="cd-panel"><div class="cd-panel-title">BAĞLANTI KURULUMU</div>'
            '<p style="color:var(--t2)">Kanal verilerini görmek için sol panelden <b>🔑 Yetkilendir (OAuth)</b> '
            'adımını tamamlayın. Yetkilendirme sonrası bu sayfa otomatik dolar.</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Üretim hattı özeti
    left, right = st.columns([2, 1])
    with left:
        panel_open("ÜRETİM HATTI DURUMU")
        if pipeline:
            stage_counts = [0] * len(PIPELINE_STAGES)
            for item in pipeline:
                index = min(item["stage_index"], len(PIPELINE_STAGES) - 1)
                stage_counts[index] += 1
            cols = st.columns(len(PIPELINE_STAGES))
            for position, stage in enumerate(PIPELINE_STAGES):
                with cols[position]:
                    cls = "cd-stage cd-stage-active" if stage_counts[position] else "cd-stage"
                    st.markdown(
                        f"""<div class="{cls}">
                              <div class="cd-stage-icon">{stage['icon']}</div>
                              <div class="cd-stage-name">{stage['name']}</div>
                              <div class="cd-stage-state">{stage_counts[position]} proje</div>
                            </div>""",
                        unsafe_allow_html=True,
                    )
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            rows = []
            for item in pipeline[:6]:
                stage_name = PIPELINE_STAGES[min(item["stage_index"], len(PIPELINE_STAGES) - 1)]["name"]
                rows.append({"Proje": item["title"], "Aşama": stage_name,
                             "Sağlayıcı": item.get("provider", "—"), "Güncelleme": item.get("updated_at", "")})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.markdown('<div class="cd-panel" style="color:var(--muted)">Hatta proje yok. '
                        '<b>🎬 Video Üretim</b> sayfasından ilk projeyi oluşturun.</div>',
                        unsafe_allow_html=True)
    with right:
        panel_open("HIZLI İŞLEMLER")
        if st.button("🎬 Video Üretim'e Git", use_container_width=True, type="primary"):
            st.session_state["nav"] = "🎬 Video Üretim"
            st.rerun()
        if st.button("📈 İstatistikleri Aç", use_container_width=True):
            st.session_state["nav"] = "📈 İstatistikler"
            st.rerun()
        if st.button("⚙️ Otomasyonu Aç", use_container_width=True):
            st.session_state["nav"] = "⚙️ Otomasyon"
            st.rerun()

        panel_open("SON HAREKETLER")
        if activity:
            for entry in activity[:8]:
                kind = "ok" if entry.get("kind") == "ok" else ("err" if entry.get("kind") == "hata" else "")
                cls = f"cd-log cd-log-{kind}" if kind else "cd-log"
                st.markdown(
                    f'<div class="{cls}"><span class="cd-log-ts">{entry.get("ts", "")}</span>'
                    f'{entry.get("msg", "")}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Henüz kayıt yok.")


# ============================================================================
# İçerik Ajanı — niş odaklı proje önerileri (kedi–köpek belgeselciği)
# ============================================================================
NICHE_IDEAS: List[Dict[str, str]] = [
    {"s": "Kedilerin gece görüşü", "t": "Why Cats Glow in the Dark (It's Not Magic)",
     "h": "Karanlıkta kedinizin gözleri neden ışık saçar? Cevap büyü değil, özel bir doku.",
     "f": "Kedilerin gözünün arkasındaki tapetum lucidum tabakası, gelen ışığı ağtabakaya geri yansıtır; bu sayede ışığı yaklaşık 6 kat daha verimli kullanırlar.",
     "b1": "Bu tabaka mavi-yeşil parlıyor görünür; yansıyan ışığın dalga boyu göz yapısına bağlıdır.",
     "b2": "Kediler tam karanlıkta değil, düşük ışıkta üstündür; insanın algıladığından çok daha az ışıkla yön bulabilirler.",
     "tags": "kedi gece görüşü, tapetum lucidum, kedi gözleri neden parlar",
     "th": "Siyah zeminde parlayan kedi gözü, tek nokta mavi ışık."},
    {"s": "Köpeklerin koku dünyası", "t": "A Dog's Nose Knows More Than You Think",
     "h": "İnsan burnu milyonlarca koku alıcısı taşır; köpeğinki kat kat fazlası. Peki bu ne demek?",
     "f": "Köpeklerin koku alma epiteli insanınkinden çok daha geniştir; burun yapısı soluk alırken ayrı, verirken ayrı hava yolu kullanır.",
     "b1": "Köpekler iki burun deliğini bağımsız kullanır; bu, kokunun yönünü belirlemesini sağlar.",
     "b2": "Eğitimli köpekler bazı hastalıkları kokudan ayırt edebilir; bu alandaki çalışmalar hâlâ sürüyor.",
     "tags": "köpek koku alma, köpek burnu, koku duyusu",
     "th": "Köpek burnu yakın plan, arka planda bulanık orman."},
    {"s": "Kediler neden kutuya girer", "t": "Why Cats Can't Resist a Box",
     "h": "Kutu, kedi için oyuncak değil; güvenlik, sıcaklık ve keşif dengesi.",
     "f": "Kapalı alanlar kedilere saklanma ve gözlem noktası sağlar; kutulu ortamda stres davranışlarının azaldığını gösteren çalışmalar var.",
     "b1": "Kutular aynı zamanda ısı yalıtımı sağlar; kedilerin konfor sıcaklığı insandan yüksektir.",
     "b2": "Yeni ortama alışan kedilerde kutu, uyum süresini kısaltabilir.",
     "tags": "kedi kutu, kedi davranışı, kedi psikolojisi",
     "th": "Karton kutudan bakan kedi, yumuşak ışık."},
    {"s": "Köpeklerin suçluluk bakışı", "t": "That Guilty Look Is a Myth",
     "h": "Köpeğiniz sizi 'suçlu' bakışla karşılıyor — ama o bakış gerçekten suçluluk mu?",
     "f": "Yapılan çalışmalar, sahiplerin suçlu bulduğu ifadenin köpeğin gerçekten bir şey yapıp yapmadığını değil, sahibinin tepkisini yansıttığını gösterdi.",
     "b1": "Köpekler insan yüz ifadelerini ve ses tonunu çok iyi okur; 'suçlu bakış' bir uyum davranışı olabilir.",
     "b2": "Disiplin yerine yönlendirme, istenmeyen davranışlarda daha etkili sonuç verir.",
     "tags": "köpek suçluluk bakışı, köpek davranışı, köpek eğitimi",
     "th": "Kanepe kenarında köpek ve sahibi, sıcak-soğuk ton karşıtlığı."},
    {"s": "Kedilerin mırlaması", "t": "The Secret Frequency of a Purr",
     "h": "Mırlama sadece mutluluk değil; düşük frekanslı bir iletişim aracı.",
     "f": "Kediler mırlamayı hem rahatlarken hem de stres veya ağrı anlarında kullanır; düşük frekanslı titreşimlerin etkisi araştırılmaya devam ediyor.",
     "b1": "Yavru kediler annelerine yakınlık kurmak için mırlar; bu davranış yetişkinlikte de kalır.",
     "b2": "Bazı mırlamalar 'talep' tonu taşır; insan bebeği ağlamasına benzeyen frekanslar içerebilir.",
     "tags": "kedi mırlaması, kedi sesleri, mırlama frekansı",
     "th": "Yakın plan kedi, göğsünde hafif ışık titreşimi."},
    {"s": "Köpeklerin kuyruk dili", "t": "Your Dog's Tail Is Talking",
     "h": "Kuyruk sallama her zaman mutluluk değil — yönü bile anlam taşıyor.",
     "f": "Araştırmalar köpeklerin sağa sallamayı olumlu, sola sallamayı daha temkinli durumlarla ilişkilendirdiğini gösteriyor.",
     "b1": "Kuyruk yüksekliği duygu durumunu ele verir: dik kuyruk uyarılmışlık, düşük kuyruk çekingenlik.",
     "b2": "Sert ve kısa hareketler oyun değil, gerginlik işareti olabilir.",
     "tags": "köpek kuyruk dili, köpek davranışı, kuyruk sallama",
     "th": "Köpek silüeti, kuyruk hareketi izi, koyu arka plan."},
    {"s": "Dokuz can miti", "t": "Do Cats Really Have Nine Lives?",
     "h": "Kedilerin dokuz canı olduğu söylenir; gerçek ise çok daha ilginç.",
     "f": "Kedilerin düşerken vücutlarını düzeltme refleksi güçlüdür, ancak bu onları her düşüşten korumaz; yükseklik ve zemin kritiktir.",
     "b1": "Refleks yaklaşık 3-4 haftalıkken gelişir; bu yüzden yavru kediler daha kırılgandır.",
     "b2": "Veterinerler yüksekten düşmelerde benzer yaralanmaları sık görür — mit, güvenlik riskini gizleyebilir.",
     "tags": "kedi dokuz can, kedi düşme refleksi, kedi mitleri",
     "th": "Yüksek kenarda dengede kedi, aşağıda yumuşak gölge."},
    {"s": "Köpeğin evrimi", "t": "From Wolf to Woof: 15,000 Years",
     "h": "Köpek, kurt değil; ama hâlâ kurdun genlerini taşıyor.",
     "f": "Köpeklerin evcilleşmesi en az 15 bin yıl öncesine uzanır; genom çalışmaları evcilleşmenin tek bir bölgede mi yoksa birden çok yerde mi olduğunu tartışıyor.",
     "b1": "Evcilleşmeyle sindirim enzimi genlerinde değişimler görüldü; köpekler nişastalı beslenmeye daha uyumlu hale geldi.",
     "b2": "Modern ırkların çoğu son 200 yılda seçilimle şekillendi — köpek tarihi ırk listesinden çok daha eski.",
     "tags": "köpek evrimi, kurt köpek, köpek tarihi",
     "th": "Kurt silüetinden köpek silüetine geçiş, zaman çizgisi."},
    {"s": "Kediler kendini evcilleştirdi", "t": "Cats Domesticated Themselves",
     "h": "Kediyi biz evcilleştirmedik; o bizi seçmiş olabilir.",
     "f": "Tarım yerleşimlerinde tahıl depolarına gelen kemiriciler kedileri çekti; bu karşılıklı yarar, kedilerin insan yaşamına yaklaşmasını sağladı.",
     "b1": "Kedi genomunda evcilleşme izleri köpeğe göre daha hafif; kedi davranışları yabani atalarına daha yakın.",
     "b2": "Antik Mısır'dan gemi yolculuklarına kadar kediler ticaret rotalarıyla dünyaya yayıldı.",
     "tags": "kedi evcilleşmesi, kedi tarihi, kedi genomu",
     "th": "Tahıl ambarı önünde oturan kedi, sıcak toprak tonları."},
    {"s": "Hayvanlar rüya görür mü", "t": "Do Dogs Dream of Electric Sheep?",
     "h": "Köpeğiniz uykuda koşuyorsa, muhtemelen rüya görüyor.",
     "f": "Kedi ve köpeklerde REM uykusu gözlemlenir; bu evre insanlarda rüyayla ilişkilidir ve hayvanlarda da benzer beyin aktivitesi görülür.",
     "b1": "Yavru köpekler ve yavru kediler yetişkinlere göre daha fazla REM uykusu uyur.",
     "b2": "Uykuda seğirme ve ses çıkarma normaldir; sık uyanma veya huzursuzluk veteriner kontrolü gerektirebilir.",
     "tags": "köpek rüyası, kedi rüyası, REM uykusu hayvanlar",
     "th": "Uyuyan köpek, başında rüya bulutu, gece mavisi."},
    {"s": "Köpeklerin zaman algısı", "t": "How Dogs Tell Time Without a Clock",
     "h": "Köpeğiniz eve dönüş saatinizi nasıl biliyor?",
     "f": "Köpekler zamanı kokudaki değişim ve günlük rutinlerin ritmiyle takip ediyor olabilir; mutlak saat yerine olay sırasına duyarlıdırlar.",
     "b1": "Sahibinin kokusunun evde zayıflaması, dönüş yaklaştıkça artması köpeğe ipucu verir.",
     "b2": "Rutin beslenme ve yürüyüş saatleri köpeklerde güçlü bir iç saat oluşturur.",
     "tags": "köpek zaman algısı, köpek rutini, köpek davranışı",
     "th": "Kapı önünde bekleyen köpek, arkada saat gölgesi."},
    {"s": "Kedilerin sessiz dili", "t": "The Silent Language of Cats",
     "h": "Kediniz ses çıkarmadan da konuşuyor — kuyruk, kulak ve bıyık dili.",
     "f": "Kedi vücut dili; kuyruk pozisyonu, kulak açısı ve bıyık yönüyle okunur. Yavaş göz kırpma, güven işareti olarak yorumlanır.",
     "b1": "Kulaklar yana yatıyorsa stres veya rahatsızlık; dik ve öne dönükse merak işareti olabilir.",
     "b2": "Yavaş göz kırpmaya karşılık vermek, kediyle bağ kurmanın en basit yollarından biri.",
     "tags": "kedi vücut dili, kedi işaretleri, yavaş göz kırpma",
     "th": "Kedi yüzü yakın plan, gözler yarı kapalı, sıcak ışık."},
    {"s": "Köpekler renk görür mü", "t": "Dogs Are Colorblind (Sort of)",
     "h": "Köpeğiniz dünyayı siyah-beyaz görmüyor; ama sizin gördüğünüz renkleri de görmüyor.",
     "f": "Köpekler dichromat görüşe sahiptir: mavi ve sarı tonlarını ayırt eder, kırmızı-yeşil ayrımında insandan zayıftır.",
     "b1": "Köpekler için kırmızı oyuncak, çimende düşük kontrast oluşturabilir; mavi-sarı oyuncaklar daha görünür.",
     "b2": "Hareket algısı ve koku, köpeğin dünyayı okuma biçiminde renkten daha baskın.",
     "tags": "köpek renk görüşü, köpek görme, dichromat",
     "th": "Yarısı mavi-sarı, yarısı kırmızı-yeşil bölünmüş köpek portresi."},
    {"s": "Kedilerin yüz sesi", "t": "Cats Have 100 Words for You",
     "h": "Miyav, mırlama, cıvıldama… Kedilerin insana özel bir ses repertuvarı var.",
     "f": "Kediler yetişkinler arasında nadiren miyavlar; miyav çoğunlukla insana yönelik bir iletişim aracıdır ve kediye özgü bir 'insan dili' olarak gelişmiştir.",
     "b1": "Kediler farklı ihtiyaçlar için farklı miyav tonları kullanır; sahipleri zamanla bunları ayırt eder.",
     "b2": "Bazı kediler açlık, susuzluk ve ilgi talebini neredeyse aynı sesle ifade eder — bağlam belirleyicidir.",
     "tags": "kedi sesleri, kedi miyav, kedi iletişimi",
     "th": "Ses dalgası grafiği üzerinde kedi silüeti, neon vurgu."},
]

# Öneri havuzu ile kanal/ViewMade üretimleri arasındaki eşleşme anahtarları.
# Başlıklar birebir aynı olmasa da konu anahtar kelimeden yakalanır.
NICHE_KEYWORDS: Dict[str, List[str]] = {
    "Kedilerin gece görüşü": ["glow", "dark", "tapetum", "night vision", "gece"],
    "Köpeklerin koku dünyası": ["nose", "smell", "scent", "koku", "burun"],
    "Kediler neden kutuya girer": ["box", "kutu", "karton"],
    "Köpeklerin suçluluk bakışı": ["guilty", "guilt", "sucluluk", "suclu"],
    "Kedilerin mırlaması": ["purr", "mirla"],
    "Köpeklerin kuyruk dili": ["tail", "kuyruk"],
    "Dokuz can miti": ["nine lives", "dokuz can"],
    "Köpeğin evrimi": ["wolf", "woof", "evrim"],
    "Kediler kendini evcilleştirdi": ["domesticat", "evcilles"],
    "Hayvanlar rüya görür mü": ["dream", "ruya", "rem sleep"],
    "Köpeklerin zaman algısı": ["clock", "tell time", "zaman"],
    "Kedilerin sessiz dili": ["silent", "body language", "blink", "sessiz"],
    "Köpekler renk görür mü": ["colorblind", "colour vision", "renk"],
    "Kedilerin yüz sesi": ["meow", "miyav", "100 words", "vocal"],
}

for _idea in NICHE_IDEAS:
    _idea["kw"] = NICHE_KEYWORDS.get(_idea["s"], [])


def build_proposal(cursor: int) -> Dict[str, Any]:
    idea = NICHE_IDEAS[cursor % len(NICHE_IDEAS)]
    scenes = [
        ("0-5 sn", f"Kanca: {idea['h']}"),
        ("5-20 sn", f"Bilim: {idea['f']}"),
        ("20-35 sn", f"Detay: {idea['b1']}"),
        ("35-50 sn", f"Şaşırtıcı gerçek: {idea['b2']}"),
        ("50-60 sn", "Kapanış: İzleyiciye soru sor, beğeni/abone çağrısı yap."),
    ]
    return {
        "project_name": f"{idea['s']} — Belgesel",
        "video_title": idea["t"],
        "hook": idea["h"],
        "scenes": scenes,
        "tags": idea["tags"],
        "thumbnail": idea["th"],
        "index": (cursor % len(NICHE_IDEAS)) + 1,
        "total": len(NICHE_IDEAS),
    }


# ============================================================================
# Video Üretim
# ============================================================================
def available_providers() -> List[Dict[str, Any]]:
    if PRODUCTION_READY:
        try:
            production = VideoProductionManager(get_config(), get_token_manager())
            return production.get_available_providers()
        except Exception:
            pass
    return [{"id": "slideshow", "name": "Slideshow (Yerel)", "description":
             "Yerel görsellerden slayt videosu. Ücretsiz.", "available": True, "cost": "Ücretsiz"}]


def render_project_viewmade(item: Dict[str, Any], vm_status: Dict[str, Any]) -> None:
    """Proje detayında ücretli ViewMade render kapısı ve çıktı önizlemesi."""
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.markdown("**ViewMade üretimi**")

    if not vm_status.get("available"):
        st.markdown(badge("VIEWMADE BAĞLI DEĞİL", "warn"), unsafe_allow_html=True)
        st.caption("OAuth oturumu veya araç eşlemesi hazır değil. "
                   "Bağlantıyı yukarıdaki ViewMade panelinden doğrulayın.")
        return

    slug = str(item.get("viewmade_package") or "")
    state = viewmade_render_state(slug) if slug else {}
    request_status = str(state.get("request_status") or "")
    phase = str(state.get("phase") or "")
    render_path = str(state.get("render_path") or "")
    local_path = ROOT / render_path if render_path else None

    if slug and (request_status in {"SUBMITTED", "RENDERING"} or phase in {"starting", "submitted"}):
        st.markdown(badge("RENDER SÜRÜYOR", "info"), unsafe_allow_html=True)
        started = str(state.get("started_at") or "")[:19].replace("T", " ")
        st.caption(f"ViewMade işi arka planda çalışıyor. Başlangıç: {started or '—'} · "
                   f"Sağlayıcı durumu: {state.get('provider_state') or 'sırada'}")
        st.progress(0.45 if request_status == "SUBMITTED" else 0.75)
        if st.button("🔄 Durumu kontrol et", key=f"vm_poll_{item['id']}", width="stretch"):
            st.rerun()
        st.caption("Render tamamlandığında video otomatik indirilir ve bu kartta önizlenir. "
                   "Sayfayı yenilemeniz yeterli.")
        return

    if slug and request_status == "COMPLETE" and local_path and local_path.is_file():
        st.markdown(" ".join([
            badge("VIEWMADE HAZIR", "ok"),
            badge("İNCELEME GEREKLİ", "warn"),
        ]), unsafe_allow_html=True)
        st.video(str(local_path), alt=f"ViewMade çıktısı: {item.get('title', '')}",
                 width=PREVIEW_WIDTH)
        probe = probe_video(str(local_path), local_path.stat().st_mtime)
        duration = probe.get("duration_s")
        resolution = (f"{probe.get('width')}×{probe.get('height')}"
                      if probe.get("width") and probe.get("height") else "—")
        details = f"{local_path.stat().st_size / 1_048_576:.1f} MB · {resolution}"
        if duration:
            details += f" · {duration:.1f} sn"
        st.caption(details)
        st.caption("Bu çıktı editöryal onaydan geçmedi. Görüntü, ses, kaynak atıfları ve "
                   "telif kontrolü yapılmadan YouTube'a yüklemeyin.")
        action_col, info_col = st.columns([1, 1])
        with action_col:
            if st.button("➡️ Yayın Merkezi'nde aç", key=f"vm_pub_{item['id']}",
                         type="primary", width="stretch"):
                st.session_state["publish_video_path"] = str(local_path)
                st.session_state["viewmade_notice"] = (
                    "Video Yayın Merkezi'ne taşındı; aşağıdaki kontrolden inceleyip yükleyin.")
                st.rerun()
        with info_col:
            view_url = f"https://viewmade.com/v/{state.get('job_id')}" if state.get("job_id") else ""
            if view_url:
                st.link_button("ViewMade'de aç", view_url, width="stretch")
        return

    if slug and request_status in {"FAILED", "STALE"}:
        st.markdown(badge("RENDER TAMAMLANMADI", "err"), unsafe_allow_html=True)
        error_text = str(state.get("error") or "").strip()
        if error_text:
            st.caption(error_text[:500])
        st.caption("Çift ücretlendirmeyi önlemek için panel yeni bir render göndermez. "
                   "Mevcut işi ViewMade panelinden veya kurtarma betiğiyle çözün.")
        if state.get("job_id"):
            st.link_button("ViewMade'de aç", f"https://viewmade.com/v/{state.get('job_id')}",
                           width="stretch")
        return

    # Tekrar üretim engeli — YouTube kanalı ve ViewMade sicili
    registry_entries = load_registry()
    own_package = str(item.get("viewmade_package") or "")
    registry_match = registry_find(registry_entries, registry_title_for_item(item))
    if (registry_match and own_package and
            str(registry_match.get("package") or "") == own_package):
        registry_match = None
    registry_value = registry_state(registry_match)
    registry_warning = ""
    if registry_value == "published":
        youtube_id = str((registry_match or {}).get("youtube_id") or "")
        st.error(f"Bu konu YouTube kanalınızda zaten yayında: "
                 f"“{registry_match.get('title')}”. Tekrar üretmeyin.")
        if youtube_id:
            st.link_button("YouTube'da aç", f"https://www.youtube.com/watch?v={youtube_id}",
                           width="stretch")
        viewmade_id = str((registry_match or {}).get("viewmade_id") or "")
        if viewmade_id:
            st.link_button("ViewMade'de aç", f"https://viewmade.com/v/{viewmade_id}",
                           width="stretch")
        return
    if registry_value == "produced":
        st.error("Bu konu için zaten hazır bir ViewMade üretimi var: "
                 f"“{registry_match.get('title')}”. Tekrar üretim kredi harcar; "
                 "mevcut üretimi önizleyin.")
        viewmade_id = str((registry_match or {}).get("viewmade_id") or "")
        if viewmade_id:
            st.link_button("ViewMade'de aç", f"https://viewmade.com/v/{viewmade_id}",
                           width="stretch")
        return
    if registry_value == "rejected":
        registry_warning = ("Önceki sürüm reddedilmişti; düzeltilmiş yeni bir sürüm "
                            "üretmenizde sakınca yok.")
    elif registry_value == "planned":
        registry_warning = ("Bu konu için planlanmış ama henüz üretilmemiş bir paket var; "
                            "yeni render bu planın yerini alır.")

    # Yeni ücretli render formu
    if phase == "failed" and state.get("error"):
        st.warning(f"Önceki render denemesi başarısız: {str(state.get('error'))[:300]}")
    if registry_warning:
        st.warning(registry_warning)
    narration_key = f"vm_narration_{item['id']}"
    if narration_key not in st.session_state:
        st.session_state[narration_key] = default_viewmade_narration(item)
    narration = st.text_area(
        "Anlatım metni (İngilizce)",
        key=narration_key,
        height=150,
        help="ViewMade İngilizce seslendirme yapar. Metni İngilizceye çevirip düzenleyin; "
             "senaryo notları Türkçe kalabilir.",
    )
    if st.button("↺ Anlatımı senaryodan yenile", key=f"vm_reset_narr_{item['id']}"):
        st.session_state[narration_key] = default_viewmade_narration(item)
        st.rerun()

    duration_s = st.slider("Video süresi (sn)", min_value=30, max_value=60, value=45,
                           step=5, key=f"vm_duration_{item['id']}")
    turkish_detected = narration_looks_turkish(narration)
    if turkish_detected:
        st.warning("Anlatım metni Türkçe görünüyor. ViewMade İngilizce seslendirme yapar; "
                   "render başlatmadan önce metni İngilizceye çevirin.")
    english_confirmed = st.checkbox(
        "Anlatım metni İngilizce ve seslendirmeye uygun.",
        value=not turkish_detected,
        key=f"vm_english_{item['id']}",
    )
    st.markdown(
        '<div class="cd-publish-note" style="margin:8px 0 10px">'
        '<b>Ücretli işlem.</b> ViewMade render başına yaklaşık 20 kredi harcar ve '
        'geri alınamaz. Yeni render yalnızca aşağıdaki açık onayla başlar; '
        'video otomatik olarak YouTube\'a yüklenmez.</div>',
        unsafe_allow_html=True,
    )
    confirm = st.text_input("Onay için RENDER yazın", key=f"vm_confirm_{item['id']}",
                            placeholder="RENDER")
    can_start = (confirm.strip().upper() == "RENDER"
                 and bool(narration.strip())
                 and english_confirmed)
    if st.button("🎬 ViewMade render başlat", key=f"vm_start_{item['id']}",
                 type="primary", width="stretch", disabled=not can_start):
        try:
            prepared = prepare_viewmade_package(item, narration, int(duration_s))
            fresh = load_pipeline()
            for updated in fresh:
                if updated["id"] == item["id"]:
                    updated["viewmade_package"] = prepared["slug"]
                    updated["provider"] = "viewmade"
                    updated["viewmade_status"] = "NOT_SUBMITTED"
                    updated["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            save_pipeline(fresh)
            pid = start_viewmade_render(prepared["slug"])
            log_activity(f"ViewMade render başlatıldı: {item['title']} (PID {pid})", "info")
            st.session_state["viewmade_notice"] = (
                "Ücretli ViewMade render arka planda başladı. Durumu bu karttan izleyin.")
            st.rerun()
        except Exception as exc:
            st.error(f"Render başlatılamadı: {exc}")
    st.caption("Onay kutusu yalnızca RENDER yazıldığında etkinleşir.")


def render_production() -> None:
    st.markdown(
        """
        <div class="cd-hero">
          <h1>Video Üretim</h1>
          <p>Planlamadan yayına beş aşamalı üretim hattı. Proje ilerledikçe aşamalar tamamlanır,
          üretim çıktısı bu sayfada önizlenir.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    vm_status = viewmade_status()
    providers = available_providers()
    if not any(provider["id"] == "viewmade" for provider in providers):
        providers.insert(1, {"id": "viewmade", "name": "ViewMade",
                             "description": "ViewMade OAuth/MCP hattı ile gerçek video üretimi.",
                             "available": False, "cost": "Kredi"})
    for provider in providers:
        if provider["id"] == "viewmade":
            provider["available"] = bool(vm_status.get("available"))
            provider["description"] = "ViewMade OAuth/MCP hattı ile gerçek video üretimi."
            provider["cost"] = "Kredi · render başına ~20"
    provider_names = {provider["id"]: provider["name"] for provider in providers}
    provider_avail = {provider["id"]: provider.get("available", False) for provider in providers}

    agent_notice = st.session_state.pop("agent_notice", "")
    if agent_notice:
        st.success(agent_notice)
    vm_notice = st.session_state.pop("viewmade_notice", "")
    if vm_notice:
        st.success(vm_notice)
    publish_notice = st.session_state.pop("publish_notice", "")
    if publish_notice:
        st.success(publish_notice)
        publish_url = st.session_state.pop("publish_result_url", "")
        if publish_url:
            st.link_button("YouTube'da aç", publish_url)

    # İçerik sicili — YouTube kanalı ve ViewMade üretimleri tek sicilde eşlenir
    registry_entries = sync_content_registry()
    published_count = sum(1 for entry in registry_entries
                          if registry_state(entry) == "published")
    produced_count = sum(1 for entry in registry_entries
                         if registry_state(entry) in {"published", "produced"})

    # İçerik Ajanı — niş odaklı proje önerisi
    panel_open("İÇERİK AJANI · NİŞ ÖNERİSİ")
    st.markdown(
        f"""
        <div class="cd-agent-panel">
          <div class="cd-agent-panel-head">
            <div class="cd-agent-panel-icon">🧭</div>
            <div style="flex:1">
              <div class="cd-agent-panel-name">İçerik Ajanı</div>
              <div class="cd-agent-panel-role">Kedi &amp; Köpek Belgeseli · Proje Öneri Motoru</div>
            </div>
            {badge(f"{len(NICHE_IDEAS)} konu havuzu", "info")}
          </div>
          <div class="cd-agent-panel-desc">
            Kanalın nişine göre proje adı, İngilizce video başlığı, kanca, beş sahnelik senaryo taslağı,
            etiketler ve kapak konsepti üretir. Beğendiğiniz öneriyi tek tıkla üretim hattına ekleyin.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"İçerik sicili: {len(registry_entries)} eşleşen içerik · {published_count} YouTube'da "
               f"yayında · {produced_count} üretilmiş. Yayındaki ve üretilmiş konular öneri havuzundan "
               "otomatik çıkarılır.")

    has_proposal = bool(st.session_state.get("agent_proposal"))

    def _new_proposal() -> None:
        cursor = int(st.session_state.get("proposal_cursor", 0))
        proposal_item, next_cursor = choose_proposal(cursor, registry_entries, load_pipeline())
        if proposal_item is None:
            st.session_state.pop("agent_proposal", None)
            st.session_state["agent_notice"] = (
                "Havuzdaki tüm konular üretildi veya YouTube'da yayında. "
                "Tekrar üretim yapılmadı; yeni konu için havuzu genişletin.")
            return
        st.session_state["agent_proposal"] = proposal_item
        st.session_state["proposal_cursor"] = next_cursor

    suggest_col, next_col, close_col = st.columns([2, 2, 2])
    with suggest_col:
        if st.button("🧭 Bana Proje Öner", type="primary", use_container_width=True,
                     key="agent_suggest"):
            _new_proposal()
            st.rerun()
    with next_col:
        if st.button("🔁 Başka Öner", use_container_width=True,
                     key="agent_next", disabled=not has_proposal):
            _new_proposal()
            st.rerun()
    with close_col:
        if has_proposal:
            if st.button("✕ Öneriyi Kapat", use_container_width=True, key="agent_close"):
                st.session_state.pop("agent_proposal", None)
                st.rerun()

    proposal = st.session_state.get("agent_proposal")
    if proposal:
        scene_rows = "".join(
            f'<div class="cd-scene"><span class="cd-scene-time">{escape(str(label))}</span>'
            f'<span>{escape(str(text))}</span></div>'
            for label, text in proposal["scenes"]
        )
        registry_info = proposal.get("registry") or {}
        registry_info_state = registry_info.get("state")
        if registry_info_state == "rejected":
            registry_badge = badge("ÖNCEKİ SÜRÜM REDDEDİLDİ · YENİDEN ÜRETİLEBİLİR", "warn")
        elif registry_info_state == "planned":
            registry_badge = badge("PLANDA VAR · HENÜZ ÜRETİLMEDİ", "warn")
        else:
            registry_badge = badge("YENİ KONU · KANALDA YOK", "ok")
        st.markdown(
            f"""
            <div class="cd-proposal">
              <div class="cd-proposal-kicker">Öneri {proposal['index']} / {proposal['total']} · Belgesel {registry_badge}</div>
              <div class="cd-proposal-name">{escape(proposal['project_name'])}</div>
              <div class="cd-proposal-title">{escape(proposal['video_title'])}</div>
              <div class="cd-hook">“{escape(proposal['hook'])}”</div>
              <div class="cd-scenes">{scene_rows}</div>
              <div class="cd-meta-grid">
                <div class="cd-meta">
                  <div class="cd-meta-label">Etiketler</div>
                  <div class="cd-meta-value">{escape(proposal['tags'])}</div>
                </div>
                <div class="cd-meta">
                  <div class="cd-meta-label">Kapak Konsepti</div>
                  <div class="cd-meta-value">{escape(proposal['thumbnail'])}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        add_col, hint_col = st.columns([2, 4])
        with add_col:
            if st.button("✅ Projeyi Hatta Ekle", type="primary", use_container_width=True,
                         key="agent_add"):
                chosen_provider = SETTINGS.get("default_provider", "slideshow")
                if chosen_provider not in provider_names or chosen_provider not in provider_avail:
                    chosen_provider = "slideshow"
                if not provider_avail.get(chosen_provider, False) and "slideshow" in provider_names:
                    chosen_provider = "slideshow"
                outline = "\n".join(f"[{label}] {text}" for label, text in proposal["scenes"])
                outline += (f"\n\nVideo başlığı (EN): {proposal['video_title']}"
                            f"\nEtiketler: {proposal['tags']}"
                            f"\nKapak: {proposal['thumbnail']}")
                add_project(proposal["project_name"], proposal["hook"], chosen_provider, script=outline)
                st.session_state["pending_project_meta"] = {
                    "duration": int(SETTINGS.get("video_duration", 60)),
                    "aspect": SETTINGS.get("aspect_ratio", "16:9"),
                }
                st.session_state["agent_notice"] = (
                    f"Proje hatta eklendi: {proposal['project_name']} — Planlama aşamasında."
                )
                log_activity(f"İçerik ajanı proje önerdi: {proposal['project_name']}", "ok")
                st.session_state.pop("agent_proposal", None)
                st.rerun()
        with hint_col:
            st.caption("Eklenen proje Planlama aşamasından başlar; video başlığı, kanca, senaryo, "
                       "etiketler ve kapak konsepti proje detayına kaydedilir.")
            if registry_info.get("state") == "rejected":
                st.caption("Not: bu konunun önceki sürümü reddedilmişti; yeni sürümde kaynak, "
                           "kalite ve telif kontrollerini mutlaka yapın.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # ViewMade bağlantısı ve üretim önizlemesi
    # ------------------------------------------------------------------
    panel_open("VIEWMADE BAĞLANTISI · MCP")
    vm_ok = bool(vm_status.get("available"))
    vm_error = st.session_state.pop("viewmade_error", "")
    if vm_error:
        st.error(f"ViewMade bağlantı hatası: {vm_error}")
    conn_class = "" if vm_ok else " is-warn"
    conn_badges = []
    conn_badges.append(badge("BAĞLI" if vm_status.get("authenticated") else "BAĞLI DEĞİL",
                             "ok" if vm_status.get("authenticated") else "err"))
    conn_badges.append(badge("3/3 ARAÇ" if vm_status.get("bound") else "EŞLEME EKSİK",
                             "ok" if vm_status.get("bound") else "warn"))
    conn_badges.append(badge(f"{vm_status.get('tool_count', 0)} MCP ARACI", "info"))
    expires_at = vm_status.get("expires_at")
    expiry_text = expires_at.strftime("%d.%m.%Y %H:%M") if expires_at else "—"
    days_text = f"{vm_status.get('days_left')} gün" if vm_status.get("days_left") is not None else "—"
    scope_text = (vm_status.get("scope") or "").replace(" ", " · ")
    st.markdown(
        f"""
        <div class="cd-conn{conn_class}">
          <div class="cd-conn-head">
            <div class="cd-conn-icon">🔗</div>
            <div style="flex:1">
              <div class="cd-conn-name">ViewMade MCP</div>
              <div class="cd-conn-sub">OAuth 2.0 · {escape(str(vm_status.get('endpoint') or 'https://mcp.viewmade.com/mcp'))}</div>
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap">{''.join(conn_badges)}</div>
          </div>
          <div class="cd-conn-stats">
            <div class="cd-conn-stat">
              <div class="cd-conn-label">Token geçerliliği</div>
              <div class="cd-conn-value">{expiry_text} · {days_text}</div>
            </div>
            <div class="cd-conn-stat">
              <div class="cd-conn-label">Render / durum / indirme</div>
              <div class="cd-conn-value">{'Hazır' if vm_status.get('bound') else 'Eksik'}</div>
            </div>
            <div class="cd-conn-stat">
              <div class="cd-conn-label">Kapsam</div>
              <div class="cd-conn-value" style="font-size:.76rem">{escape(scope_text) or '—'}</div>
            </div>
            <div class="cd-conn-stat">
              <div class="cd-conn-label">Yenileme</div>
              <div class="cd-conn-value">{'Destekli' if vm_status.get('refreshable') else 'Yeniden giriş'}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    vm_action_1, vm_action_2, vm_action_3 = st.columns([2, 2, 2])
    with vm_action_1:
        if st.button("🔌 Canlı bağlantıyı test et", width="stretch", key="vm_live_test"):
            list_viewmade_videos.clear()
            with st.spinner("ViewMade MCP sorgulanıyor…"):
                probe = list_viewmade_videos()
            if probe.get("ok"):
                st.session_state["viewmade_notice"] = (
                    f"MCP bağlantısı doğrulandı — {len(probe.get('items', []))} üretim listelendi.")
            else:
                st.session_state["viewmade_error"] = probe.get("error") or "bilinmeyen hata"
            st.rerun()
    with vm_action_2:
        if st.button("🔄 Videoları yenile", width="stretch", key="vm_refresh"):
            list_viewmade_videos.clear()
            st.session_state["viewmade_notice"] = "ViewMade video listesi yenilendi."
            st.rerun()
    with vm_action_3:
        st.link_button("ViewMade panelini aç", vm_status.get("connect_url") or
                       "https://viewmade.com/dashboard/connect", width="stretch")

    if not vm_ok:
        st.markdown(
            '<div class="cd-publish-note" style="margin-top:12px">ViewMade bağlantısı hazır değil. '
            'OAuth oturumunu yenileyin ve araç eşlemesinin 3/3 olduğunu doğrulayın.</div>',
            unsafe_allow_html=True,
        )

    vm_list = list_viewmade_videos() if vm_ok else {"ok": False, "items": [], "error": ""}
    if vm_ok and not vm_list.get("ok"):
        st.error(f"ViewMade video listesi alınamadı: {vm_list.get('error')}")
    elif vm_ok:
        vm_items = [item for item in vm_list.get("items", []) if item.get("status") == "ready"]
        if not vm_items:
            st.info("ViewMade hesabında hazır video bulunmuyor.", icon="🎬")
        else:
            def _vm_label(item: Dict[str, Any]) -> str:
                created = str(item.get("created_at") or "")[:10]
                entry = registry_find(registry_entries, str(item.get("title") or ""),
                                      viewmade_id=str(item.get("id") or ""))
                mark = " · ✓ YouTube'da" if (entry or {}).get("youtube_id") else ""
                return f"{item.get('title') or 'Başlıksız'} · {created}{mark}"

            selected_vm_id = st.selectbox(
                "ViewMade üretimi",
                options=[str(item["id"]) for item in vm_items],
                format_func=lambda value: _vm_label(
                    next(item for item in vm_items if str(item["id"]) == value)),
                key="vm_video_select",
            )
            selected_vm = next(item for item in vm_items if str(item["id"]) == selected_vm_id)
            local_vm = find_local_viewmade_video(selected_vm_id)
            vm_preview_col, vm_meta_col = st.columns([3, 2])
            with vm_preview_col:
                if local_vm:
                    st.video(str(local_vm), alt=f"ViewMade önizlemesi: {selected_vm.get('title')}",
                             width=PREVIEW_WIDTH)
                else:
                    st.markdown(
                        f"""
                        <div class="cd-video-card" style="margin-bottom:10px">
                          <div class="cd-video-title">{escape(str(selected_vm.get('title') or 'ViewMade videosu'))}</div>
                          <div class="cd-video-sub">VIEWMADE'DE HAZIR · YEREL KOPYA YOK</div>
                          <div style="color:var(--t2); font-size:.86rem; line-height:1.55; margin-top:10px">
                            Video ViewMade hesabında tamamlandı. Önizlemek için indirin; indirme ücretsizdir,
                            yeni render başlatmaz.
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            selected_entry = registry_find(registry_entries,
                                           str(selected_vm.get("title") or ""),
                                           viewmade_id=selected_vm_id)
            selected_youtube_id = str((selected_entry or {}).get("youtube_id") or "")
            with vm_meta_col:
                status_badges = [badge("VIEWMADE HAZIR", "ok")]
                status_badges.append(badge("YOUTUBE'DA YAYINDA", "err") if selected_youtube_id
                                     else badge("İNCELEME GEREKLİ", "warn"))
                st.markdown(" ".join(status_badges), unsafe_allow_html=True)
                if selected_youtube_id:
                    st.link_button("YouTube'da aç",
                                   f"https://www.youtube.com/watch?v={selected_youtube_id}",
                                   width="stretch")
                if local_vm:
                    probe = probe_video(str(local_vm), local_vm.stat().st_mtime)
                    duration = probe.get("duration_s")
                    resolution = (f"{probe.get('width')}×{probe.get('height')}"
                                  if probe.get("width") and probe.get("height") else "—")
                    st.caption(f"Yerel kopya · {local_vm.stat().st_size / 1_048_576:.1f} MB · "
                               f"{resolution} · {duration:.1f} sn" if duration else
                               f"Yerel kopya · {local_vm.stat().st_size / 1_048_576:.1f} MB")
                    if st.button("➡️ Yayın Merkezi'nde aç", width="stretch", key="vm_to_publish"):
                        st.session_state["publish_video_path"] = str(local_vm)
                        st.session_state["viewmade_notice"] = (
                            "Video Yayın Merkezi'ne taşındı. Aşağıdaki yayın kontrolünden inceleyip yükleyin.")
                        st.rerun()
                else:
                    if st.button("⬇️ Önizlemeyi getir", type="primary", width="stretch",
                                 key="vm_download_preview"):
                        try:
                            with st.spinner("ViewMade videosu indiriliyor ve önizlemeye hazırlanıyor…"):
                                download_viewmade_preview(selected_vm_id)
                            st.session_state["viewmade_notice"] = "Video indirildi ve önizlemeye hazır."
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Video indirilemedi: {exc}")
                st.link_button("ViewMade'de aç",
                               f"https://viewmade.com/v/{selected_vm_id}", width="stretch")
                with st.expander("Video bilgisi"):
                    st.write(f"**Başlık:** {selected_vm.get('title') or '—'}")
                    st.write(f"**Durum:** {selected_vm.get('status') or '—'}")
                    st.write(f"**Oluşturma:** {str(selected_vm.get('created_at') or '—')[:19]}")
                    st.caption("ViewMade çıktıları yayın öncesi insan incelemesi ve atıf kontrolü gerektirir.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ViewMade ↔ YouTube eşleşmesi — aynı video tekrar tekrar üretilmez
    panel_open("VIEWMADE ↔ YOUTUBE EŞLEŞMESİ")
    matched_rows: List[Dict[str, str]] = []
    if vm_list.get("ok"):
        for item in vm_list.get("items", []):
            vm_id = str(item.get("id") or "")
            entry = registry_find(registry_entries, str(item.get("title") or ""),
                                  viewmade_id=vm_id)
            youtube_id = str((entry or {}).get("youtube_id") or "")
            local_copy = find_local_viewmade_video(vm_id)
            matched_rows.append({
                "ViewMade Videosu": str(item.get("title") or "Başlıksız"),
                "Üretim": "Hazır" if item.get("status") == "ready" else str(item.get("status") or "—"),
                "Yerel Kopya": "Var" if local_copy else "Yok",
                "YouTube": f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else "",
                "Durum": "YouTube'da yayında" if youtube_id else "Henüz yayınlanmadı",
            })
    if matched_rows:
        matched_total = sum(1 for row in matched_rows if row["YouTube"])
        st.markdown(" ".join([
            badge(f"{matched_total}/{len(matched_rows)} YOUTUBE'DA", "ok" if matched_total else "warn"),
            badge("BAŞLIK + VIEWMADE KİMLİĞİ EŞLEŞMESİ", "muted", dot=False),
        ]), unsafe_allow_html=True)
        st.dataframe(
            matched_rows,
            hide_index=True,
            width="stretch",
            alt="ViewMade üretimlerinin YouTube kanalıyla eşleşme tablosu",
            column_config={
                "YouTube": st.column_config.LinkColumn("YouTube", display_text="İzle"),
                "Üretim": st.column_config.TextColumn("Üretim", width="small"),
                "Yerel Kopya": st.column_config.TextColumn("Yerel Kopya", width="small"),
            },
        )
        st.caption("Eşleşen üretimler YouTube kanalınızda yayında; panel bunlar için yeni ücretli "
                   "render göndermez ve tekrar yüklemeyi engeller.")
        if st.button("🔄 Eşleşmeyi yenile", key="registry_refresh", width="stretch"):
            channel_videos_index.clear()
            list_viewmade_videos.clear()
            st.session_state["viewmade_notice"] = "İçerik sicili ve YouTube eşleşmesi yenilendi."
            st.rerun()
    else:
        st.caption("Eşleşme tablosu için ViewMade video listesi gerekir.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Aşama şeridi
    cols = st.columns(len(PIPELINE_STAGES))
    for position, stage in enumerate(PIPELINE_STAGES):
        with cols[position]:
            st.markdown(
                f"""<div class="cd-stage">
                      <div class="cd-stage-icon">{stage['icon']}</div>
                      <div class="cd-stage-name">{stage['name']}</div>
                      <div class="cd-stage-state">Aşama {position + 1}</div>
                    </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Sağlayıcı durumları
    panel_open("VİDEO SAĞLAYICILARI")
    chips = []
    for provider in providers:
        state = "ok" if provider.get("available") else "muted"
        chips.append(badge(provider["name"], state))
    st.markdown(" ".join(chips), unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Yeni proje formu
    form_col, info_col = st.columns([3, 2])
    with form_col:
        panel_open("YENİ PROJE")
        with st.form("new_project_form", border=False):
            title = st.text_input("Proje Adı", placeholder="Örn: Kedilerin Tarihçesi Bölüm 1")
            topic = st.text_area("Konu / Senaryo Fikri", placeholder="Videonun işleyeceği konuyu kısaca yazın…",
                                 height=110)
            choosable = [provider["id"] for provider in providers]
            default_provider = SETTINGS.get("default_provider", "slideshow")
            if default_provider not in choosable:
                default_provider = "slideshow"
            provider_id = st.selectbox("Sağlayıcı", options=choosable,
                                       index=choosable.index(default_provider) if default_provider in choosable else 0,
                                       format_func=lambda pid: provider_names.get(pid, pid))
            detail_col_1, detail_col_2 = st.columns(2)
            with detail_col_1:
                duration = st.number_input("Süre (sn)", min_value=10, max_value=3600,
                                           value=int(SETTINGS.get("video_duration", 60)), step=10)
            with detail_col_2:
                aspect = st.selectbox("En-Boy Oranı", options=["16:9", "9:16", "1:1"],
                                      index=["16:9", "9:16", "1:1"].index(SETTINGS.get("aspect_ratio", "16:9"))
                                      if SETTINGS.get("aspect_ratio") in ("16:9", "9:16", "1:1") else 0)
            submitted = st.form_submit_button("🚀 Projeyi Başlat", type="primary", use_container_width=True)
            if submitted:
                if not title.strip():
                    st.error("Proje adı gerekli.")
                elif not topic.strip():
                    st.error("Konu metni gerekli.")
                elif not provider_avail.get(provider_id, False):
                    st.error("Seçilen sağlayıcı yapılandırılmamış. Ayarlar sayfasından API anahtarlarını ekleyin.")
                else:
                    existing = (registry_find(registry_entries, title.strip()) or
                                registry_find(registry_entries, topic.strip()))
                    if registry_state(existing) in {"published", "produced"}:
                        st.error("Bu konu zaten yayında veya üretilmiş: "
                                 f"“{existing.get('title')}”. Tekrar proje açmak yerine mevcut "
                                 "üretimi Yayın Merkezi'nden yönetin.")
                    else:
                        add_project(title.strip(), topic.strip(), provider_id)
                        st.session_state["pending_project_meta"] = {
                            "duration": int(duration), "aspect": aspect}
                        st.success(f"Proje oluşturuldu: {title.strip()} — Planlama aşamasında.")
                        st.rerun()
    with info_col:
        panel_open("HAT AKIŞI")
        st.markdown(
            """
            <div class="cd-panel">
              <div style="color:var(--t2); font-size:.88rem; line-height:1.75">
                <b style="color:var(--text)">1 · Planlama</b> — konu, hedef kitle ve takvim belirlenir.<br>
                <b style="color:var(--text)">2 · Senaryo</b> — senaryo ajanı taslağı yazar, siz düzenlersiniz.<br>
                <b style="color:var(--text)">3 · Üretim</b> — seçilen sağlayıcı videoyu işler.<br>
                <b style="color:var(--text)">4 · İnceleme</b> — önizleme ekranında onay verirsiniz.<br>
                <b style="color:var(--text)">5 · Yayın</b> — YouTube'a yüklenir (varsayılan: gizli).
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not PRODUCTION_READY:
            st.markdown(badge("Üretim modülü: temel mod", "warn"), unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # Proje kartları
    panel_open("PROJELER")
    pipeline_items = sync_viewmade_projects(load_pipeline())
    if not pipeline_items:
        st.markdown('<div class="cd-panel" style="color:var(--muted)">Henüz proje yok. '
                    'Yukarıdaki formla ilk projeyi başlatın.</div>', unsafe_allow_html=True)
    for item in pipeline_items:
        with st.container(border=True):
            head_left, head_right = st.columns([3, 2])
            with head_left:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:10px'>"
                    f"<span style='font-family:var(--mono); font-size:.72rem; color:var(--muted)'>"
                    f"{item['id']}</span>"
                    f"<span style='font-weight:700; color:var(--text)'>{item['title']}</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Sağlayıcı: {provider_names.get(item.get('provider', ''), '—')} · "
                           f"Oluşturma: {item.get('created_at', '')}")
            with head_right:
                state = "ok" if item["stage_index"] >= len(PIPELINE_STAGES) else ("info" if item["stage_index"] else "warn")
                state_text = ("Yayında" if item["stage_index"] >= len(PIPELINE_STAGES)
                              else f"Aşama {item['stage_index'] + 1}/{len(PIPELINE_STAGES)} · "
                                   f"{PIPELINE_STAGES[min(item['stage_index'], len(PIPELINE_STAGES) - 1)]['name']}")
                st.markdown(badge(state_text, state), unsafe_allow_html=True)

            # AşamaIZ tracker
            track = st.columns(len(PIPELINE_STAGES))
            for position, stage in enumerate(PIPELINE_STAGES):
                with track[position]:
                    state = stage_state(item["stage_index"], position)
                    cls = {"done": "cd-stage cd-stage-done", "active": "cd-stage cd-stage-active"}.get(state, "cd-stage")
                    st.markdown(
                        f"""<div class="{cls}">
                              <div class="cd-stage-icon">{stage['icon']}</div>
                              <div class="cd-stage-name">{stage['name']}</div>
                              <div class="cd-stage-state">{stage_label(state)}</div>
                            </div>""",
                        unsafe_allow_html=True,
                    )

            # Önizleme
            output_path = item.get("output_path", "")
            if output_path and os.path.exists(output_path) and item["stage_index"] >= 3:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                st.markdown(badge("ÖNİZLEME HAZIR", "info"), unsafe_allow_html=True)
                st.video(output_path, alt=f"Proje önizlemesi: {item['title']}",
                         width=PREVIEW_WIDTH)
                try:
                    with open(output_path, "rb") as handle:
                        st.download_button("⬇️ Videoyu İndir", data=handle.read(),
                                           file_name=os.path.basename(output_path),
                                           mime="video/mp4",
                                           key=f"dl_{item['id']}")
                except OSError:
                    pass

            # Kontroller
            control_left, control_right = st.columns([1, 3])
            with control_left:
                if item["stage_index"] < len(PIPELINE_STAGES):
                    next_stage = PIPELINE_STAGES[min(item["stage_index"], len(PIPELINE_STAGES) - 1)]["name"]
                    if st.button("⏭️ Sonraki Aşamaya Geç", key=f"adv_{item['id']}",
                                 use_container_width=True, type="primary"):
                        advance_project(item["id"])
                        # Üretim aşamasına girildiğinde çıktı yolu rezerve et
                        items = load_pipeline()
                        for updated in items:
                            if updated["id"] == item["id"] and updated["stage_index"] == 3 and not updated.get("output_path"):
                                safe = "".join(ch for ch in item["title"] if ch.isalnum() or ch in " -_").strip() or "video"
                                updated["output_path"] = str(ROOT / "outputs" / f"{safe}_{item['id']}.mp4")
                                save_pipeline(items)
                        st.rerun()
                    st.caption(f"Sonraki: {next_stage if item['stage_index'] == 0 else PIPELINE_STAGES[min(item['stage_index']+1, len(PIPELINE_STAGES)-1)]['name']}")
            with control_right:
                if st.button("🗑️ Sil", key=f"del_{item['id']}"):
                    delete_project(item["id"])
                    st.rerun()
                detail = st.expander("Proje Detayı")
                with detail:
                    st.write(f"**Konu:** {item.get('topic', '')}")
                    script = st.text_area("Senaryo Notları", value=item.get("script", ""),
                                          key=f"scr_{item['id']}", height=120)
                    notes = st.text_area("Yönetici Notları", value=item.get("notes", ""),
                                         key=f"not_{item['id']}", height=80)
                    if st.button("💾 Detayları Kaydet", key=f"save_{item['id']}"):
                        items = load_pipeline()
                        for updated in items:
                            if updated["id"] == item["id"]:
                                updated["script"] = script
                                updated["notes"] = notes
                                updated["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                        save_pipeline(items)
                        st.success("Kaydedildi.")
                    render_project_viewmade(item, vm_status)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # Yerel video önizlemeleri — renders/ + outputs/
    entries = local_video_entries()
    panel_open("VİDEO ÖNİZLEMELERİ")
    if not entries:
        st.info("Henüz yerel video çıktısı yok. Bir projede ViewMade render tamamlandığında "
                "veya yerel üretim bittiğinde video burada görünür.", icon="🎬")
    else:
        st.caption("Hazır çıktılar. ViewMade videoları yayın öncesi editöryal inceleme gerektirir.")
        grid = st.columns(3)
        for index, entry in enumerate(entries[:6]):
            with grid[index % 3]:
                st.video(str(entry["path"]), alt=f"Önizleme: {entry['title']}",
                         width=GALLERY_PREVIEW_WIDTH)
                st.markdown(f"**{entry['title']}**")
                meta_bits = [entry["source"], f"{entry['size_mb']:.1f} MB"]
                duration = (entry.get("probe") or {}).get("duration_s")
                if duration:
                    meta_bits.append(f"{duration:.1f} sn")
                st.caption(" · ".join(meta_bits))
                if st.button("Yayın Merkezi'ne taşı", key=f"gal_pub_{index}", width="stretch"):
                    st.session_state["publish_video_path"] = str(entry["path"])
                    st.session_state["viewmade_notice"] = (
                        "Video Yayın Merkezi'ne taşındı; aşağıdaki kontrolden inceleyip yükleyin.")
                    st.rerun()

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Yayın Merkezi — insan incelemesi + yazılı onay + kontrollü YouTube yüklemesi
    panel_open("YAYIN MERKEZİ")
    if not entries:
        st.caption("Yayın Merkezi için hazır video gerekir.")
        return

    paths = [str(entry["path"]) for entry in entries]
    if st.session_state.get("publish_select") not in paths:
        st.session_state.pop("publish_select", None)
    wanted = st.session_state.pop("publish_video_path", "")
    if wanted in paths:
        st.session_state["publish_select"] = wanted

    selected_path = st.selectbox(
        "Yayınlanacak video",
        options=paths,
        format_func=lambda value: next(
            f"{entry['title']} · {entry['source']}" for entry in entries
            if str(entry["path"]) == value),
        key="publish_select",
    )
    entry = next(item for item in entries if str(item["path"]) == selected_path)
    probe = entry.get("probe") or {}
    publish_registry = registry_find(registry_entries, entry["title"])
    published_youtube_url = ""
    if registry_state(publish_registry) == "published":
        published_youtube_url = (f"https://www.youtube.com/watch?v="
                                 f"{publish_registry.get('youtube_id')}")
    lowered = f"{entry['name']} {entry['title']}".lower()
    blocked_reason = ""
    if "dog-guilty-look" in lowered or "guilty look" in lowered:
        blocked_reason = ("Bu pilot yayın için reddedildi: kaynakları eğlence/derleme "
                          "klipleri, görünür filigran ve yerel kanıt kaydıyla uyuşmayan "
                          "anlatım içeriyor. Yayınlamayın; yeni ve onaylı bir render kullanın.")
    elif published_youtube_url:
        blocked_reason = ("Bu video YouTube kanalınızda zaten yayında. Aynı video tekrar "
                          "yüklenmez; yeni bir sürüm için farklı içerik üretin.")
    elif not probe.get("ok") or probe.get("issues"):
        blocked_reason = ("Video dosyası doğrulanamadı. Dosya bozuk veya eksik olabilir; "
                          "yükleme güvenlik nedeniyle kapatıldı.")

    preview_col, meta_col = st.columns([3, 2])
    with preview_col:
        st.video(str(entry["path"]), alt=f"Yayın önizlemesi: {entry['title']}",
                 width=PREVIEW_WIDTH)
    with meta_col:
        status_badges = [badge(entry["source"].upper(), "info")]
        status_badges.append(badge("YOUTUBE'DA YAYINDA", "err") if published_youtube_url
                             else badge("İNCELEME GEREKLİ", "warn"))
        st.markdown(" ".join(status_badges), unsafe_allow_html=True)
        st.markdown(f"**{entry['title']}**")
        resolution = (f"{probe.get('width')}×{probe.get('height')}"
                      if probe.get("width") and probe.get("height") else "—")
        duration = probe.get("duration_s")
        st.caption(f"{entry['size_mb']:.1f} MB · {resolution}" +
                   (f" · {duration:.1f} sn" if duration else ""))
        if entry.get("provider_status"):
            st.caption(f"Sağlayıcı durumu: {entry['provider_status']}")
        if blocked_reason:
            st.error(blocked_reason)
            if published_youtube_url:
                st.link_button("YouTube'da aç", published_youtube_url, width="stretch")
        else:
            st.markdown(
                '<div class="cd-publish-note">Yükleme öncesi videoyu baştan sona izleyin. '
                'ViewMade çıktıları otomatik olarak onaylı sayılmaz; kaynak atıflarını ve '
                'görüntü kalitesini kontrol edin.</div>',
                unsafe_allow_html=True,
            )
        if entry.get("subject_note"):
            with st.expander("Editöryal not"):
                st.write(entry["subject_note"])
        if entry.get("attributions"):
            with st.expander("Kaynak atıfları"):
                for line in entry["attributions"][:15]:
                    st.markdown(f"- {line}")

    safe_key = (re.sub(r"[^a-zA-Z0-9_-]", "_", entry["name"]) + "_" +
                hashlib.sha256(str(entry["path"]).encode("utf-8")).hexdigest()[:8])
    title_default = str(entry["title"])[:100]
    description_default = publish_description(entry)
    tags_default = ", ".join(str(tag) for tag in entry["tags"])

    title_value = st.text_input("Başlık", value=title_default, max_chars=100,
                                key=f"pub_title_{safe_key}")
    description_value = st.text_area("Açıklama", value=description_default, height=180,
                                     max_chars=5000, key=f"pub_desc_{safe_key}")
    tags_value = st.text_input("Etiketler (virgülle ayırın)", value=tags_default,
                               key=f"pub_tags_{safe_key}")

    privacy_labels = {
        "Gizli — yalnızca kanal yöneticileri": "private",
        "Liste dışı — bağlantıyla erişilir": "unlisted",
        "Herkese açık — herkes görebilir": "public",
    }
    default_privacy = SETTINGS.get("default_privacy", "unlisted")
    privacy_index = next((index for index, value in enumerate(privacy_labels.values())
                          if value == default_privacy), 1)
    privacy_label = st.selectbox("Gizlilik", options=list(privacy_labels), index=privacy_index,
                                 key=f"pub_privacy_{safe_key}")
    privacy = privacy_labels[privacy_label]

    reviewed = st.checkbox(
        "Videoyu baştan sona izledim; görüntü, ses, kaynak atıfları ve telif açısından "
        "yayına uygun buldum.",
        key=f"pub_review_{safe_key}",
    )
    confirm_text = st.text_input("Yükleme onayı için YAYINLA yazın",
                                 key=f"pub_confirm_{safe_key}", placeholder="YAYINLA")

    quota_used = get_quota_used()
    try:
        quota_limit = int(getattr(get_config(), "daily_quota_limit", 10000) or 10000)
    except Exception:
        quota_limit = 10000
    try:
        target_channel = active_channel()
        channel_text = (f"{target_channel.get('title')} · {target_channel.get('channel_id')}"
                        if target_channel else "Kanal seçilmedi")
    except Exception:
        target_channel = None
        channel_text = "Kanal bilgisi alınamadı"
    st.caption(f"Hedef kanal: {channel_text} · Bugünkü YouTube API kotası: "
               f"{quota_used} / {quota_limit} · Seçili gizlilik: {privacy}")

    upload_allowed = (
        not blocked_reason
        and target_channel is not None
        and reviewed
        and confirm_text.strip().upper() == "YAYINLA"
        and bool(title_value.strip())
    )
    if st.button("🚀 YouTube'a yükle", type="primary", width="stretch",
                 disabled=not upload_allowed, key=f"pub_upload_{safe_key}"):
        if len(title_value) > 100:
            st.error("Başlık 100 karakteri aşamaz.")
        else:
            tags = [part.strip() for part in re.split(r"[,\n]", tags_value) if part.strip()]
            try:
                with st.spinner("YouTube'a yükleniyor… Bu işlem birkaç dakika sürebilir."):
                    manager = get_upload_manager()
                    result = manager.upload_short(
                        str(entry["path"]),
                        title_value.strip(),
                        description_value.strip(),
                        tags,
                        privacy_status=privacy,
                        category_id=str(SETTINGS.get("category_id", "15")),
                        confirm_public=(privacy == "public"),
                    )
                video_id = result.get("video_id") or ""
                video_url = result.get("video_url") or (
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
                fresh = load_pipeline()
                for updated in fresh:
                    if (updated.get("output_path") and
                            Path(str(updated["output_path"])).resolve() == entry["path"].resolve()):
                        updated["video_id"] = video_id
                        updated["stage_index"] = len(PIPELINE_STAGES)
                        updated["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                save_pipeline(fresh)
                upload_registry = load_registry()
                if registry_merge(upload_registry, title_value.strip(), source="upload",
                                  youtube_id=video_id or None,
                                  viewmade_id=str((publish_registry or {}).get("viewmade_id") or "") or None,
                                  status="uploaded"):
                    save_registry(upload_registry)
                channel_videos_index.clear()
                log_activity(f"Video YouTube'a yüklendi: {title_value.strip()} "
                             f"({privacy})", "ok")
                st.session_state["publish_notice"] = (
                    f"Video YouTube'a yüklendi · {privacy} · Video kimliği: {video_id}")
                st.session_state["publish_result_url"] = video_url
                st.rerun()
            except Exception as exc:
                st.error(f"Yükleme başarısız: {exc}")

    history = upload_history_entries(5)
    if history:
        with st.expander("Son yüklemeler"):
            for row in history:
                st.markdown(
                    f"- **{row.get('file_name') or '—'}** · {row.get('privacy_status') or '—'} "
                    f"· {str(row.get('uploaded_at') or '')[:19]} · "
                    f"[YouTube]({row.get('video_url') or '#'})"
                )


# ============================================================================
# Ajanlar
# ============================================================================
def render_agents() -> None:
    st.markdown(
        """
        <div class="cd-hero">
          <h1>Ajanlar</h1>
          <p>Yedi uzman otomasyon ajanı. Her ajan üretim hattının ilgili aşamasında çalışır;
          açıp kapatabilir, her birine özel hızlı işlemler çalıştırabilirsiniz.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    enabled = SETTINGS.setdefault("agents_enabled", dict(DEFAULT_SETTINGS["agents_enabled"]))
    active_count = sum(1 for agent in AGENTS if enabled.get(agent["id"], True))
    left_b, right_b = st.columns(2)
    with left_b:
        st.markdown(badge(f"{active_count}/{len(AGENTS)} ajan aktif", "info"), unsafe_allow_html=True)
    with right_b:
        if st.button("🔄 Varsayılana Döndür", use_container_width=True):
            enabled.update(DEFAULT_SETTINGS["agents_enabled"])
            save_settings(SETTINGS)
            st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Ajan kartları ızgarası
    grid = st.columns(2)
    for index, agent in enumerate(AGENTS):
        with grid[index % 2]:
            is_on = enabled.get(agent["id"], True)
            status = badge("AKTİF", "ok") if is_on else badge("PASİF", "muted", dot=False)
            st.markdown(
                f"""
                <div class="cd-agent">
                  <div class="cd-agent-head">
                    <div class="cd-agent-icon">{agent['icon']}</div>
                    <div>
                      <div class="cd-agent-name">{agent['name']}</div>
                      <div class="cd-agent-role">{agent['role']}</div>
                    </div>
                    <div style="margin-left:auto">{status}</div>
                  </div>
                  <div class="cd-agent-desc">{agent['desc']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.toggle("Ajanı çalıştır", value=is_on, key=f"tg_{agent['id']}"):
                if not enabled.get(agent["id"], True):
                    enabled[agent["id"]] = True
                    save_settings(SETTINGS)
                    log_activity(f"{agent['name']} ajanı etkinleştirildi", "ok")
                    st.rerun()
            elif enabled.get(agent["id"], False):
                enabled[agent["id"]] = False
                save_settings(SETTINGS)
                log_activity(f"{agent['name']} ajanı duraklatıldı", "warn")
                st.rerun()

            # Ajana özel hızlı işlemler
            detail = st.expander("Hızlı işlem")
            with detail:
                render_agent_action(agent)


def render_agent_action(agent: Dict[str, str]) -> None:
    agent_id = agent["id"]
    if agent_id == "strategy":
        st.caption("Kanal temasına uygun konu fikirleri:")
        ideas = [
            "Kediler neden gece daha iyi görür? — 60 saniyelik açıklama videosu",
            "Köpeklerin koku dünyası: 300 milyon koku reseptörü",
            "Kedi dilinin 10 gizli işareti — sahipleri şaşırtan liste videosu",
            "Sokak hayvanlarını koruma rehberi — duyarlılık belgeseli",
            "Evde kedi bakımı: yeni başlayanlar için 5 altın kural",
        ]
        for idea in ideas:
            st.markdown(f"- {idea}")
        if st.button("📋 Takvime Ekle (Panoya Kopyala)", key="strat_copy"):
            st.session_state["strategy_ideas"] = ideas
            st.success("Fikirler bu oturum için kaydedildi; Video Üretim sayfasında kullanabilirsiniz.")
    elif agent_id == "script":
        projects = [item["title"] for item in load_pipeline()]
        if projects:
            chosen = st.selectbox("Proje seçin", options=projects, key="scr_pick")
            sections = st.text_area("Bölüm planı (her satır bir bölüm)", height=110,
                                    placeholder="Giriş\nAna Bölüm 1\nAna Bölüm 2\nKapanış")
            if st.button("📝 Senaryo Taslağı Oluştur", key="scr_gen"):
                lines = [line.strip() for line in sections.splitlines() if line.strip()]
                if lines:
                    draft = []
                    for line in lines:
                        draft.append(f"## {line}\nBu bölümde {chosen} için '{line.lower()}' "
                                     "konusunu sade, anlatı tonunda ele alın. İzleyiciyi "
                                     "sürükleyen bir bilgi veya hikâye ile bitirin.\n")
                    st.session_state["script_draft"] = "\n".join(draft)
                    st.success("Taslak hazırlandı — aşağıda.")
                    st.text_area("Taslak", value=st.session_state.get("script_draft", ""), height=200,
                                 key="scr_out")
                else:
                    st.warning("En az bir bölüm satırı girin.")
        else:
            st.caption("Önce Video Üretim sayfasından bir proje oluşturun.")
    elif agent_id == "seo":
        topic = st.text_input("Konu", key="seo_topic", placeholder="Örn: kedi dili")
        if topic and st.button("🔍 SEO Paketi Oluştur", key="seo_gen"):
            core = topic.strip().lower()
            st.markdown("**Başlık önerileri**")
            for pattern in (f"{topic.strip().title()} Hakkında Bilmediğiniz 5 Şey",
                            f"{topic.strip().title()} — 60 Saniyede Açıklama",
                            f"Uzmanlar Açıkladı: {topic.strip().title()} Nasıl Anlaşılır?"):
                st.markdown(f"- {pattern}")
            st.markdown("**Etiketler**")
            st.code(", ".join([core, f"{core} nedir", f"{core} nasıl", "kedi", "köpek",
                               "hayvan belgeseli", "kısa belgesel", "youtube tr"]), language=None)
            st.markdown("**Açıklama taslağı**")
            st.code(f"{topic.strip().capitalize()} hakkında sade ve bilgilendirici bir belgesel.\n"
                    f"İçerik: {core} nedir, nasıl anlaşılır, dikkat edilmesi gerekenler.\n"
                    f"{SETTINGS.get('channel_name') or 'Cats & Dogs Documentary'} kanalından izleyin.",
                    language=None)
    elif agent_id == "thumbnail":
        st.caption("Kapak konsept kontrol listesi:")
        for tip in ("Yakın plan hayvan yüzü (duygusal ifadeli)", "Maksimum 3 kelime büyük başlık",
                    "Yüksek kontrast: sıcak arka plan + soğuk vurgu",
                    "Merkez kompozisyon; küçük ekranda test edin",
                    "Yüz + ok/daire ile ilgi noktası işaretleme"):
            st.markdown(f"- {tip}")
        if st.button("🎨 Konsept Notlarını Projeye Kaydet", key="thb_save"):
            project = next(iter(load_pipeline()), None)
            if project:
                items = load_pipeline()
                for updated in items:
                    if updated["id"] == project["id"]:
                        updated["notes"] = (updated.get("notes", "") +
                                            "\n[Kapak] " + "; ".join([
                                                "yakın plan yüz", "3 kelime başlık", "yüksek kontrast"])).strip()
                save_pipeline(items)
                st.success(f"'{project['title']}' proje notlarına eklendi.")
            else:
                st.warning("Proje bulunamadı.")
    elif agent_id == "production":
        st.caption("Üretim hattı, sağlayıcı seçimi ve render takibi Video Üretim sayfasında yönetilir.")
        if st.button("🎬 Video Üretim'e git", key="prd_go"):
            st.session_state["nav"] = "🎬 Video Üretim"
            st.rerun()
    elif agent_id == "publishing":
        freq = SETTINGS.get("posting_frequency", "Haftada 3")
        time_ = SETTINGS.get("preferred_post_time", "14:00")
        privacy = SETTINGS.get("default_privacy", "unlisted")
        st.markdown(
            f"""
            <div class="cd-panel" style="line-height:1.8">
              <span style="font-family:var(--mono); font-size:.7rem; color:var(--muted)">YAYIN ÇERÇEVESİ</span><br>
              Frekans: <b style="color:var(--text)">{freq}</b><br>
              Tercih edilen saat: <b style="color:var(--text)">{time_}</b><br>
              Varsayılan gizlilik: <b style="color:var(--text)">{privacy}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("⚙️ Yayın ayarlarını düzenle", key="pub_go"):
            st.session_state["nav"] = "🔧 Ayarlar"
            st.rerun()
    elif agent_id == "analytics":
        st.caption("Performans takibi ve geliştirme önerileri İstatistikler sayfasında.")
        if st.button("📈 İstatistiklere git", key="ana_go"):
            st.session_state["nav"] = "📈 İstatistikler"
            st.rerun()


# ============================================================================
# İstatistikler
# ============================================================================
def style_figure(fig: "go.Figure") -> "go.Figure":
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=THEME["t2"], size=12),
        title_font=dict(size=14, color=THEME["text"]),
        margin=dict(l=10, r=10, t=42, b=10),
        xaxis=dict(gridcolor=THEME["line"], zerolinecolor=THEME["line"]),
        yaxis=dict(gridcolor=THEME["line"], zerolinecolor=THEME["line"]),
        legend=dict(orientation="h", y=-0.2),
        height=320,
    )
    return fig


def render_stats() -> None:
    channel = active_channel()
    if not channel:
        st.markdown(
            """
            <div class="cd-hero">
              <h1>İstatistikler</h1>
              <p>Kanal verilerini göstermek için bağlantı gerekli. Sol panelden yetkilendirin.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="cd-hero">
          <h1>İstatistikler</h1>
          <p>{channel.get('title', 'Kanal')} performans panosu · veriler YouTube Analytics'ten alınır</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPI satırı
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("ABONE", fmt_int(channel.get("subscriber_count", 0)), "Canlı sayım", "accent"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("TOPLAM GÖRÜNTÜLENME", fmt_int(channel.get("view_count", 0)), "Kanal ömrü", "info"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("VİDEO", fmt_int(channel.get("video_count", 0)), "Yayında", "ok"),
                    unsafe_allow_html=True)
    with c4:
        views_total = int(channel.get("view_count", 0) or 0)
        video_total = int(channel.get("video_count", 0) or 0)
        avg = views_total // video_total if video_total else 0
        st.markdown(kpi_card("ORT. VİDEO İZLENME", fmt_int(avg), "video başına", "purple"),
                    unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Zaman aralığı
    range_choice = st.radio("Aralık", options=["Son 7 gün", "Son 30 gün", "Son 90 gün"],
                            horizontal=True, key="stat_range")
    days = {"Son 7 gün": 7, "Son 30 gün": 30, "Son 90 gün": 90}[range_choice]
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    chart_col, side_col = st.columns([7, 3])
    with chart_col:
        panel_open(f"GÜNLÜK GÖRÜNTÜLENME · {range_choice.upper()}")
        try:
            reporter = get_reporter()
            daily = reporter.get_daily_views(start_date=start_date, end_date=end_date)
            if daily:
                df = pd.DataFrame(daily)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df["views"], mode="lines+markers",
                    line=dict(color=THEME["accent"], width=2.5),
                    fill="tozeroy", fillcolor=THEME["soft"],
                    marker=dict(size=5),
                    name="Görüntülenme",
                ))
                fig.update_layout(title=None, height=300)
                st.plotly_chart(style_figure(fig), use_container_width=True)
                total = int(df["views"].sum())
                best = df.loc[df["views"].idxmax()]
                st.caption(f"Toplam: **{fmt_int(total)}** · En iyi gün: "
                           f"**{best['date']}** ({fmt_int(best['views'])})")
            else:
                st.info("Seçilen aralıkta görüntülenme verisi yok.")
        except Exception as exc:
            st.warning(f"Veri alınamadı: {str(exc)[:140]}")

    with side_col:
        panel_open("KOTA & DURUM")
        st.markdown(
            f"""
            <div class="cd-panel" style="line-height:1.9">
              {badge('Analytics erişimi', 'ok')}<br>
              {badge(f'Aralık: {days} gün', 'info', dot=False)}<br>
              {badge('Veri kaynağı: YouTube Data & Analytics API', 'muted', dot=False)}
            </div>
            """,
            unsafe_allow_html=True,
        )
        recent_days_note = ("Uzun aralıklarda raporlama birkaç saniye sürebilir."
                            if days > 30 else "Kısa aralık — hızlı rapor.")
        st.caption(recent_days_note)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # Video performans tablosu
    panel_open("VİDEO PERFORMANSI")
    try:
        reporter = get_reporter()
        videos = reporter.get_recent_videos(max_results=10)
        rows: List[Dict[str, Any]] = []
        if videos:
            for video in videos:
                stats: Dict[str, Any] = {}
                try:
                    stats = reporter.get_video_stats(video.get("video_id", "")) or {}
                except Exception:
                    stats = {}
                rows.append({
                    "Başlık": video.get("title", "—"),
                    "Yayın": str(video.get("published_at", ""))[:10],
                    "Görüntülenme": int(stats.get("views", 0) or 0),
                    "Beğeni": int(stats.get("likes", 0) or 0),
                    "Yorum": int(stats.get("comments", 0) or 0),
                    "Video ID": video.get("video_id", ""),
                })
        if rows:
            dfv = pd.DataFrame(rows)
            dfv = dfv.sort_values("Görüntülenme", ascending=False)
            st.dataframe(
                dfv,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Görüntülenme": st.column_config.NumberColumn(format="%d"),
                    "Beğeni": st.column_config.NumberColumn(format="%d"),
                    "Yorum": st.column_config.NumberColumn(format="%d"),
                },
            )

            # En iyi 6 video grafiği
            top = dfv.head(6).iloc[::-1]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=[t[:46] + ("…" if len(t) > 46 else "") for t in top["Başlık"]],
                x=top["Görüntülenme"],
                orientation="h",
                marker=dict(color=THEME["accent"]),
                name="Görüntülenme",
            ))
            fig2.update_layout(height=320, title=None, yaxis=dict(automargin=True))
            st.plotly_chart(style_figure(fig2), use_container_width=True)

            # Etkileşim oranı özeti
            total_views = dfv["Görüntülenme"].sum()
            total_likes = dfv["Beğeni"].sum()
            total_comments = dfv["Yorum"].sum()
            rate = ((total_likes + total_comments) / total_views * 100) if total_views else 0
            e1, e2, e3 = st.columns(3)
            with e1:
                st.markdown(kpi_card("ETKİLEŞİM ORANI", f"%{rate:.1f}", "(beğeni+yorum)/izlenme", "ok"),
                            unsafe_allow_html=True)
            with e2:
                st.markdown(kpi_card("TOPLAM BEĞENİ", fmt_int(total_likes), "son 12 video", "info"),
                            unsafe_allow_html=True)
            with e3:
                st.markdown(kpi_card("TOPLAM YORUM", fmt_int(total_comments), "son 12 video", "purple"),
                            unsafe_allow_html=True)
        else:
            st.info("Henüz video verisi yok.")
    except Exception as exc:
        st.warning(f"Video listesi alınamadı: {str(exc)[:140]}")


# ============================================================================
# Otomasyon
# ============================================================================
def render_automation() -> None:
    st.markdown(
        """
        <div class="cd-hero">
          <h1>Otomasyon</h1>
          <p>Planla → Uygula → İzle → Geliştir döngüsü. Ayarları belirleyin, hattı ilerletin,
          kayıtları izleyin ve önerilere göre yayınınızı geliştirin.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    enabled = SETTINGS.get("agents_enabled", {})
    pipeline_items = load_pipeline()
    active_count = sum(1 for agent in AGENTS if enabled.get(agent["id"], True))
    pending_count = sum(1 for item in pipeline_items if item["stage_index"] < len(PIPELINE_STAGES))

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.markdown(kpi_card("AKTİF AJAN", f"{active_count}/{len(AGENTS)}", "otomasyon gücü", "info"),
                    unsafe_allow_html=True)
    with d2:
        st.markdown(kpi_card("HATTA PROJE", str(pending_count), f"{len(pipeline_items)} toplam", "accent"),
                    unsafe_allow_html=True)
    with d3:
        st.markdown(kpi_card("YAYIN RİTMİ", SETTINGS.get("posting_frequency", "Haftada 3"),
                             f"saat {SETTINGS.get('preferred_post_time', '14:00')}", "purple"),
                    unsafe_allow_html=True)
    with d4:
        auto_state = "Açık" if SETTINGS.get("auto_upload") else "Kapalı"
        st.markdown(kpi_card("OTO YÜKLEME", auto_state,
                             f"günde ≤ {SETTINGS.get('max_daily', 5)} video", "ok" if SETTINGS.get("auto_upload") else "warn"),
                    unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # --- 1) PLANLAMA ---
    panel_open("1 · PLANLAMA")
    plan_col, auto_col = st.columns(2)
    with plan_col:
        freq = st.selectbox("Yayın frekansı",
                            options=["Günde 1", "Günde 2", "Haftada 3", "Haftada 5", "Haftada 7"],
                            index=["Günde 1", "Günde 2", "Haftada 3", "Haftada 5", "Haftada 7"].index(
                                SETTINGS.get("posting_frequency", "Haftada 3"))
                            if SETTINGS.get("posting_frequency") in
                            ("Günde 1", "Günde 2", "Haftada 3", "Haftada 5", "Haftada 7") else 2)
        post_time = st.time_input("Tercih edilen yayın saati", value=None, key="plan_time")
        max_daily = st.number_input("Günlük maksimum video", min_value=1, max_value=20,
                                    value=int(SETTINGS.get("max_daily", 5)))
    with auto_col:
        auto_upload = st.toggle("Üretim bitince YouTube'a otomatik yükle (varsayılan gizli)",
                                value=bool(SETTINGS.get("auto_upload", False)))
        auto_schedule = st.toggle("Yeni projeleri yayın takvimine otomatik ekle",
                                  value=bool(SETTINGS.get("auto_schedule", False)))
        if st.button("💾 Planlama Ayarlarını Kaydet", type="primary", use_container_width=True):
            SETTINGS["posting_frequency"] = freq
            SETTINGS["max_daily"] = int(max_daily)
            SETTINGS["auto_upload"] = bool(auto_upload)
            SETTINGS["auto_schedule"] = bool(auto_schedule)
            if post_time:
                SETTINGS["preferred_post_time"] = post_time.strftime("%H:%M")
            save_settings(SETTINGS)
            log_activity("Planlama ayarları güncellendi", "ok")
            st.success("Kaydedildi.")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # --- 2) UYGULAMA ---
    panel_open("2 · UYGULAMA — ÜRETİM HATTI")
    if pipeline_items:
        queue_rows = []
        for item in pipeline_items:
            stage_name = PIPELINE_STAGES[min(item["stage_index"], len(PIPELINE_STAGES) - 1)]["name"]
            done = item["stage_index"] >= len(PIPELINE_STAGES)
            queue_rows.append({"Proje": item["title"],
                               "Aşama": "Yayında" if done else stage_name,
                               "Durum": "Tamamlandı" if done else "Sürüyor",
                               "ID": item["id"]})
        st.dataframe(pd.DataFrame(queue_rows)[["Proje", "Aşama", "Durum"]],
                     hide_index=True, use_container_width=True)
        act_left, act_mid, act_right = st.columns(3)
        with act_left:
            if st.button("⏭️ Bekleyen Tümünü İlerlet", type="primary", use_container_width=True):
                for item in [x for x in pipeline_items if x["stage_index"] < len(PIPELINE_STAGES)]:
                    advance_project(item["id"])
                st.rerun()
        with act_mid:
            if st.button("🔄 Paneli Yenile", use_container_width=True):
                st.rerun()
        with act_right:
            if st.button("📅 Bugünün Planını Göster", use_container_width=True):
                freq_label = SETTINGS.get("posting_frequency", "Haftada 3")
                st.info(f"Bugün plana göre {freq_label} ritmiyle "
                        f"{SETTINGS.get('preferred_post_time', '14:00')} civarı yayın hedefleniyor.")
    else:
        st.markdown('<div class="cd-panel" style="color:var(--muted)">Uygulanacak proje yok. '
                    '<b>🎬 Video Üretim</b> sayfasından proje başlatın.</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # --- 3) İZLEME ---
    mon_col, dev_col = st.columns([1, 1])
    with mon_col:
        panel_open("3 · İZLEME — ETKİNLİK KAYDI")
        activity: List[Dict[str, Any]] = []
        if ACTIVITY_FILE.exists():
            try:
                activity = json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                activity = []
        if activity:
            for entry in activity[:15]:
                kind = entry.get("kind", "info")
                cls_map = {"ok": "cd-log cd-log-ok", "hata": "cd-log cd-log-err", "warn": "cd-log cd-log-warn"}
                cls = cls_map.get(kind, "cd-log")
                st.markdown(f'<div class="{cls}"><span class="cd-log-ts">{entry.get("ts", "")}</span>'
                            f'{entry.get("msg", "")}</div>', unsafe_allow_html=True)
            if st.button("🗑️ Kayıtları Temizle", key="clear_logs"):
                try:
                    ACTIVITY_FILE.unlink()
                except OSError:
                    pass
                st.rerun()
        else:
            st.caption("Kayıt yok.")

    # --- 4) GELİŞTİRME ---
    with dev_col:
        panel_open("4 · GELİŞTİRME — ÖNERİLER")
        suggestions: List[str] = []
        if SETTINGS.get("posting_frequency") == "Haftada 3":
            suggestions.append("Frekansı Haftada 5'e çıkarmak büyümeyi hızlandırabilir; kapasiteniz varsa deneyin.")
        if pending_count > 5:
            suggestions.append(f"Hatta {pending_count} proje bekliyor — Üretim aşamasındaki darboğazı kontrol edin.")
        if not SETTINGS.get("auto_schedule", False):
            suggestions.append("Otomatik takvim eklemeyi açın; yayın ritmi tutarlı olur, algoritma favori görür.")
        try:
            reporter = get_reporter()
            daily = reporter.get_daily_views(start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                                             end_date=datetime.now().strftime("%Y-%m-%d"))
            if daily:
                totals = [int(d["views"]) for d in daily]
                if totals and max(totals) > 0 and (sum(totals) / 7) < (max(totals) / 2):
                    suggestions.append("Son 7 günde tek bir gün zirve yaptı — o günün içeriğini çoğaltın.")
                elif totals and sum(totals) == 0:
                    suggestions.append("7 günde görüntülenme yok — yeni içerik üretin ve eski videoları gizlilikten çıkarın.")
        except Exception:
            pass
        if not suggestions:
            suggestions = ["Her şey yolunda görünüyor — içerik ritmini koruyun."]
        for suggestion in suggestions:
            st.markdown(f"""<div class="cd-log"><span class="cd-log-ts">💡</span>{suggestion}</div>""",
                        unsafe_allow_html=True)


# ============================================================================
# Ayarlar
# ============================================================================
def render_settings() -> None:
    st.markdown(
        """
        <div class="cd-hero">
          <h1>Ayarlar</h1>
          <p>Sadece düzenlenebilir ayarlar görüntülenir — kod görünmez, hiçbir şey kırılmaz.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Görünüm
    panel_open("GÖRÜNÜM")
    theme_keys = list(THEMES.keys())
    theme_labels = [THEMES[key]["label"] for key in theme_keys]
    chosen = st.selectbox("Tema", options=theme_keys,
                          index=theme_keys.index(SETTINGS.get("theme", "standart"))
                          if SETTINGS.get("theme") in theme_keys else 0,
                          format_func=lambda key: THEMES[key]["label"])
    if chosen != SETTINGS.get("theme"):
        SETTINGS["theme"] = chosen
        save_settings(SETTINGS)
        st.rerun()
    st.caption("Standart tema: 🎛️ Kontrol Odası — koyu, editoryal, tek vurgu rengi.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Kanal varsayılanları
    panel_open("KANAL VARSAYILANLARI")
    ch_col, cat_col = st.columns(2)
    with ch_col:
        channel_name = st.text_input("Kanal adı", value=SETTINGS.get("channel_name", ""))
        channel_desc = st.text_area("Kanal açıklaması", value=SETTINGS.get("channel_desc", ""), height=100)
    with cat_col:
        categories = {
            "15": "Hayvanlar", "22": "Kişiler ve Bloglar", "23": "Komedi", "24": "Eğlence",
            "25": "Haberler ve Politika", "26": "Nasıl Yapılır ve Stil", "27": "Eğitim",
            "28": "Bilim ve Teknoloji",
        }
        cat_id = st.selectbox("Varsayılan kategori", options=list(categories.keys()),
                              index=list(categories.keys()).index(SETTINGS.get("category_id", "15"))
                              if SETTINGS.get("category_id") in categories else 0,
                              format_func=lambda cid: categories[cid])
        privacy_options = ["private", "unlisted", "public"]
        privacy = st.selectbox("Varsayılan gizlilik",
                               options=privacy_options,
                               index=privacy_options.index(SETTINGS.get("default_privacy", "unlisted"))
                               if SETTINGS.get("default_privacy") in privacy_options else 1,
                               help="'Public' seçilirse YouTube'a açılırken ek onay adımı istenir.")
    if st.button("💾 Kanal Ayarlarını Kaydet", type="primary"):
        SETTINGS["channel_name"] = channel_name.strip()
        SETTINGS["channel_desc"] = channel_desc.strip()
        SETTINGS["category_id"] = cat_id
        SETTINGS["default_privacy"] = privacy
        save_settings(SETTINGS)
        log_activity("Kanal ayarları güncellendi", "ok")
        st.success("Kanal ayarları kaydedildi.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Video üretim varsayılanları
    panel_open("VİDEO ÜRETİM VARSAYILANLARI")
    providers = available_providers()
    prov_col, fmt_col = st.columns(2)
    with prov_col:
        default_provider = st.selectbox("Varsayılan sağlayıcı",
                                        options=[provider["id"] for provider in providers],
                                        index=[provider["id"] for provider in providers].index(
                                            SETTINGS.get("default_provider", "slideshow"))
                                        if SETTINGS.get("default_provider") in
                                        [provider["id"] for provider in providers] else 0,
                                        format_func=lambda pid: next(
                                            (provider["name"] for provider in providers if provider["id"] == pid), pid))
    with fmt_col:
        duration = st.number_input("Varsayılan süre (sn)", min_value=10, max_value=3600,
                                   value=int(SETTINGS.get("video_duration", 60)), step=10)
        aspect = st.selectbox("Varsayılan en-boy oranı",
                              options=["16:9", "9:16", "1:1"],
                              index=["16:9", "9:16", "1:1"].index(SETTINGS.get("aspect_ratio", "16:9"))
                              if SETTINGS.get("aspect_ratio") in ("16:9", "9:16", "1:1") else 0)
    if st.button("💾 Üretim Ayarlarını Kaydet"):
        SETTINGS["default_provider"] = default_provider
        SETTINGS["video_duration"] = int(duration)
        SETTINGS["aspect_ratio"] = aspect
        save_settings(SETTINGS)
        log_activity("Video üretim ayarları güncellendi", "ok")
        st.success("Üretim ayarları kaydedildi.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # API anahtar durumları (değerler ASLA gösterilmez)
    panel_open("API ANAHTAR DURUMU")
    key_status = [
        ("Viewmade", "VIEWMADE_API_KEY"),
        ("NVIDIA / MiniMax", "NVIDIA_API_KEY"),
        ("Kling AI", "KLING_ACCESS_KEY"),
        ("OpenAI", "OPENAI_API_KEY"),
        ("Gemini", "GEMINI_API_KEY"),
    ]
    chips = " ".join(
        badge(name, "ok" if os.environ.get(env_key) else "muted", dot=os.environ.get(env_key))
        for name, env_key in key_status
    )
    st.markdown(chips, unsafe_allow_html=True)
    st.caption("🟢 Yeşil: anahtar yapılandırılmış · ⚫ Gri: anahtar yok. Anahtarlar .env dosyasından okunur ve panelde "
               "asla gösterilmez. Anahtar eklemek için destek dokümanınızdaki talimatı kullanın.")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Sistem
    panel_open("SİSTEM")
    sys_col, danger_col = st.columns(2)
    with sys_col:
        manager = get_token_manager()
        if manager.is_valid():
            st.markdown(badge("OAuth token geçerli", "ok"), unsafe_allow_html=True)
            creds = manager.get_credentials()
            if creds and getattr(creds, "expiry", None):
                try:
                    st.caption(f"Sonraki yenileme: {creds.expiry.strftime('%d.%m.%Y %H:%M')}")
                except Exception:
                    pass
        else:
            st.markdown(badge("Token yok — sol panelden yetkilendirin", "err"), unsafe_allow_html=True)
        outputs_dir = ROOT / "outputs"
        size_mb = 0.0
        if outputs_dir.exists():
            size_mb = sum(f.stat().st_size for f in outputs_dir.glob("*.mp4")) / 1_048_576
        st.caption(f"Üretilmiş videolar: {len(list(outputs_dir.glob('*.mp4'))) if outputs_dir.exists() else 0} adet "
                   f"· {size_mb:.1f} MB")
    with danger_col:
        st.markdown(badge("Dikkatli kullanın", "warn"), unsafe_allow_html=True)
        clear_col_1, clear_col_2 = st.columns(2)
        with clear_col_1:
            if st.button("🧹 Üretim Hattını Sıfırla", use_container_width=True):
                save_pipeline([])
                log_activity("Üretim hattı sıfırlandı", "warn")
                st.rerun()
        with clear_col_2:
            if st.button("🧹 Etkinlik Kayıtlarını Sil", use_container_width=True):
                try:
                    ACTIVITY_FILE.unlink()
                except OSError:
                    pass
                st.rerun()
        if st.button("♻️ Tüm Panel Ayarlarını Sıfırla", use_container_width=True):
            save_settings(dict(DEFAULT_SETTINGS))
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()


# ============================================================================
# Yönlendirici + Alt Bilgi
# ============================================================================
ROUTES = {
    "🎛️ Genel Bakış": render_overview,
    "🎬 Video Üretim": render_production,
    "🤖 Ajanlar": render_agents,
    "📈 İstatistikler": render_stats,
    "⚙️ Otomasyon": render_automation,
    "🔧 Ayarlar": render_settings,
}

ROUTES.get(st.session_state.get("nav", "🎛️ Genel Bakış"), render_overview)()

st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div style="border-top:1px solid var(--line); padding-top:16px; display:flex;
                justify-content:space-between; font-family:var(--mono); font-size:.7rem;
                color:var(--muted); letter-spacing:.06em">
      <span>YOUTUBE OTOMASYON STÜDYOSU · v2.2</span>
      <span>OAUTH 2.0 · YOUTUBE DATA & ANALYTICS API</span>
    </div>
    """,
    unsafe_allow_html=True,
)
