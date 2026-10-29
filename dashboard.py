#!/usr/bin/env python
"""YouTube Professional Dashboard - Streamlit Based"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import sys
sys.path.insert(0, 'src/cddocs')

from youtube.token_manager import TokenManager
from youtube.api_client import YouTubeAPIClient
from youtube.analytics import AnalyticsReporter


# --- Sayfa Yapılandırması ---
st.set_page_config(
    page_title="YouTube Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Stilizasyonu ---
st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stSelectbox > div > div > div {
        background-color: #f0f2f6;
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
    </style>
""", unsafe_allow_html=True)

# --- Başlık ---
st.title("📊 YouTube Profesyonel Dashboard")
st.markdown("**YouTube Analitik & Kanal Yönetimi**")
st.markdown("---")

# --- Sidebar: Kanal Seçimi ---
st.sidebar.header("⚙️ Ayarlar & Kanal Seçimi")

token_manager = TokenManager('src/cddocs/youtube/youtube_token.json')
token_manager.load_credentials()

# Mevcut seçili channel
selected_channel_id = token_manager.get_selected_channel()
none_label = "Varsayılan (Mine) Kanal" if selected_channel_id is None else "Seçili: " + selected_channel_id[:20] + "..."

st.sidebar.info("Mevcut Kanal: " + none_label)

# Kanal seçimi
if st.sidebar.button("Kanalları Yenile ve Seç"):
    # Kanalları listele
    client = YouTubeAPIClient(token_manager)
    request = client.service.channels().list(part="snippet,statistics", mine=True)
    response = request.execute()
    
    if response.get("items"):
        channels = response["items"]
        channel_options = {}
        for ch in channels:
            title = ch["snippet"]["title"]
            ch_id = ch["id"]
            stats = ch.get("statistics", {})
            # Ensure integer values
            subs = int(stats.get("subscriberCount", 0))
            views = int(stats.get("viewCount", 0))
            videos = int(stats.get("videoCount", 0))
            channel_options[ch_id] = {
                "title": title,
                "subscribers": subs,
                "views": views,
                "videos": videos
            }
        
        # Seçimi kaydet
        st.session_state["channel_options"] = channel_options
        if selected_channel_id and selected_channel_id in channel_options:
            st.session_state["selected_channel_id"] = selected_channel_id
        elif channel_options:
            # İlk kanalı varsayılan yap
            first_id = list(channel_options.keys())[0]
            st.session_state["selected_channel_id"] = first_id
            token_manager.set_selected_channel(first_id)
    
    st.rerun()

# Aktif channel'ı göster
if "selected_channel_id" in st.session_state:
    active_id = st.session_state["selected_channel_id"]
else:
    active_id = selected_channel_id

# Channel seçimi
channel_options = st.session_state.get("channel_options", {})
if not channel_options:
    # İlk yükleme veya refresh
    client = YouTubeAPIClient(token_manager)
    request = client.service.channels().list(part="snippet,statistics", mine=True)
    response = request.execute()
    if response.get("items"):
        channel_options = {}
        for ch in response["items"]:
            title = ch["snippet"]["title"]
            ch_id = ch["id"]
            stats = ch.get("statistics", {})
            subs = int(stats.get("subscriberCount", 0))
            views = int(stats.get("viewCount", 0))
            videos = int(stats.get("videoCount", 0))
            channel_options[ch_id] = {
                "title": title,
                "subscribers": subs,
                "views": views,
                "videos": videos
            }
    st.session_state["channel_options"] = channel_options

# Kanal seçimi UI
st.sidebar.subheader("Kanallar")
if channel_options:
    # Mevcut seçiliyi ön plana çıkar
    selected = st.sidebar.radio(
        "Kanal Seçiniz:",
        options=list(channel_options.keys()),
        format_func=lambda x: channel_options[x]["title"] + " (" + str(channel_options[x]["subscribers"]) + " abone)",
        index=list(channel_options.keys()).index(active_id) if active_id in channel_options else 0,
        key="channel_radio"
    )
    
    # Seçimi kaydet
    if selected != st.session_state.get("selected_channel_id"):
        st.session_state["selected_channel_id"] = selected
        token_manager.set_selected_channel(selected)
        st.sidebar.success("Kanal " + channel_options[selected]["title"] + " olarak ayarlandı!")
        st.rerun()
    
    # Kanal bilgisini göster
    active_channel = channel_options[selected]
    st.sidebar.success("Aktif Kanal: " + active_channel["title"])
    st.sidebar.info("Abone: " + str(active_channel["subscribers"]))
    st.sidebar.info("Görüntüleme: " + str(active_channel["views"]))
    st.sidebar.info("Video: " + str(active_channel["videos"]))
else:
    st.sidebar.warning("Kanalları yükleyemedim! Token'ı kontrol edin.")

st.sidebar.markdown("---")
if st.sidebar.button("Varsayılan Kanaalı Sıfırla"):
    token_manager.set_selected_channel(None)
    del st.session_state["selected_channel_id"]
    st.sidebar.success("Varsayılan kanaal ayarlandı!")
    st.rerun()

# --- Ana Sayfa: İstatistik Kartları ---
st.header("Ana Istatistikler")

if channel_options and selected in channel_options:
    active_channel = channel_options[selected]
    
    # Ana métrickartlar
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""<div class="metric-card">
            <h3>Abone Sayısı</h3>
            <h1>""" + str(active_channel["subscribers"]) + """</h1>
        </div>""", unsafe_allow_html=True)
    
    with col2:
        st.markdown("""<div class="metric-card">
            <h3>Görüntülenme Sayısı</h3>
            <h1>""" + str(active_channel["views"]) + """</h1>
        </div>""", unsafe_allow_html=True)
    
    with col3:
        st.markdown("""<div class="metric-card">
            <h3>Video Sayısı</h3>
            <h1>""" + str(active_channel["videos"]) + """</h1>
        </div>""", unsafe_allow_html=True)
    
    # --- Grafikler ---
    st.markdown("---")
    st.subheader("Performans Grafikleri")
    
    col_grafik1, col_grafik2 = st.columns(2)
    
    with col_grafik1:
        # Gerçek abone sayısıyla pie chart
        subs = int(active_channel["subscribers"])
        hedef = 1000000
        kalan = max(hedef - subs, 0)
        fig = px.pie(
            values=[subs, kalan],
            names=["Abone", "Kalan Hedef"],
            title="Abone vs. Hedef Görevi",
            color_discrete_sequence=["#ff0000", "#ffcccc"]
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col_grafik2:
        # Gerçek API'den son 7 günlük veri (AnalyticsReporter ile)
        try:
            reporter = AnalyticsReporter(token_manager)
            # Basit bir zaman serisi: kanal istatistiklerinden yararlan
            # Not: Gerçek YouTube Analytics zaman serisi için get_analytics_report kullanılmalı
            views_count = int(active_channel["views"])
            dates = [datetime.now() - timedelta(days=x) for x in range(7)]
            # Her gün için eşit dağılım (gerçek API verisiyle değiştirilmeli)
            views_per_day = [max(views_count // 7, 0) for _ in range(7)]
            
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=dates,
                y=views_per_day,
                mode="lines+markers",
                name="Günlük Görüntüleme",
                line=dict(color="#ff0000", width=3)
            ))
            fig2.update_layout(
                title="Son 7 Gün - Günlük Görüntüleme (Tahmini)",
                xaxis_title="Tarih",
                yaxis_title="Görüntüleme Sayısı",
                height=300
            )
            st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.error(f"Grafik verisi alınamadı: {e}")
    
    # --- Son Aktivite / Videolar ---
    st.markdown("---")
    st.subheader("Son Aktivite")
    
    try:
        reporter = AnalyticsReporter(token_manager)
        recent_videos = reporter.get_recent_videos(max_results=10)
        
        if recent_videos:
            video_df = pd.DataFrame(recent_videos)
            st.dataframe(
                video_df[["title", "video_id", "published_at"]],
                column_config={
                    "title": "Video Başlığı",
                    "video_id": "Video ID",
                    "published_at": "Yayın Tarihi"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("Henüz video bulunamadı.")
    except Exception as e:
        st.error(f"Video listesi alınamadı: {e}")
    
    # --- Analytics Raporu ---
    st.markdown("---")
    st.subheader("Analytics Özeti")
    
    if st.button("Analytics Raporunu Çalıştır"):
        with st.spinner("Analytics verileri alınıyor..."):
            try:
                reporter = AnalyticsReporter(token_manager)
                # Video istatistiği (son uploaded videoyu varsayalım)
                if "video_id" in st.session_state:
                    vid_stats = reporter.get_video_stats(st.session_state["video_id"])
                    st.success("Analytics verileri alındı!")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Görüntülemeler", str(vid_stats.get("views", 0)))
                    with col_b:
                        st.metric("Beğeni", str(vid_stats.get("likes", 0)))
                    
                    st.info("Yorum: " + str(vid_stats.get("comments", 0)))
                    st.info("Süre: " + vid_stats.get("duration", "Bilinmiyor"))
                
            except Exception as e:
                st.error("Analytics hatası: " + str(e)[:100])
    
    # Analytics butonu
    if st.button("Analytics Başlat", help="Seçili videoyu için detaylı analytics raporu"):
        st.session_state["run_analytics"] = True
    
# --- Alt Bilgi ---
st.markdown("---")
st.caption("YouTube Profesyonel Dashboard | Versiyon 1.0")
st.caption("Geliştirilme tarihi: " + datetime.now().strftime("%B %Y"))
st.caption("Google API Entegrasyonu & OAuth 2.0 Kimlik Doğrulama")