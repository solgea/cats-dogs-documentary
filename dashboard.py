#!/usr/bin/env python
"""YouTube Profesyonel Dashboard - Streamlit Tabanlı.

Mimari:
- config.py: Merkezi yapılandırma (ortam değişkenleri)
- token_manager.py: Güvenli OAuth token yönetimi (0o600 dosya izni)
- api_client.py: YouTube Data API v3 istemcisi (retry, quota, validation)
- upload.py: Güvenli upload yöneticisi (confirm_public koruması)
- analytics.py: Seçili kanal desteğiyle analitik raporlama
- oauth_flow.py: OAuth 2.0 yetkilendirme akışı
"""

import sys
import os

# Proje dizinini Python yoluna ekle (src/cddocs)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "cddocs"))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from youtube.config import YouTubeConfig
from youtube.token_manager import TokenManager
from youtube.api_client import YouTubeAPIClient
from youtube.upload import UploadManager
from youtube.analytics import AnalyticsReporter
from youtube.oauth_flow import OAuthFlowManager


# ============================================================================
# Sayfa Yapılandırması
# ============================================================================
st.set_page_config(
    page_title="YouTube Profesyonel Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# CSS Stilizasyonu (Türkçe)
# ============================================================================
st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
    h1, h2, h3 {
        color: #ff0000;
    }
    .stButton > button {
        width: 100%;
        margin-top: 0.5rem;
    }
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .success-box {
        background: #d4edda;
        border: 1px solid #28a745;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# Başlık
# ============================================================================
st.title("📊 YouTube Profesyonel Dashboard")
st.markdown("**YouTube Analitik & Kanal Yönetimi**")
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
    st.info("Lütfen YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET ortam değişkenlerini ayarlayın.")
    st.stop()

token_manager = TokenManager(config=config)
token_manager.load_credentials()

# OAuth flow manager (yeniden yetkilendirme için)
oauth_manager = OAuthFlowManager(config)

# ============================================================================
# Sidebar: Kanal Seçimi ve Ayarlar
# ============================================================================
st.sidebar.header("⚙️ Ayarlar & Kanal Seçimi")

# Token durumu
if token_manager.is_valid():
    st.sidebar.success("✅ Token geçerli")
else:
    st.sidebar.warning("⚠️ Token geçersiz veya yok")
    if st.sidebar.button("Yeniden Yetkilendir (OAuth)"):
        result = oauth_manager.run_local_server(port=8502)
        if result:
            access_token, refresh_token = result
            st.sidebar.success("✅ Yeni token alındı!")
            st.rerun()
        else:
            st.sidebar.error("❌ Yetkilendirme başarısız")

st.sidebar.markdown("---")

# Mevcut seçili kanal
selected_channel_id = token_manager.get_selected_channel()
none_label = "Varsayılan (Mine) Kanal" if selected_channel_id is None else f"Seçili: {selected_channel_id[:20]}..."
st.sidebar.info(f"Mevcut Kanal: {none_label}")

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
        st.sidebar.error(f"Kanalları yükleyemedi: {str(e)[:100]}")
        return {}

if st.sidebar.button("🔄 Kanalları Yenile ve Seç"):
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
st.sidebar.subheader("📺 Kanallar")
if channel_options:
    selected = st.sidebar.radio(
        "Kanal Seçiniz:",
        options=list(channel_options.keys()),
        format_func=lambda x: f"{channel_options[x]['title']} ({channel_options[x]['subscribers']} abone)",
        index=list(channel_options.keys()).index(active_id) if active_id in channel_options else 0,
        key="channel_radio",
    )

    # Seçimi kaydet
    if selected != st.session_state.get("selected_channel_id"):
        st.session_state["selected_channel_id"] = selected
        token_manager.set_selected_channel(selected)
        st.sidebar.success(f"✅ Kanal '{channel_options[selected]['title']}' olarak ayarlandı!")
        st.rerun()

    # Kanal bilgisini göster
    active_channel = channel_options[selected]
    st.sidebar.success(f"**Aktif Kanal:** {active_channel['title']}")
    st.sidebar.info(f"👥 Abone: {active_channel['subscribers']:,}")
    st.sidebar.info(f"👁️ Görüntüleme: {active_channel['views']:,}")
    st.sidebar.info(f"📹 Video: {active_channel['videos']}")
else:
    st.sidebar.warning("Kanalları yükleyemedi! Token'ı kontrol edin.")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Varsayılan Kanaalı Sıfırla"):
    token_manager.set_selected_channel(None)
    if "selected_channel_id" in st.session_state:
        del st.session_state["selected_channel_id"]
    st.sidebar.success("✅ Varsayılan kanaal ayarlandı!")
    st.rerun()

# ============================================================================
# Ana Sayfa: İstatistik Kartları
# ============================================================================
st.header("📈 Ana İstatistikler")

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
                <h3>👥 Abone Sayısı</h3>
                <h1>{active_channel['subscribers']:,}</h1>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div class="metric-card">
                <h3>👁️ Görüntülenme Sayısı</h3>
                <h1>{active_channel['views']:,}</h1>
            </div>""",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""<div class="metric-card">
                <h3>📹 Video Sayısı</h3>
                <h1>{active_channel['videos']}</h1>
            </div>""",
            unsafe_allow_html=True,
        )

    # ========================================================================
    # Grafikler (Gerçek API Verisi)
    # ========================================================================
    st.markdown("---")
    st.subheader("📊 Performans Grafikleri")

    col_grafik1, col_grafik2 = st.columns(2)

    with col_grafik1:
        # Pie chart: Abone vs Hedef
        subs = int(active_channel["subscribers"])
        hedef = 1_000_000
        kalan = max(hedef - subs, 0)
        fig = px.pie(
            values=[subs, kalan],
            names=["Abone", "Kalan Hedef"],
            title="Abone vs. 1 Milyon Hedef",
            color_discrete_sequence=["#ff0000", "#ffcccc"],
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_grafik2:
        # Gerçek analiz verisi: Son 7 günlük görüntüleme
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
                        name="Günlük Görüntüleme",
                        line=dict(color="#ff0000", width=3),
                    )
                )
                fig2.update_layout(
                    title="Son 7 Gün - Günlük Görüntüleme",
                    xaxis_title="Tarih",
                    yaxis_title="Görüntüleme Sayısı",
                    height=300,
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Analiz verisi bulunamadı.")
        except Exception as e:
            st.error(f"Grafik verisi alınamadı: {str(e)[:100]}")

    # ========================================================================
    # Son Aktivite / Videolar (Gerçek API)
    # ========================================================================
    st.markdown("---")
    st.subheader("📺 Son Aktivite")

    try:
        reporter = AnalyticsReporter(token_manager, config=config)
        recent_videos = reporter.get_recent_videos(max_results=10)

        if recent_videos:
            video_df = pd.DataFrame(recent_videos)
            # Sadece mevcut sütunları seç
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
            st.info("Henüz video bulunamadı.")
    except Exception as e:
        st.error(f"Video listesi alınamadı: {str(e)[:100]}")

    # ========================================================================
    # Video Yükleme Formu (Güvenli + Ön İzleme)
    # ========================================================================
    st.markdown("---")
    st.subheader("📤 Video Yükle")

    # Video dosya ön izleme
    video_file = st.text_input(
        "Video Dosya Yolu",
        placeholder="örn: videos/ornek.mp4",
        help="Yüklenecek MP4 dosyasının tam yolu",
        key="video_file_input",
    )

    # Dosya ön izleme bilgisi
    if video_file and os.path.exists(video_file):
        file_size = os.path.getsize(video_file)
        file_size_mb = file_size / (1024 * 1024)
        file_name = os.path.basename(video_file)

        col_prev1, col_prev2, col_prev3 = st.columns(3)
        with col_prev1:
            st.metric("📁 Dosya Adı", file_name)
        with col_prev2:
            st.metric("💾 Boyut", f"{file_size_mb:.2f} MB")
        with col_prev3:
            # Tahmini süre (MB başına ~1 dakika varsayımı, very rough)
            est_duration = max(1, int(file_size_mb))
            st.metric("⏱️ Tahmini Süre", f"{est_duration} dakika")

        # Duplicate kontrolü
        try:
            upload_manager_preview = UploadManager(token_manager, config=config)
            duplicate = upload_manager_preview._is_duplicate(video_file)
            if duplicate:
                st.warning(
                    f"⚠️ Bu dosya daha önce yüklendi (Video ID: {duplicate.get('video_id')}). "
                    "Yine de yüklemek için 'Yinelenene İzin Ver' işaretleyin."
                )
                st.session_state["duplicate_detected"] = True
            else:
                st.session_state["duplicate_detected"] = False
        except Exception:
            st.session_state["duplicate_detected"] = False

    elif video_file:
        st.error("❌ Dosya bulunamadı: " + video_file)
        st.session_state["duplicate_detected"] = False

    # Yükleme formu
    with st.form("upload_form", clear_on_submit=False):
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            video_title = st.text_input(
                "Video Başlığı",
                placeholder="Video başlığını girin",
                key="video_title_input",
            )
        with col_up2:
            video_desc = st.text_area(
                "Açıklama",
                placeholder="Video açıklaması",
                height=100,
                key="video_desc_input",
            )
            video_tags = st.text_input(
                "Etiketler (virgülle ayrılmış)",
                placeholder="kedi,köpek,test",
                key="video_tags_input",
            )

        privacy_col1, privacy_col2 = st.columns(2)
        with privacy_col1:
            privacy_status = st.selectbox(
                "Gizlilik Durumu",
                options=["unlisted", "private", "public"],
                index=0,
                help="Varsayılan 'unlisted'. 'Public' yapmak için onay gereklidir.",
                key="privacy_select",
            )
        with privacy_col2:
            confirm_public = st.checkbox(
                "Kamuya açmayı onaylıyorum",
                value=False,
                disabled=(privacy_status != "public"),
                help="'Public' seçiminde işaretlemek zorunludur.",
                key="confirm_public_cb",
            )

        allow_dup_cb = st.checkbox(
            "Yinelenen dosyaya izin ver",
            value=st.session_state.get("duplicate_detected", False),
            help="Aynı dosya daha önce yüklendiyse bu işaretlemesi gerekir.",
            key="allow_dup_cb",
        )

        submit_upload = st.form_submit_button("📤 Yükle", type="primary")

    if submit_upload:
        if not video_file or not video_title:
            st.error("❌ Lütfen video dosya yolu ve başlığını girin.")
        elif not os.path.exists(video_file):
            st.error("❌ Dosya bulunamadı: " + video_file)
        else:
            try:
                tags = [t.strip() for t in video_tags.split(",") if t.strip()] if video_tags else []
                upload_manager = UploadManager(token_manager, config=config)

                def progress_callback(uploaded: int, total: int):
                    """Upload ilerleme geri çağrısı."""
                    pct = int(uploaded / total * 100) if total > 0 else 0
                    progress_bar.progress(pct)
                    status_text.text(f"Yükleniyor: %{pct}")

                progress_bar = st.progress(0)
                status_text = st.empty()

                with st.spinner("Video yükleniyor... Bu biraz sürebilir."):
                    result = upload_manager.upload_short(
                        video_path=video_file,
                        title=video_title,
                        description=video_desc,
                        tags=tags,
                        privacy_status=privacy_status,
                        confirm_public=confirm_public,
                        progress_callback=progress_callback,
                        allow_duplicate=allow_dup_cb,
                    )

                progress_bar.progress(100)
                status_text.text("Tamamlandı!")

                st.success("✅ Video başarıyla yüklendi!")
                st.info(f"📹 Video ID: {result.get('video_id')}")
                st.info(f"🔗 URL: {result.get('video_url')}")
                st.info(f"🔒 Gizlilik: {result.get('status', {}).get('privacyStatus')}")

                # Yüklenen videoyu session'a kaydet (analitik için)
                st.session_state["last_uploaded_video_id"] = result.get("video_id")

            except ValueError as ve:
                st.error(f"❌ Doğrulama hatası: {ve}")
            except FileNotFoundError as fe:
                st.error(f"❌ Dosya bulunamadı: {fe}")
            except Exception as e:
                st.error(f"❌ Yükleme hatası: {str(e)[:200]}")

    # ========================================================================
    # Gizlilik Değiştirme (Güvenli)
    # ========================================================================
    st.markdown("---")
    st.subheader("🔒 Video Gizliliği Değiştir")

    with st.form("privacy_form"):
        vid_id = st.text_input(
            "Video ID",
            placeholder="Değiştirilecek video ID'si",
            value=st.session_state.get("last_uploaded_video_id", ""),
        )
        new_privacy = st.selectbox(
            "Yeni Gizlilik",
            options=["private", "unlisted", "public"],
            index=1,
        )
        confirm_privacy = st.checkbox(
            "Kamuya açmayı onaylıyorum",
            value=False,
            disabled=(new_privacy != "public"),
        )
        submit_privacy = st.form_submit_button("🔒 Değiştir")

    if submit_privacy:
        if not vid_id:
            st.error("❌ Lütfen Video ID'si girin.")
        else:
            try:
                upload_manager = UploadManager(token_manager, config=config)
                result = upload_manager.set_privacy_status(
                    video_id=vid_id,
                    privacy_status=new_privacy,
                    confirm_public=confirm_privacy,
                )
                st.success(
                    f"✅ Video {vid_id} gizliliği '{result.get('privacy_status')}' olarak değiştirildi."
                )
            except ValueError as ve:
                st.error(f"❌ {ve}")
            except Exception as e:
                st.error(f"❌ Hata: {str(e)[:200]}")

    # ========================================================================
    # Analitik Raporu
    # ========================================================================
    st.markdown("---")
    st.subheader("📊 Analitik Raporu")

    col_an1, col_an2 = st.columns(2)
    with col_an1:
        anal_start = st.date_input(
            "Başlangıç Tarihi",
            value=datetime.now() - timedelta(days=7),
        )
    with col_an2:
        anal_end = st.date_input(
            "Bitiş Tarihi",
            value=datetime.now(),
        )

    if st.button("📊 Analitik Verileri Getir"):
        try:
            reporter = AnalyticsReporter(token_manager, config=config)
            report = reporter.get_analytics_report(
                start_date=anal_start.strftime("%Y-%m-%d"),
                end_date=anal_end.strftime("%Y-%m-%d"),
                metrics=["views", "likes", "comments", "estimatedMinutesWatched"],
                dimensions=[],
            )

            if report.get("rows"):
                st.success("✅ Analitik veriler alındı!")
                total_views = sum(int(r[0]) for r in report["rows"] if len(r) > 0)
                st.metric("Toplam Görüntüleme", f"{total_views:,}")
                st.json(report)
            else:
                st.info("Belirtilen tarih aralığında veri bulunamadı.")
        except Exception as e:
            st.error(f"❌ Analitik hatası: {str(e)[:200]}")

# ============================================================================
# Alt Bilgi
# ============================================================================
st.markdown("---")
st.caption("YouTube Profesyonel Dashboard | Versiyon 2.0")
st.caption("Geliştirilme tarihi: " + datetime.now().strftime("%d %B %Y"))
st.caption("Google API Entegrasyonu & OAuth 2.0 Kimlik Doğrulama")

if config_errors:
    st.markdown("---")
    st.markdown(
        '<div class="warning-box">⚠️ <b>Güvenlik Uyarıası:</b> '
        "YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET ortam değişkenleri "
        "henüz ayarlanmamış. .env.example dosyasını inceleyin.</div>",
        unsafe_allow_html=True,
    )
