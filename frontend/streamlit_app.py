"""
Streamlit user-facing interface. Run with:
    streamlit run frontend/streamlit_app.py

This is the "customer-facing" deliverable - built for a non-technical
investor-relations user, not a developer console. No raw JSON, no
internal field names, no stack traces.

Deliberately talks to the FastAPI service over HTTP (see api/main.py)
instead of importing MicroRAG in-process. That is the real separation
between the presentation layer and the retrieval/data layer: this file
does not know what a vector store or an embedding model is, and the
API can be redeployed, restarted, or scaled independently of this UI.

Styling: theme colors live in .streamlit/config.toml (Streamlit's
supported mechanism for base colors); the CSS block below only adds
what the theme system can't - card layout, badges, the confidence bar.
Kept as one block, not scattered inline styles, so the visual language
stays consistent as this grows.
"""
import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 30

st.set_page_config(page_title="Family Office Intelligence", page_icon="🔍", layout="centered")

FIRM_TYPE_LABELS = {
    "": "Any",
    "single_family_office": "Single-Family Office",
    "multi_family_office": "Multi-Family Office",
    "unclear": "Unclassified",
}
FIRM_TYPE_BADGE_CLASS = {
    "single_family_office": ("badge-sfo", "Single-Family Office"),
    "multi_family_office": ("badge-mfo", "Multi-Family Office"),
    "unclear": ("badge-unclear", "Type unconfirmed"),
}

EXAMPLE_QUESTIONS = [
    "Which family offices are active in AI investing?",
    "Who do I contact at Hillspire?",
    "What has Duquesne Family Office done recently?",
]

STATUS_STYLE = {
    # status -> (css modifier class, icon)
    "ok": ("status-ok", "✓"),
    "no_results": ("status-muted", "ℹ"),
    "generation_unavailable": ("status-muted", "ℹ"),
    "ungrounded": ("status-warn", "⚠"),
    "generation_error": ("status-warn", "⚠"),
}

CSS = """
<style>
    .block-container { padding-top: 2.5rem; max-width: 760px; }

    .hero-title { font-size: 2rem; font-weight: 700; color: #16213E; margin-bottom: 0.1rem; }
    .hero-sub { color: #6B7280; font-size: 0.98rem; margin-bottom: 1.6rem; }

    /* Uniform pill buttons - applies to the primary Search button and the
       secondary example-question chips alike, for one consistent language. */
    .stButton > button {
        border-radius: 999px;
        font-weight: 600;
        border: 1px solid #E2E1DC;
        padding: 0.4rem 1.1rem;
    }
    .stButton > button[kind="primary"] { border: none; }

    .fo-card {
        background: #FFFFFF;
        border: 1px solid #ECEBE6;
        border-radius: 14px;
        padding: 1.1rem 1.4rem;
        margin-bottom: 0.9rem;
        box-shadow: 0 1px 2px rgba(22, 33, 62, 0.04);
    }

    .answer-card { border-left: 4px solid #9CA3AF; }
    .answer-card.status-ok { border-left-color: #1E7A46; }
    .answer-card.status-warn { border-left-color: #B7791F; }
    .answer-card.status-muted { border-left-color: #9CA3AF; }
    .answer-card .answer-label {
        font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em;
        text-transform: uppercase; color: #6B7280; margin-bottom: 0.4rem;
    }
    .answer-card .answer-text { color: #1F2430; font-size: 1rem; line-height: 1.55; }

    .sources-heading {
        font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em;
        text-transform: uppercase; color: #6B7280; margin: 1.3rem 0 0.6rem 0;
    }

    .source-card {
        background: #FFFFFF;
        border: 1px solid #ECEBE6;
        border-radius: 12px;
        padding: 0.85rem 1.1rem;
        margin-bottom: 0.6rem;
    }
    .source-name { font-weight: 700; color: #16213E; font-size: 0.98rem; }

    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; margin-left: 0.5rem;
    }
    .badge-sfo { background: #E9F3EC; color: #1E7A46; }
    .badge-mfo { background: #E9EEF9; color: #2C5AA0; }
    .badge-unclear { background: #F1F0EC; color: #6B7280; }

    .conf-row { display: flex; align-items: center; gap: 0.6rem; margin-top: 0.5rem; }
    .conf-track { flex: 1; background: #ECEBE6; border-radius: 999px; height: 6px; }
    .conf-fill { background: #B08D57; border-radius: 999px; height: 6px; }
    .conf-label { font-size: 0.78rem; color: #6B7280; white-space: nowrap; }

    .fo-footer { color: #9CA3AF; font-size: 0.85rem; margin-top: 1.8rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def call_api(path: str, method: str = "get", **kwargs):
    """
    Every network call goes through here. Failure modes (API down,
    timeout, bad response) are caught and turned into a value the
    caller can branch on - nothing propagates as a raw exception to
    the UI. The brief is explicit that failures must still produce a
    clear, readable response, not an error dump.
    """
    try:
        resp = requests.request(method, f"{API_BASE_URL}{path}", timeout=REQUEST_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.ConnectionError:
        return None, "The search service is currently unavailable. Please try again in a moment."
    except requests.exceptions.Timeout:
        return None, "The search is taking longer than expected. Please try again."
    except requests.exceptions.HTTPError:
        return None, "The search service returned an unexpected error. Please try again."
    except (ValueError, requests.exceptions.RequestException):
        return None, "Something went wrong reaching the search service. Please try again."


def render_answer(status: str, answer: str) -> None:
    css_class, icon = STATUS_STYLE.get(status, ("status-muted", "ℹ"))
    label = {"ok": "Answer", "no_results": "No matches", "generation_unavailable": "Records only",
              "ungrounded": "Answer withheld", "generation_error": "Answer unavailable"}.get(status, "Result")
    st.markdown(
        f"""<div class="fo-card answer-card {css_class}">
                <div class="answer-label">{icon} {label}</div>
                <div class="answer-text">{answer}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    st.markdown('<div class="sources-heading">Records used</div>', unsafe_allow_html=True)
    for s in sources:
        badge_class, badge_label = FIRM_TYPE_BADGE_CLASS.get(
            s.get("firm_type", ""), ("badge-unclear", "Type unconfirmed")
        )
        conf_pct = max(0, min(100, round(s.get("confidence", 0.0) * 100)))
        st.markdown(
            f"""<div class="source-card">
                    <span class="source-name">{s['name']}</span>
                    <span class="badge {badge_class}">{badge_label}</span>
                    <div class="conf-row">
                        <div class="conf-track"><div class="conf-fill" style="width:{conf_pct}%;"></div></div>
                        <span class="conf-label">{conf_pct}% verified</span>
                    </div>
                </div>""",
            unsafe_allow_html=True,
        )


st.markdown('<div class="hero-title">Family Office Intelligence</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-sub">Ask a question in plain language about the family offices in this dataset.</div>',
    unsafe_allow_html=True,
)

health, health_err = call_api("/health")
if health_err:
    st.error(f"⚠️ {health_err}")
elif health:
    if health.get("chunks_indexed", 0) == 0:
        st.warning("The dataset is currently empty - no records have been indexed yet.")
    if not health.get("generation_available", False):
        st.info("Answer generation is not configured right now - search will return matching records only.")

with st.sidebar:
    st.markdown("### Refine your search")
    firm_type_choice = st.selectbox(
        "Firm type", options=list(FIRM_TYPE_LABELS.keys()), format_func=lambda k: FIRM_TYPE_LABELS[k]
    )
    min_conf = st.slider(
        "Minimum verification confidence", 0.0, 1.0, 0.0, 0.05,
        help="Every fact in this dataset carries a confidence score based on how it was verified. "
             "Raise this to only see well-verified records; lower it to see everything, including "
             "honestly-flagged partial records."
    )
    st.caption(
        "Records below this bar aren't hidden because they're wrong - they're hidden because "
        "their evidence is thinner. Lower the bar to see them anyway."
    )

st.markdown("**Try an example:**")
cols = st.columns(len(EXAMPLE_QUESTIONS))
example_clicked = False
for col, q in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(q, use_container_width=True):
        st.session_state["query_text"] = q
        example_clicked = True

query = st.text_input(
    "What would you like to know?",
    key="query_text",
    placeholder="e.g. Which family offices are investing in AI right now?",
)

if (st.button("Search", type="primary") or example_clicked) and query:
    payload = {
        "question": query,
        "min_confidence": min_conf,
        "firm_type": firm_type_choice or None,
    }
    with st.spinner("Searching verified records..."):
        result, err = call_api("/query", method="post", json=payload)

    if err:
        st.error(f"⚠️ {err}")
    else:
        render_answer(result.get("status", ""), result.get("answer", ""))
        render_sources(result.get("sources", []))

st.markdown(
    '<div class="fo-footer">Answers are restricted to what the underlying verified dataset actually '
    'supports. When the evidence isn\'t strong enough to answer confidently, this system says so '
    'rather than guessing.</div>',
    unsafe_allow_html=True,
)
