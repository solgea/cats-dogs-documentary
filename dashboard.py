#!/usr/bin/env python
"""YouTube Profesyonel Yönetim Paneli - Streamlit Tabanlı.

Mimari:
- config.py: Merkezi yapılandırma (ortam değişkenleri)
- token_manager.py: Güvenli OAuth token yönetimi (0o600 dosya izni)
- api_client.py: YouTube Data API v3 istemcisi (retry, quota, validation)
- upload.py: Güvenli upload yöneticisi (confirm_public koruması, duplicate önleme)
- analytics.py: Seçili kanal desteğiyle analitik raporlama
- oauth_flow.py: OAuth 2.0 yetkilendirme akışı
- async_upload.py: Async wrapperlar
- rate_limiter.py: Token bucket ve quota rate limiting
"""

import sys
import os
import json
import csv
import io
from datetime import datetime, timedelta
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "cddocs"))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from youtube.config import YouTubeConfig
from youtube.token_manager import TokenManager
from youtube.api_client import YouTubeAPIClient
from youtube.upload import UploadManager
from youtube.analytics import AnalyticsReporter
from youtube.oauth_flow import OAuthFlowManager

# ============================================================================
# Dil ve Tema Ayarları (Session State)
# ============================================================================
if "lang" not in st.session_state:
    st.session_state["lang"] = "tr"
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Dashboard"

LANG = st.session_state["lang"]
DARK = st.session_state["dark_mode"]

TR = {
    "app_title": "📊 YouTube Profesyonel Yönetim Paneli",
    "app_subtitle": "YouTube Analitik & Kanal Yönetimi",
    "settings": "⚙️ Ayarlar & Kanal Seçimi",
    "token_valid": "✅ Token geçerli",
    "token_invalid": "⚠️ Token geçersiz veya yok",
    "reauthorize": "Yeniden Yetkilendir (OAuth)",
    "auth_success": "✅ Yeni token alındı!",
    "auth_fail": "❌ Yetkilendirme başarısız",
    "current_channel": "Mevcut Kanal:",
    "refresh_channels": "🔄 Kanalları Yenile ve Seç",
    "channel_select": "Kanal Seçiniz:",
    "channel_set": "✅ Kanal '{}' olarak ayarlandı!",
    "active_channel": "**Aktif Kanal:** {}",
    "subscribers": "👥 Abone: {}",
    "views": "👁️ Görüntüleme: {}",
    "videos": "📹 Video: {}",
    "reset_channel": "🔄 Varsayılan Kanaalı Sıfırla",
    "reset_done": "✅ Varsayılan kanaal ayarlandı!",
    "channel_load_fail": "Kanalları yükleyemedi! Token'ı kontrol edin.",
    "dashboard": "📊 Dashboard",
    "video_mgmt": "📹 Video Yönetimi",
    "upload_history": "📜 Yükleme Geçmişi",
    "analytics": "📈 Analitik",
    "settings_tab": "🔧 Ayarlar",
    "main_stats": "📈 Ana İstatistikler",
    "subs_count": "👥 Abone Sayısı",
    "views_count": "👁️ Görüntülenme Sayısı",
    "video_count": "📹 Video Sayısı",
    "perf_charts": "📊 Performans Grafikleri",
    "subs_goal": "Abone vs. 1 Milyon Hedef",
    "daily_views": "Son 7 Gün - Günlük Görüntüleme",
    "no_analytics": "Analiz verisi bulunamadı.",
    "recent_videos": "📺 Son Aktivite",
    "no_videos": "Henüz video bulunamadı.",
    "video_list_fail": "Video listesi alınamadı: {}",
    "upload_video": "📤 Video Yükle",
    "video_path": "Video Dosya Yolu",
    "path_placeholder": "örn: videos/ornek.mp4",
    "file_preview": "📁 Dosya Ön İzleme",
    "file_name": "📁 Dosya Adı: {}",
    "file_size": "💾 Boyut: {:.2f} MB",
    "est_duration": "⏱️ Tahmini Süre: {} dakika",
    "duplicate_warn": "⚠️ Bu dosya daha önce yüklendi (Video ID: {}). ",
    "duplicate_allow": "Yine de yüklemek için 'Yinelenene İzin Ver' işaretleyin.",
    "file_not_found": "❌ Dosya bulunamadı: {}",
    "upload_form": "Yükleme Formu",
    "video_title": "Video Başlığı",
    "title_placeholder": "Video başlığını girin",
    "description": "Açıklama",
    "desc_placeholder": "Video açıklaması",
    "tags": "Etiketler (virgülle ayrılmış)",
    "tags_placeholder": "kedi,köpek,test",
    "privacy": "Gizlilik Durumu",
    "privacy_help": "Varsayılan 'unlisted'. 'Public' yapmak için onay gereklidir.",
    "confirm_public": "Kamuya açmayı onaylıyorum",
    "allow_dup": "Yinelenen dosyaya izin ver",
    "allow_dup_help": "Aynı dosya daha önce yüklendiyse bu işaretlemesi gerekir.",
    "btn_upload": "📤 Yükle",
    "upload_success": "✅ Video başarıyla yüklendi!",
    "video_id": "📹 Video ID: {}",
    "video_url": "🔗 URL: {}",
    "privacy_status": "🔒 Gizlilik: {}",
    "upload_fail": "❌ Yükleme hatası: {}",
    "val_fail": "❌ Doğrulama hatası: {}",
    "change_privacy": "🔒 Video Gizliliği Değiştir",
    "vid_id": "Video ID",
    "vid_id_placeholder": "Değiştirilecek video ID'si",
    "new_privacy": "Yeni Gizlilik",
    "confirm_privacy": "Kamuya açmayı onaylıyorum",
    "btn_change": "🔒 Değiştir",
    "enter_vid": "❌ Lütfen Video ID'si girin.",
    "privacy_changed": "✅ Video {} gizliliği '{}' olarak değiştirildi.",
    "analytics_title": "📊 Analitik Raporu",
    "start_date": "Başlangıç Tarihi",
    "end_date": "Bitiş Tarihi",
    "btn_get_analytics": "📊 Analitik Verileri Getir",
    "analytics_success": "✅ Analitik veriler alındı!",
    "total_views": "Toplam Görüntüleme",
    "no_data": "Belirtilen tarih aralığında veri bulunamadı.",
    "analytics_fail": "❌ Analitik hatası: {}",
    "footer": "YouTube Profesyonel Yönetim Paneli | Versiyon 2.1",
    "footer_date": "Geliştirilme tarihi: {}",
    "footer_auth": "Google API Entegrasyonu & OAuth 2.0 Kimlik Doğrulama",
    "lang_tr": "Türkçe",
    "lang_en": "English",
    "theme_dark": "🌙 Karanlık Mod",
    "theme_light": "☀️ Aydınlık Mod",
    "quota": "📊 Kota Kullanımı",
    "quota_used": "Kullanılan: {}",
    "quota_limit": "Limit: {}",
    "quota_remaining": "Kalan: {}",
    "token_expiry": "🔑 Token Süresi: {}",
    "upload_history_title": "📜 Yükleme Geçmişi",
    "no_uploads": "Henüz yükleme geçmişi yok.",
    "file": "Dosya",
    "video_id_col": "Video ID",
    "uploaded_at": "Yüklenme Tarihi",
    "privacy": "Gizlilik",
    "export_csv": "📥 CSV Olarak Dışa Aktar",
    "export_json": "📥 JSON Olarak Dışa Aktar",
    "clear_history": "🗑️ Geçmişi Temizle",
    "video_mgmt_title": "📹 Video Yönetimi",
    "recent_title": "Son Yüklenen Videolar",
    "video_details": "📋 Video Ayrıntıları",
    "views": "Görüntülemeler",
    "likes": "Beğeniler",
    "comments": "Yorumlar",
    "duration": "Süre",
}

EN = {
    "app_title": "📊 YouTube Professional Management Panel",
    "app_subtitle": "YouTube Analytics & Channel Management",
    "settings": "⚙️ Settings & Channel Selection",
    "token_valid": "✅ Token valid",
    "token_invalid": "⚠️ Token invalid or missing",
    "reauthorize": "Re-authorize (OAuth)",
    "auth_success": "✅ New token acquired!",
    "auth_fail": "❌ Authorization failed",
    "current_channel": "Current Channel:",
    "refresh_channels": "🔄 Refresh and Select Channels",
    "channel_select": "Select Channel:",
    "channel_set": "✅ Channel set to '{}'!",
    "active_channel": "**Active Channel:** {}",
    "subscribers": "👥 Subscribers: {}",
    "views": "👁️ Views: {}",
    "videos": "📹 Videos: {}",
    "reset_channel": "🔄 Reset to Default Channel",
    "reset_done": "✅ Default channel set!",
    "channel_load_fail": "Failed to load channels! Check your token.",
    "dashboard": "📊 Dashboard",
    "video_mgmt": "📹 Video Management",
    "upload_history": "📜 Upload History",
    "analytics": "📈 Analytics",
    "settings_tab": "🔧 Settings",
    "main_stats": "📈 Main Statistics",
    "subs_count": "👥 Subscriber Count",
    "views_count": "👁️ View Count",
    "video_count": "📹 Video Count",
    "perf_charts": "📊 Performance Charts",
    "subs_goal": "Subscribers vs. 1 Million Goal",
    "daily_views": "Last 7 Days - Daily Views",
    "no_analytics": "No analytics data found.",
    "recent_videos": "📺 Recent Activity",
    "no_videos": "No videos found yet.",
    "video_list_fail": "Failed to load video list: {}",
    "upload_video": "📤 Upload Video",
    "video_path": "Video File Path",
    "path_placeholder": "e.g. videos/example.mp4",
    "file_preview": "📁 File Preview",
    "file_name": "📁 File Name: {}",
    "file_size": "💾 Size: {:.2f} MB",
    "est_duration": "⏱️ Est. Duration: {} minutes",
    "duplicate_warn": "⚠️ This file was already uploaded (Video ID: {}). ",
    "duplicate_allow": "Check 'Allow Duplicate' to upload anyway.",
    "file_not_found": "❌ File not found: {}",
    "upload_form": "Upload Form",
    "video_title": "Video Title",
    "title_placeholder": "Enter video title",
    "description": "Description",
    "desc_placeholder": "Enter video description",
    "tags": "Tags (comma separated)",
    "tags_placeholder": "cat,dog,test",
    "privacy": "Privacy Status",
    "privacy_help": "Default 'unlisted'. 'Public' requires confirmation.",
    "confirm_public": "Confirm public release",
    "allow_dup": "Allow duplicate file",
    "allow_dup_help": "Check this if the same file was uploaded before.",
    "btn_upload": "📤 Upload",
    "upload_success": "✅ Video uploaded successfully!",
    "video_id": "📹 Video ID: {}",
    "video_url": "🔗 URL: {}",
    "privacy_status": "🔒 Privacy: {}",
    "upload_fail": "❌ Upload error: {}",
    "val_fail": "❌ Validation error: {}",
    "change_privacy": "🔒 Change Video Privacy",
    "vid_id": "Video ID",
    "vid_id_placeholder": "Enter video ID to change",
    "new_privacy": "New Privacy",
    "confirm_privacy": "Confirm public release",
    "btn_change": "🔒 Change",
    "enter_vid": "❌ Please enter a Video ID.",
    "privacy_changed": "✅ Video {} privacy changed to '{}'.",
    "analytics_title": "📊 Analytics Report",
    "start_date": "Start Date",
    "end_date": "End Date",
    "btn_get_analytics": "📊 Get Analytics Data",
    "analytics_success": "✅ Analytics data retrieved!",
    "total_views": "Total Views",
    "no_data": "No data found for the specified date range.",
    "analytics_fail": "❌ Analytics error: {}",
    "footer": "YouTube Professional Management Panel | Version 2.1",
    "footer_date": "Development date: {}",
    "footer_auth": "Google API Integration & OAuth 2.0 Authentication",
    "lang_tr": "Türkçe",
    "lang_en": "English",
    "theme_dark": "🌙 Dark Mode",
    "theme_light": "☀️ Light Mode",
    "quota": "📊 Quota Usage",
    "quota_used": "Used: {}",
    "quota_limit": "Limit: {}",
    "quota_remaining": "Remaining: {}",
    "token_expiry": "🔑 Token Expiry: {}",
    "upload_history_title": "📜 Upload History",
    "no_uploads": "No upload history yet.",
    "file": "File",
    "video_id_col": "Video ID",
    "uploaded_at": "Upload Date",
    "privacy": "Privacy",
    "export_csv": "📥 Export as CSV",
    "export_json": "📥 Export as JSON",
    "clear_history": "🗑️ Clear History",
    "video_mgmt_title": "📹 Video Management",
    "recent_title": "Recently Uploaded Videos",
    "video_details": "📋 Video Details",
    "views": "Views",
    "likes": "Likes",
    "comments": "Comments",
    "duration": "Duration",
}

T = TR if LANG == "tr" else EN

# ============================================================================
# CSS Stilizasyonu (Türkçe / İngilizce + Dark Mode)
# ============================================================================
bg_color = "#0e1117" if DARK else "#ffffff"
text_color = "#ffffff" if DARK else "#000000"
card_bg = "#262730" if DARK else "#ffffff"

st.markdown(
    f"""
    <style>
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
        background-color: {bg_color};
        color: {text_color};
    }}
    .metric-card {{
        background: {card_bg};
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        color: {text_color};
    }}
    h1, h2, h3 {{
        color: #ff0000;
    }}
    .stButton > button {{
        width: 100%;
        margin-top: 0.5rem;
    }}
    .warning-box {{
        background: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }}
    .success-box {{
        background: #d4edda;
        border: 1px solid #28a745;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }}
    .stSelectbox > div > div > div {{
        background-color: {card_bg};
        color: {text_color};
    }}
    .stTextInput > div > div > input {{
        background-color: {card_bg};
        color: {text_color};
    }}
    .stTextArea > div > div > textarea {{
        background-color: {card_bg};
        color: {text_color};
    }}
    .stDataFrame {{}}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# Başlık
# ============================================================================
st.title(T["app_title"])
st.markdown(f"**{T['app_subtitle']}**")
st.markdown("---")

# ============================================================================
# Yapılandırma ve Token Yöneticisi
# ============================================================================
config = YouTubeConfig()
config_errors = config.validate()

if config_errors:
    st.error("⚠️ Yapılandırma hataları:")
    for err in config_errors:
        st.error(f"• {err}")
    st.markdown("---")
    st.markdown("### 🔧 Çözüm Adımları:")
    st.markdown("""
    1. **`.env` dosyasını açın** (`C:\\Users\\trycahce\\Desktop\\Proje\\cats-dogs-documentary\\.env`)
    2. **Aşağıdaki değerleri Google Cloud Console'dan kopyalayın:**
       - `YOUTUBE_CLIENT_ID` = OAuth 2.0 Client ID
       - `YOUTUBE_CLIENT_SECRET` = OAuth 2.0 Client Secret
    3. **Dosyayı kaydedin** ve dashboard'ı yeniden başlatın.
    4. **Google Cloud Console'da** Authorized redirect URI olarak `http://localhost:8502` ekleyin.
    """)
    st.info("📁 `.env` dosya yolu: `C:\\Users\\trycahce\\Desktop\\Proje\\cats-dogs-documentary\\.env`")
    st.stop()

# OAuth flow manager (yeniden yetkilendirme için)
oauth_manager = OAuthFlowManager(config)

token_manager = TokenManager(config=config)
token_manager.load_credentials()

# Token durumu kontrolü ve iyileştirilmiş hata mesajı
if not token_manager.is_valid():
    st.warning("⚠️ Token geçersiz veya yok")
    st.markdown("### 🔑 Token Gereklidir")
    st.markdown("""
    YouTube API'ye erişmek için geçerli bir OAuth token gereklidir.
    
    **Adımlar:**
    1. Sol panelde **"Yeniden Yetkilendir (OAuth)"** butonuna tıklayın
    2. Google hesabınızla giriş yapın ve onay verin
    3. Token otomatik olarak `youtube_token.json` dosyasına kaydedilecektir
    4. Dashboard otomatik olarak yenilenecektir
    """)
    if st.sidebar.button("🔑 Token Oluştur (OAuth)", key="create_token_btn", use_container_width=True):
        result = oauth_manager.run_local_server(port=8503)
        if result:
            st.success("✅ Yeni token alındı!")
            st.rerun()
        else:
            st.error("❌ Yetkilendirme başarısız!")
else:
    creds = token_manager.get_credentials()
    if creds and creds.expiry:
        expiry_str = creds.expiry.strftime("%d.%m.%Y %H:%M")
        st.sidebar.info(f"{T['token_expiry'].format(expiry_str)}")


# ============================================================================
# Sidebar: Dil, Tema, Kanal Seçimi ve Ayarlar
# ============================================================================
st.sidebar.header(T["settings"])

# Dil seçimi
lang_col1, lang_col2 = st.sidebar.columns(2)
with lang_col1:
    if st.button(T["lang_tr"], key="lang_tr_btn", use_container_width=True):
        st.session_state["lang"] = "tr"
        st.rerun()
with lang_col2:
    if st.button(T["lang_en"], key="lang_en_btn", use_container_width=True):
        st.session_state["lang"] = "en"
        st.rerun()

# Tema seçimi
theme_label = T["theme_dark"] if not DARK else T["theme_light"]
if st.sidebar.button(theme_label, key="theme_btn", use_container_width=True):
    st.session_state["dark_mode"] = not DARK
    st.rerun()

st.sidebar.markdown("---")

# Mevcut seçili kanal
selected_channel_id = token_manager.get_selected_channel()
none_label = "Varsayılan (Mine) Kanal" if LANG == "tr" else "Default (Mine) Channel"
if selected_channel_id is None:
    st.sidebar.info(f"{T['current_channel']} {none_label}")
else:
    st.sidebar.info(f"{T['current_channel']} Seçili: {selected_channel_id[:20]}...")

# Kanal listesini yükle (API çağrısı)
def _load_channels():
    """Kanalları API'den çek ve session_state'e kaydet."""
    try:
        client = YouTubeAPIClient(token_manager, config=config)
        channels = client.list_accessible_channels()
        channel_options = {}
        for ch in channels:
            channel_options[ch["channel_id"]] = {
                "title": ch["title"],
                "subscribers": ch["subscriber_count"],
                "views": ch["view_count"],
                "videos": ch["video_count"],
            }
        st.session_state["channel_options"] = channel_options
        return channel_options
    except Exception as e:
        st.sidebar.error(f"{T['channel_load_fail']}: {str(e)[:100]}")
        return {}

if st.sidebar.button(T["refresh_channels"], key="refresh_btn", use_container_width=True):
    _load_channels()
    st.rerun()

# İlk yükleme veya refresh
if "channel_options" not in st.session_state or not st.session_state["channel_options"]:
    _load_channels()

channel_options = st.session_state.get("channel_options", {})

# Aktif kanal ID'sini belirle
if "selected_channel_id" in st.session_state:
    active_id = st.session_state["selected_channel_id"]
else:
    active_id = selected_channel_id

# Kanal seçimi UI
st.sidebar.subheader("📺 " + ("Kanallar" if LANG == "tr" else "Channels"))
if channel_options:
    selected = st.sidebar.radio(
        T["channel_select"],
        options=list(channel_options.keys()),
        format_func=lambda x: f"{channel_options[x]['title']} ({channel_options[x]['subscribers']} {'abone' if LANG == 'tr' else 'subs'})",
        index=list(channel_options.keys()).index(active_id) if active_id in channel_options else 0,
        key="channel_radio",
    )

    # Seçimi kaydet
    if selected != st.session_state.get("selected_channel_id"):
        st.session_state["selected_channel_id"] = selected
        token_manager.set_selected_channel(selected)
        st.sidebar.success(T["channel_set"].format(channel_options[selected]["title"]))
        st.rerun()

    # Kanal bilgisini göster
    active_channel = channel_options[selected]
    st.sidebar.success(T["active_channel"].format(active_channel["title"]))
    st.sidebar.info(T["subscribers"].format(active_channel["subscribers"]))
    st.sidebar.info(T["views"].format(active_channel["views"]))
    st.sidebar.info(T["videos"].format(active_channel["videos"]))
else:
    st.sidebar.warning(T["channel_load_fail"])

st.sidebar.markdown("---")
if st.sidebar.button(T["reset_channel"], key="reset_btn", use_container_width=True):
    token_manager.set_selected_channel(None)
    if "selected_channel_id" in st.session_state:
        del st.session_state["selected_channel_id"]
    st.sidebar.success(T["reset_done"])
    st.rerun()

# Kota kullanımı
try:
    client_quota = YouTubeAPIClient(token_manager, config=config)
    quota_used = client_quota.quota_used_today
    quota_limit = config.daily_quota_limit
    quota_remaining = max(0, quota_limit - quota_used)
    st.sidebar.markdown("---")
    st.sidebar.subheader(T["quota"])
    st.sidebar.info(T["quota_used"].format(quota_used))
    st.sidebar.info(T["quota_limit"].format(quota_limit))
    st.sidebar.info(T["quota_remaining"].format(quota_remaining))
    # Kota progres bar
    quota_pct = min(100, int(quota_used / quota_limit * 100)) if quota_limit > 0 else 0
    st.sidebar.progress(quota_pct)
except Exception:
    pass

# ============================================================================
# Ana Sekmeler
# ============================================================================
tab_labels = [
    T["dashboard"],
    T["video_mgmt"],
    T["upload_history"],
    T["analytics"],
    T["settings_tab"],
]
tabs = st.tabs(tab_labels)

# ============================================================================
# Tab 1: Dashboard
# ============================================================================
with tabs[0]:
    st.header(T["main_stats"])

    # Seçili kanal bilgilerini al
    active_channel = None
    if channel_options:
        current_sel = st.session_state.get("selected_channel_id") or active_id
        if current_sel in channel_options:
            active_channel = channel_options[current_sel]

    if active_channel:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                f"""<div class="metric-card">
                <h3>{T['subs_count']}</h3>
                <h1>{active_channel['subscribers']:,}</h1>
            </div>""",
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""<div class="metric-card">
                <h3>{T['views_count']}</h3>
                <h1>{active_channel['views']:,}</h1>
            </div>""",
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                f"""<div class="metric-card">
                <h3>{T['video_count']}</h3>
                <h1>{active_channel['videos']}</h1>
            </div>""",
                unsafe_allow_html=True,
            )

        # Grafikler
        st.markdown("---")
        st.subheader(T["perf_charts"])

        col_grafik1, col_grafik2 = st.columns(2)

        with col_grafik1:
            subs = int(active_channel["subscribers"])
            hedef = 1_000_000
            kalan = max(hedef - subs, 0)
            fig = px.pie(
                values=[subs, kalan],
                names=["Abone", "Kalan Hedef"],
                title=T["subs_goal"],
                color_discrete_sequence=["#ff0000", "#ffcccc"],
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_grafik2:
            try:
                reporter = AnalyticsReporter(token_manager, config=config)
                bugun = datetime.now().strftime("%Y-%m-%d")
                on_gun_once = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                daily_views = reporter.get_daily_views(
                    start_date=on_gun_once,
                    end_date=bugun,
                )

                if daily_views:
                    dates = [d["date"] for d in daily_views]
                    views = [d["views"] for d in daily_views]

                    fig2 = go.Figure()
                    fig2.add_trace(
                        go.Scatter(
                            x=dates,
                            y=views,
                            mode="lines+markers",
                            name=T["daily_views"],
                            line=dict(color="#ff0000", width=3),
                        )
                    )
                    fig2.update_layout(
                        title=T["daily_views"],
                        xaxis_title="Tarih",
                        yaxis_title="Görüntüleme Sayısı",
                        height=300,
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info(T["no_analytics"])
            except Exception as e:
                st.error(f"Grafik verisi alınamadı: {str(e)[:100]}")

        # Son Aktivite
        st.markdown("---")
        st.subheader(T["recent_videos"])

        try:
            reporter = AnalyticsReporter(token_manager, config=config)
            recent_videos = reporter.get_recent_videos(max_results=10)

            if recent_videos:
                video_df = pd.DataFrame(recent_videos)
                cols = [c for c in ["title", "video_id", "published_at"] if c in video_df.columns]
                st.dataframe(
                    video_df[cols],
                    column_config={
                        "title": "Video Başlığı",
                        "video_id": "Video ID",
                        "published_at": "Yayın Tarihi",
                    },
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info(T["no_videos"])
        except Exception as e:
            st.error(T["video_list_fail"].format(str(e)[:100]))

    else:
        st.info("Lütfen sol panelden bir kanal seçin.")

# ============================================================================
# Tab 2: Video Yönetimi
# ============================================================================
with tabs[1]:
    st.header(T["video_mgmt_title"])

    col_vm1, col_vm2 = st.columns([3, 1])

    with col_vm1:
        st.subheader(T["recent_title"])

    with col_vm2:
        if st.button("🔄 Yenile", key="vm_refresh", use_container_width=True):
            st.rerun()

    try:
        reporter = AnalyticsReporter(token_manager, config=config)
        recent_videos = reporter.get_recent_videos(max_results=50)

        if recent_videos:
            video_df = pd.DataFrame(recent_videos)
            cols = [c for c in ["title", "video_id", "published_at"] if c in video_df.columns]
            st.dataframe(
                video_df[cols],
                column_config={
                    "title": "Video Başlığı",
                    "video_id": "Video ID",
                    "published_at": "Yayın Tarihi",
                },
                hide_index=True,
                use_container_width=True,
            )

            # Video ayrıntıları
            st.markdown("---")
            st.subheader(T["video_details"])
            vid_id_input = st.text_input(
                "Video ID Girin",
                placeholder="Örn: dQw4w9WgXcQ",
                key="vm_vid_id",
            )
            if st.button("📊 İstatistikleri Getir", key="vm_get_stats"):
                if vid_id_input:
                    try:
                        stats = reporter.get_video_stats(vid_id_input)
                        if stats:
                            col_vd1, col_vd2, col_vd3, col_vd4 = st.columns(4)
                            with col_vd1:
                                st.metric(T["views"], f"{stats.get('views', 0):,}")
                            with col_vd2:
                                st.metric(T["likes"], f"{stats.get('likes', 0):,}")
                            with col_vd3:
                                st.metric(T["comments"], f"{stats.get('comments', 0):,}")
                            with col_vd4:
                                st.metric(T["duration"], stats.get("duration", "Bilinmiyor"))
                        else:
                            st.info("Video bulunamadı.")
                    except Exception as e:
                        st.error(f"Hata: {str(e)[:100]}")
                else:
                    st.error(T["enter_vid"])
        else:
            st.info(T["no_videos"])
    except Exception as e:
        st.error(T["video_list_fail"].format(str(e)[:100]))

# ============================================================================
# Tab 3: Yükleme Geçmişi
# ============================================================================
with tabs[2]:
    st.header(T["upload_history_title"])

    try:
        upload_manager = UploadManager(token_manager, config=config)
        history = upload_manager.get_upload_history()

        if history:
            history_rows = []
            for file_hash, record in history.items():
                history_rows.append({
                    T["file"]: record.get("file_name", ""),
                    T["video_id_col"]: record.get("video_id", ""),
                    T["uploaded_at"]: record.get("uploaded_at", ""),
                    T["privacy"]: record.get("privacy_status", ""),
                })

            hist_df = pd.DataFrame(history_rows)
            st.dataframe(
                hist_df,
                hide_index=True,
                use_container_width=True,
            )

            col_exp1, col_exp2, col_exp3 = st.columns(3)

            with col_exp1:
                csv = hist_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    T["export_csv"],
                    data=csv,
                    file_name="yukleme_gecmisi.csv",
                    mime="text/csv",
                    key="exp_csv",
                )

            with col_exp2:
                json_str = json.dumps(history, indent=2, ensure_ascii=False).encode("utf-8")
                st.download_button(
                    T["export_json"],
                    data=json_str,
                    file_name="yukleme_gecmisi.json",
                    mime="application/json",
                    key="exp_json",
                )

            with col_exp3:
                if st.button(T["clear_history"], key="clear_hist", use_container_width=True):
                    upload_manager.clear_upload_history()
                    st.success("Geçmiş temizlendi!")
                    st.rerun()
        else:
            st.info(T["no_uploads"])
    except Exception as e:
        st.error(f"Yükleme geçmişi alınamadı: {str(e)[:100]}")

# ============================================================================
# Tab 4: Analitik
# ============================================================================
with tabs[3]:
    st.header(T["analytics_title"])

    col_an1, col_an2 = st.columns(2)
    with col_an1:
        anal_start = st.date_input(
            T["start_date"],
            value=datetime.now() - timedelta(days=7),
        )
    with col_an2:
        anal_end = st.date_input(
            T["end_date"],
            value=datetime.now(),
        )

    if st.button(T["btn_get_analytics"], key="an_get", use_container_width=True):
        try:
            reporter = AnalyticsReporter(token_manager, config=config)
            report = reporter.get_analytics_report(
                start_date=anal_start.strftime("%Y-%m-%d"),
                end_date=anal_end.strftime("%Y-%m-%d"),
                metrics=["views", "likes", "comments", "estimatedMinutesWatched"],
                dimensions=[],
            )

            if report.get("rows"):
                st.success(T["analytics_success"])
                total_views = sum(int(r[0]) for r in report["rows"] if len(r) > 0)
                st.metric(T["total_views"], f"{total_views:,}")
                st.json(report)
            else:
                st.info(T["no_data"])
        except Exception as e:
            st.error(T["analytics_fail"].format(str(e)[:200]))

# ============================================================================
# Tab 5: Ayarlar
# ============================================================================
with tabs[4]:
    st.header(T["settings_tab"])

    st.subheader("🔐 Güvenlik")
    st.info(
        "OAuth client secret'i ortam değişkeninden okunur. "
        "YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET değişkenlerini ayarlayın."
    )

    st.markdown("---")

    st.subheader("📊 Kota Ayarları")
    st.info(f"Günlük kota limiti: {config.daily_quota_limit}")
    st.info(f"Maksimum deneme sayısı: {config.max_retries}")
    st.info(f"Parça boyutu: {config.upload_chunk_size // 1024} KB")

    st.markdown("---")

    st.subheader("🌐 Dil ve Tema")
    st.write(f"Mevcut dil: {'Türkçe' if LANG == 'tr' else 'English'}")
    st.write(f"Mevcut tema: {'Karanlık' if DARK else 'Aydınlık'}")

    st.markdown("---")

    st.subheader("🔑 Token Yönetimi")
    if st.button("Token'ı Temizle", key="clear_token", use_container_width=True):
        token_manager.clear()
        st.success("Token temizlendi!")
        st.rerun()

    if st.button("Token'ı Yenile", key="refresh_token_btn", use_container_width=True):
        if token_manager.refresh_if_needed():
            st.success("Token yenilendi!")
            st.rerun()
        else:
            st.error("Token yenileme başarısız!")

# ============================================================================
# Alt Bilgi
# ============================================================================
st.markdown("---")
st.caption(T["footer"])
st.caption(T["footer_date"].format(datetime.now().strftime("%d %B %Y")))
st.caption(T["footer_auth"])

if config_errors:
    st.markdown("---")
    st.markdown(
        '<div class="warning-box">⚠️ <b>Güvenlik Uyarıası:</b> '
        "YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET ortam değişkenleri "
        "henüz ayarlanmamış. .env.example dosyasını inceleyin.</div>",
        unsafe_allow_html=True,
    )



