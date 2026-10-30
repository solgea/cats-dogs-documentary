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
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "cddocs"))

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
ROOT = Path(__file__).parent
SETTINGS_FILE = ROOT / "panel_settings.json"
PIPELINE_FILE = ROOT / "production_pipeline.json"
ACTIVITY_FILE = ROOT / "activity_log.json"

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


def add_project(title: str, topic: str, provider: str) -> Dict[str, Any]:
    project = {
        "id": f"PRJ-{int(time.time())}",
        "title": title,
        "topic": topic,
        "provider": provider,
        "stage_index": 0,
        "script": "",
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

    nav = st.radio(
        "Menü",
        options=[
            "🎛️ Genel Bakış",
            "🎬 Video Üretim",
            "🤖 Ajanlar",
            "📈 İstatistikler",
            "⚙️ Otomasyon",
            "🔧 Ayarlar",
        ],
        label_visibility="collapsed",
        key="nav",
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

    # Sistem durumu
    manager = get_token_manager()
    token_ok = manager.is_valid()
    if token_ok:
        st.markdown(badge("Sistem Çevrimiçi", "ok"), unsafe_allow_html=True)
    else:
        st.markdown(badge("Bağlantı Gerekli", "err"), unsafe_allow_html=True)
        if st.button("🔑 Yetkilendir (OAuth)", use_container_width=True, type="primary"):
            try:
                oauth = OAuthFlowManager(get_config())
                result = oauth.run_local_server(port=8503)
                if result:
                    access_token, refresh_token = result
                    if manager.set_credentials_from_oauth(access_token, refresh_token):
                        log_activity("OAuth yetkilendirmesi tamamlandı", "ok")
                        st.cache_data.clear()
                        st.rerun()
            except Exception as exc:
                st.error(f"Yetkilendirme hatası: {str(exc)[:160]}")

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

    providers = available_providers()
    provider_names = {provider["id"]: provider["name"] for provider in providers}
    provider_avail = {provider["id"]: provider.get("available", False) for provider in providers}

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
    pipeline_items = load_pipeline()
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
                st.video(output_path)
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

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # Üretilmiş videolar galerisi
    outputs_dir = ROOT / "outputs"
    if outputs_dir.exists():
        videos = sorted(outputs_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if videos:
            panel_open("ÜRETİLEN VİDEOLAR")
            grid = st.columns(3)
            for index, video_path in enumerate(videos[:9]):
                with grid[index % 3]:
                    st.video(str(video_path))
                    st.caption(f"{video_path.name} · {video_path.stat().st_size / 1_048_576:.1f} MB")


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
