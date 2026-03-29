import streamlit as st
from pathlib import Path
from pitchdeck_core import generate_pitchdeck

# --- Config ---
APP_DIR = Path(__file__).parent
TEMPLATE_PATH = APP_DIR / "templates" / "saleshax-template-base.html"
PLAYBOOK_PATH = APP_DIR / "references" / "playbook.md"

st.set_page_config(page_title="SALESHAX Pitch Deck Generator", page_icon="S", layout="centered")

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0c0b0b; }
    h1 { font-family: 'Georgia', serif; font-weight: 300; letter-spacing: -0.02em; }
    .result-box { background: rgba(52,200,138,.06); border: 1px solid rgba(52,200,138,.2);
                  border-radius: 12px; padding: 24px; margin: 16px 0; }
    .result-url { font-size: 20px; font-weight: 500; color: #2ebb7e; }
    .stTextInput > div > div > input { background: #141311; border-color: rgba(255,255,255,.1); color: white; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("### S A L E S H A X")
st.title("Pitch Deck Generator")
st.markdown("Domain eingeben, Pitch Deck wird automatisch generiert und deployed.")

# --- Input ---
domain = st.text_input("Lead-Domain", placeholder="z.B. cluetec-audit.de", label_visibility="collapsed")

generate = st.button("Pitch Deck generieren", type="primary", use_container_width=True)

# --- API Keys ---
api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
netlify_token = st.secrets.get("NETLIFY_TOKEN", "")

if not api_key:
    st.error("ANTHROPIC_API_KEY fehlt in den Secrets.")
    st.stop()

# --- Generate ---
if generate and domain:
    domain = domain.strip().lower()
    if not domain:
        st.warning("Bitte eine Domain eingeben.")
        st.stop()

    status_text = st.empty()
    progress = st.progress(0)

    steps = {"Website wird analysiert...": 15, "Claude analysiert": 50,
             "HTML wird generiert...": 80, "Wird auf Netlify deployed...": 90}

    def on_status(msg):
        status_text.markdown(f"**{msg}**")
        for key, val in steps.items():
            if key in msg:
                progress.progress(val)
                break

    try:
        result = generate_pitchdeck(
            domain=domain,
            api_key=api_key,
            netlify_token=netlify_token,
            template_path=TEMPLATE_PATH,
            playbook_path=PLAYBOOK_PATH,
            on_status=on_status,
        )
        progress.progress(100)
        status_text.empty()

        st.success(f"Pitch Deck für **{result['company_name']}** ist live!")

        # Always use netlify.app URL — guaranteed instant SSL
        live_url = result["netlify_url"]

        st.markdown(f"""
        <div class="result-box">
            <div class="result-url">{live_url}</div>
        </div>
        """, unsafe_allow_html=True)


        col1, col2 = st.columns(2)
        with col1:
            st.link_button("Im Browser öffnen", live_url, use_container_width=True)
        with col2:
            st.download_button(
                "HTML herunterladen",
                data=result["html"],
                file_name=f"saleshax-{result['company_slug']}-pitchdeck.html",
                mime="text/html",
                use_container_width=True,
            )

        with st.expander("Details"):
            g = result["generated"]
            st.markdown(f"**Company:** {g.get('company_name', '?')}")
            st.markdown(f"**Awareness:** {g.get('awareness_stage', '?')}")
            st.markdown(f"**TAM:** {g.get('target_count', '?')}")
            st.markdown(f"**Decision Maker:** {g.get('decision_maker_title', '?')}")

    except Exception as e:
        progress.empty()
        status_text.empty()
        st.error(f"Fehler: {e}")

elif generate and not domain:
    st.warning("Bitte eine Domain eingeben.")
