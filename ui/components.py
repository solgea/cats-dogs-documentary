"""Yeniden kullanılabilir arayüz bileşenleri (Kontrol Odası dili)."""
from __future__ import annotations

from html import escape
from typing import Any, List, Optional

import streamlit as st

def kpi_card(label: str, value: Any, sub: str = "", color: str = "accent") -> str:
    return f"""
    <div class="cd-kpi" style="--kc: var(--{color});">
      <div class="cd-kpi-label">{label}</div>
      <div class="cd-kpi-value">{value}</div>
      <div class="cd-kpi-sub">{sub}</div>
    </div>"""


def fmt_int(value: int) -> str:
    """Format an integer with comma separators."""
    return f"{value:,}"


def gate_row(label: str, condition: bool, help_text: str = "") -> str:
    """Render a gate row widget.
    
    Shows a labeled row that is conditionally displayed.
    """
    if condition:
        return f'<div class="cd-gate-row"><span class="cd-gate-label">{label}</span> <span class="cd-gate-text">{help_text}</span></div>'
    return ""


def goto(page: str) -> None:
    """Navigate to a different page.
    
    Sets the navigation session state to the specified page.
    """
    st.session_state["nav"] = page


def empty_state(text: str) -> str:
    return f'''
    <div class="cd-empty-state">
      <span class="cd-empty-state-icon">📋</span>
      <div class="cd-empty-state-text">{text}</div>
    </div>'''


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


def page_header(title: str, subtitle: str, chips: Optional[List[str]] = None,
                kicker: str = "", compact: bool = False) -> None:
    """Her sayfada aynı başlık dili: amaç, durum çipleri ve tek odak."""
    chip_html = ('<div class="cd-chip-row">' + "".join(chips) + "</div>") if chips else ""
    kicker_html = f'<div class="cd-page-kicker">{escape(kicker)}</div>' if kicker else ""
    compact_class = " cd-hero-compact" if compact else ""
    st.markdown(
        f'<div class="cd-hero{compact_class}">{kicker_html}'
        f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p>{chip_html}</div>",
        unsafe_allow_html=True,
    )


def focus_card(kicker: str, title: str, meta: str, tone: str = "accent",
               idle: bool = False) -> str:
    # Avoid backslash in f-string expression part (Python 3.12+ restriction)
    idle_marker = " is-idle" if idle else ""
    return (
        f'<div class="cd-focus focus-{tone}{idle_marker}">'
        f'<div class="cd-focus-kicker">{escape(kicker)}</div>'
        f'<div class="cd-focus-title">{escape(title)}</div>'
        f'<div class="cd-focus-meta">{escape(meta)}</div></div>'
    )


def vm_stage_progress(item: dict) -> dict:
    """Calculate progress for a ViewMade production item.

    Handles the real ViewMade MCP statuses (queued, rendering, ready, failed)
    and the local adapter request statuses (SUBMITTED, RENDERING, COMPLETE,
    FAILED, STALE). When the item carries a ``progress`` object from
    ``viewmade_check_video_status`` ({"stage", "pct", "eta", "label"}), the
    real stage label and percentage are used.

    Parameters
    ----------
    item : dict
        ViewMade production item dictionary containing at minimum:
        - 'status': str - production status (queued, rendering, ready, failed, ...)
        - 'created_at': str - creation timestamp
        - 'progress': dict - optional progress data with 'stage' and 'pct' keys

    Returns
    -------
    dict
        {
            "stage": int,           # 1-5 or 0 if unknown/failed
            "step": str,            # Human-readable step with icon
            "percentage": int,      # 0-100 completion percentage
            "status": str,          # Raw status string (lowercased)
            "status_text": str,     # Turkish status word (Sırada/Üretimde/Hazır/...)
            "badge_color": str,     # Color name for badge styling
            "is_active": bool,      # True while in the pipeline (queued/submitted/rendering)
            "is_queued": bool,      # True when waiting in queue
            "is_rendering": bool,   # True when actively producing
            "is_complete": bool,    # True if stage 5 (ready/published)
            "is_failed": bool,      # True if the production failed
        }
    """
    status = str(item.get("status") or "").lower()
    progress_data = item.get("progress") or {}
    pct = 0
    vm_stage_label = ""
    if isinstance(progress_data, dict):
        try:
            pct = int(progress_data.get("pct") or 0)
        except (TypeError, ValueError):
            pct = 0
        vm_stage_label = str(
            progress_data.get("stage") or progress_data.get("label") or ""
        ).strip()

    # Map ViewMade status to pipeline stage
    stage_map = {
        # Real ViewMade MCP statuses (list_videos / check_video_status)
        "queued": 1,
        "rendering": 2,
        "ready": 5,
        "failed": 0,
        # Local adapter request statuses (viewmade-request.json)
        "submitted": 1,
        "complete": 5,
        "completed": 5,
        "succeeded": 5,
        "success": 5,
        "error": 0,
        "rejected": 0,
        "stale": 0,
    }

    stage = stage_map.get(status, 0)

    # Calculate percentage
    if pct > 0:
        percentage = min(100, pct)
    elif stage == 5:  # ready, complete, completed, succeeded, success
        percentage = 100
    elif stage == 0:  # failed, error, rejected, stale
        percentage = 0
    elif stage == 1:  # queued, submitted — henüz üretim başlamadı
        percentage = 5
    else:
        # Estimate based on stage (mid-point of each stage)
        percentage = int((stage - 1) * 20 + 10)

    # Turkish status wording — "üretimde mi sırada mı"
    status_text_map = {
        "queued": "Sırada",
        "submitted": "Sırada",
        "rendering": "Üretimde",
        "ready": "Hazır",
        "complete": "Tamamlandı",
        "completed": "Tamamlandı",
        "succeeded": "Tamamlandı",
        "success": "Tamamlandı",
        "failed": "Başarısız",
        "error": "Hata",
        "rejected": "Reddedildi",
        "stale": "Yeniden gerekli",
    }

    # Determine badge color
    badge_color = STAGE_COLORS.get(stage, "muted") if stage > 0 else "muted"

    # Get stage name and icon; prefer ViewMade's own stage label when provided
    stage_name = VIEWMADE_STAGES[stage - 1] if 1 <= stage <= 5 else "Bilinmiyor"
    step_icon = STAGE_ICONS.get(stage, "❓")
    step_text = vm_stage_label or stage_name

    return {
        "stage": stage,
        "step": f"{step_icon} {step_text}",
        "percentage": percentage,
        "status": status,
        "status_text": status_text_map.get(status, "Bilinmiyor"),
        "badge_color": badge_color,
        "is_active": status in {"submitted", "queued", "rendering"},
        "is_queued": status in {"submitted", "queued"},
        "is_rendering": status == "rendering",
        "is_complete": stage == 5,
        "is_failed": stage == 0,
    }


def render_vm_stage_indicator(item: dict, show_percentage: bool = True) -> str:
    """Render a ViewMade production stage indicator badge.

    Shows the production status word (Sırada / Üretimde / Hazır / Başarısız),
    the current stage and the completion percentage.

    Examples
    --------
    - queued item   → "Sırada · 🧭 Fikir & Niş · %5"
    - rendering     → "Üretimde · 🎬 Görsel Üretim · %45"
    - ready item    → "Hazır · 📤 Yayın & Ölçüm · %100"

    Parameters
    ----------
    item : dict
        ViewMade production item dictionary
    show_percentage : bool, optional
        Whether to show the percentage completion (default True)

    Returns
    -------
    str
        HTML string for the stage indicator badge
    """
    progress = vm_stage_progress(item)

    parts = [progress["status_text"]]
    if progress["stage"] > 0:
        parts.append(progress["step"])
    if show_percentage and progress["percentage"] > 0:
        parts.append(f"%{progress['percentage']}")

    return badge(escape(" · ".join(parts)), progress["badge_color"])


def vm_stage_summary(items: list) -> dict:
    """Calculate summary statistics for a list of ViewMade production items.

    Returns counts and percentages for each stage, plus ready-to-show
    pipeline counters (sırada / üretimde / hazır / başarısız).

    Parameters
    ----------
    items : list
        List of ViewMade production item dictionaries

    Returns
    -------
    dict
        {
            "total": int,                    # Total items
            "by_stage": {int: int},          # Stage number -> count
            "active": int,                   # Items in the pipeline (queued/rendering)
            "queued": int,                   # Items waiting in queue (Sırada)
            "rendering": int,                # Items actively producing (Üretimde)
            "complete": int,                 # Items at stage 5 (ready/published)
            "stalled": int,                  # Items stuck (failed/error/rejected)
            "average_progress": float,       # Average percentage completion
        }
    """
    total = len(items)
    if total == 0:
        return {
            "total": 0,
            "by_stage": {},
            "active": 0,
            "queued": 0,
            "rendering": 0,
            "complete": 0,
            "stalled": 0,
            "average_progress": 0.0,
        }

    by_stage = {i: 0 for i in range(1, 6)}
    by_stage[0] = 0  # Unknown/failure stage
    active = 0
    queued = 0
    rendering = 0
    complete = 0
    stalled = 0
    total_pct = 0.0

    for item in items:
        progress = vm_stage_progress(item)
        stage = progress["stage"]
        by_stage[stage] = by_stage.get(stage, 0) + 1

        if progress["is_active"]:
            active += 1
        if progress["is_queued"]:
            queued += 1
        if progress["is_rendering"]:
            rendering += 1
        if progress["is_complete"]:
            complete += 1
        if stage == 0:  # failed, error, rejected, stale
            stalled += 1

        total_pct += progress["percentage"]

    avg_pct = total_pct / total if total > 0 else 0.0

    return {
        "total": total,
        "by_stage": by_stage,
        "active": active,
        "queued": queued,
        "rendering": rendering,
        "complete": complete,
        "stalled": stalled,
        "average_progress": round(avg_pct, 1),
    }


# ViewMade production stage mapping (1-indexed, matching the 5-stage pipeline)
VIEWMADE_STAGES = [
    "Fikir & Niş",
    "Senaryo & Anlatım",
    "Görsel Üretim",
    "Kalite & İnceleme",
    "Yayın & Ölçüm",
]

# Stage color coding
STAGE_COLORS = {
    1: "info",      # Fikir
    2: "info",      # Senaryo
    3: "accent",    # Üretim
    4: "warn",      # İnceleme
    5: "ok",        # Yayın
}

# Stage icons
STAGE_ICONS = {
    1: "🧭",
    2: "📝",
    3: "🎬",
    4: "🔬",
    5: "📤",
}


# Export the new functions
__all__ = [
    "VIEWMADE_STAGES",
    "STAGE_COLORS",
    "STAGE_ICONS",
    "vm_stage_progress",
    "render_vm_stage_indicator",
    "vm_stage_summary",
]