"""
Turns a call document into the small "card" HTML shown on the dashboard grid.
"""
import time
from phone import text_dir_attrs

STATUS_META = {
    "dialing":  {"label": "Dialing...", "class": "st-dialing"},
    "new":      {"label": "New",        "class": "st-new"},
    "reviewed": {"label": "Reviewed",   "class": "st-reviewed"},
    "failed":   {"label": "Call Failed", "class": "st-failed"},
}
def _format_duration(seconds) -> str:
    if not seconds:
        return "\u2014"
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}" if m else f"0:{s:02d}"


def render_card(doc) -> str:
    call_id = str(doc["_id"])
    ts = time.strftime("%b %d, %H:%M", time.localtime(doc.get("created_at", 0)))
    status = doc.get("status", "new")
    meta = STATUS_META.get(status, STATUS_META["new"])
    direction = doc.get("call_direction", "inbound")
    dir_label = "Outbound" if direction == "outbound" else "Inbound"

    # Catch any lingering whitespace strings and testing artifacts (e.g. the
    # "<local-participant>" placeholder LiveKit uses in local test rooms) so
    # the list never shows raw internal identifiers as if they were numbers.
    caller_val = (doc.get("caller_number") or "").strip()
    caller = caller_val if caller_val and "local-participant" not in caller_val.lower() else "Unknown Number"

    business = doc.get("business_name") or ""
    duration_label = _format_duration(doc.get("call_duration"))

    pulse = (
        '<span class="pulse" aria-hidden="true"><span></span><span></span><span></span><span></span></span>'
        if status in ("new", "dialing") else ""
    )

    # data-search is what the search bar filters against (currently phone number).
    return f"""
    <article class="row" data-call-id="{call_id}" data-status="{status}" data-search="{caller.lower()}" tabindex="0" role="button" aria-label="View call details for {caller}">
        <span class="row-cell row-number">
            <span class="dir-badge dir-{direction}" title="{dir_label}">{dir_label}</span>
            <span class="caller-number mono">{caller}</span>
            {f'<span class="business-name">{business}</span>' if business else ''}
        </span>
        <span class="row-cell row-time mono">{ts}</span>
        <span class="row-cell row-duration mono">{duration_label}</span>
        <span class="row-cell row-status">
            <span class="status-pill {meta['class']}">{pulse}{meta['label']}</span>
        </span>
    </article>
    """


def render_cards_html(docs, empty_message="No calls yet. They'll appear here automatically.") -> str:
    return "".join(render_card(d) for d in docs) or (
        '<div class="empty">'
        '<div class="pulse"><span></span><span></span><span></span><span></span></div>'
        f"{empty_message}"
        "</div>"
    )