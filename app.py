import streamlit as st
import anthropic
import pandas as pd
import json
import os
from dotenv import load_dotenv
from prompt import CLARIFICATION_PROMPT, RANKING_PROMPT, DEEP_DIVE_PROMPT

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

MODEL = "claude-haiku-4-5"  # Swap to "claude-sonnet-4-6" for production
DATA_PATH = "data/campaign_database_v1.csv"

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TacticShare",
    page_icon="⚡",
    layout="centered"
)

# ─── Styling ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Space+Mono&display=swap');

  html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
  }

  /* Background */
  .stApp {
    background-color: #0d0d0d;
    color: #f0ece0;
  }

  /* Hero */
  .hero {
    padding: 2.5rem 0 1.5rem 0;
    border-bottom: 2px solid #ff4500;
    margin-bottom: 2rem;
  }
  .hero h1 {
    font-size: 3rem;
    font-weight: 700;
    color: #ff4500;
    letter-spacing: -1px;
    margin: 0;
    line-height: 1;
  }
  .hero p {
    font-size: 1.1rem;
    color: #a0998a;
    margin-top: 0.5rem;
  }

  /* Section labels */
  .section-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #ff4500;
    margin-bottom: 0.5rem;
  }

  /* Input fields */
  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea {
    background-color: #1a1a1a !important;
    color: #f0ece0 !important;
    border: 1px solid #333 !important;
    border-radius: 4px !important;
    font-family: 'Space Grotesk', sans-serif !important;
  }
  .stTextInput > div > div > input:focus,
  .stTextArea > div > div > textarea:focus {
    border-color: #ff4500 !important;
    box-shadow: 0 0 0 1px #ff4500 !important;
  }

  /* Labels */
  .stTextInput label, .stTextArea label {
    color: #f0ece0 !important;
    font-weight: 500 !important;
  }

  /* Primary button */
  .stButton > button {
    background-color: #ff4500 !important;
    color: #0d0d0d !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 0.6rem 2rem !important;
    font-size: 1rem !important;
    letter-spacing: 0.5px !important;
    transition: opacity 0.2s !important;
  }
  .stButton > button:hover {
    opacity: 0.85 !important;
  }

  /* Match cards */
  .match-card {
    background: #1a1a1a;
    border-left: 3px solid #ff4500;
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
  }
  .match-card h3 {
    margin: 0 0 0.3rem 0;
    font-size: 1.1rem;
    color: #f0ece0;
  }
  .match-card .score {
    font-family: 'Space Mono', monospace;
    color: #ff4500;
    font-size: 1.4rem;
    font-weight: bold;
  }
  .match-card .parallel {
    font-style: italic;
    color: #a0998a;
    font-size: 0.9rem;
    margin-top: 0.4rem;
    border-top: 1px solid #2a2a2a;
    padding-top: 0.4rem;
  }

  /* Deep dive */
  .dive-section {
    background: #1a1a1a;
    border-radius: 4px;
    padding: 1.4rem;
    margin-bottom: 1.2rem;
  }
  .dive-section h3 {
    color: #ff4500;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 0 0 0.8rem 0;
    font-family: 'Space Mono', monospace;
  }
  .point-block {
    border-left: 2px solid #2a2a2a;
    padding-left: 1rem;
    margin-bottom: 1rem;
  }
  .point-block h4 {
    color: #f0ece0;
    margin: 0 0 0.3rem 0;
    font-size: 0.95rem;
  }
  .point-block p {
    color: #a0998a;
    font-size: 0.9rem;
    margin: 0 0 0.2rem 0;
  }
  .inference-flag {
    background: #1f1a00;
    border: 1px solid #5a4500;
    border-radius: 3px;
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
    color: #c8a000;
    font-family: 'Space Mono', monospace;
    display: inline-block;
    margin-bottom: 0.3rem;
  }

  /* Clarification box */
  .clarify-box {
    background: #1a1a1a;
    border: 1px solid #ff4500;
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.2rem;
    color: #f0ece0;
  }

  /* Divider */
  hr {
    border-color: #2a2a2a !important;
  }

  /* Hide streamlit branding */
  #MainMenu, footer, header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data
def load_database():
    df = pd.read_csv(DATA_PATH)
    return df

def database_to_string(df):
    """Convert full dataframe to a readable string for the LLM context."""
    rows = []
    for _, row in df.iterrows():
        entry = f"CAMPAIGN: {row['Campaign']}\n"
        for col in df.columns:
            if col != 'Campaign':
                entry += f"  {col}: {row[col]}\n"
        rows.append(entry)
    return "\n---\n".join(rows)

def get_precedent_string(df, campaign_name):
    """Get a single campaign's full data as a string."""
    row = df[df['Campaign'] == campaign_name].iloc[0]
    lines = []
    for col in df.columns:
        lines.append(f"{col}: {row[col]}")
    return "\n".join(lines)

def call_llm(prompt_text):
    """Single LLM call. Returns text response."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY not found. Check your .env file.")
        st.stop()
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt_text}]
    )
    return message.content[0].text

def parse_json_response(text):
    """Safely parse JSON from LLM response."""
    try:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except Exception:
        return None

def reset_to_input():
    """Clear session state back to input stage."""
    for key in ['stage', 'matches', 'clarification', 'selected_campaign', 'deep_dive']:
        if key in st.session_state:
            del st.session_state[key]

# ─── HTML Export ──────────────────────────────────────────────────────────────

def generate_html_report(user_inputs, deep_dive):
    """Generate a standalone HTML report from the deep dive data."""
    s = deep_dive['sections']
    parallels_html = ""
    for p in s['parallels']['points']:
        parallels_html += f"""
        <div class="point">
          <h4>{p['heading']}</h4>
          <p class="evidence">{p['evidence']}</p>
          <p class="relevance">↳ {p['relevance']}</p>
        </div>"""

    differences_html = ""
    for p in s['differences']['points']:
        differences_html += f"""
        <div class="point">
          <h4>{p['heading']}</h4>
          <p class="evidence">{p['evidence']}</p>
          <p class="risk risk-flag">⚠ {p['risk']}</p>
        </div>"""

    recommendations_html = ""
    for p in s['recommendations']['points']:
        if p['type'] == 'inference':
            recommendations_html += f"""
            <div class="point">
              <span class="inference-badge">⚡ INFERENCE</span>
              <h4>{p['heading']}</h4>
              <p>{p['content']}</p>
            </div>"""
        else:
            recommendations_html += f"""
            <div class="point">
              <h4>{p['heading']}</h4>
              <p>{p['content']}</p>
            </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TacticShare — {deep_dive['precedent_name']}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Space+Mono&display=swap');
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d0d0d; color: #f0ece0; font-family: 'Space Grotesk', sans-serif; padding: 2rem; max-width: 800px; margin: 0 auto; }}
    .logo {{ font-size: 1.8rem; font-weight: 700; color: #ff4500; border-bottom: 2px solid #ff4500; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
    .meta {{ background: #1a1a1a; border-radius: 4px; padding: 1rem 1.4rem; margin-bottom: 2rem; }}
    .meta h2 {{ font-size: 1.3rem; color: #ff4500; margin-bottom: 0.5rem; }}
    .meta p {{ color: #a0998a; font-size: 0.9rem; margin-bottom: 0.2rem; }}
    .meta .state {{ color: #f0ece0; font-weight: 500; margin-top: 0.5rem; font-family: 'Space Mono', monospace; font-size: 0.85rem; }}
    .section {{ background: #1a1a1a; border-radius: 4px; padding: 1.4rem; margin-bottom: 1.2rem; }}
    .section h3 {{ color: #ff4500; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 2px; font-family: 'Space Mono', monospace; margin-bottom: 0.5rem; }}
    .section .intro {{ color: #a0998a; font-size: 0.9rem; margin-bottom: 1rem; font-style: italic; }}
    .point {{ border-left: 2px solid #2a2a2a; padding-left: 1rem; margin-bottom: 1rem; }}
    .point h4 {{ color: #f0ece0; font-size: 0.95rem; margin-bottom: 0.3rem; }}
    .point p {{ color: #a0998a; font-size: 0.88rem; line-height: 1.5; }}
    .evidence {{ color: #a0998a; }}
    .relevance {{ color: #7a9a7a !important; margin-top: 0.2rem; }}
    .risk-flag {{ color: #c07070 !important; margin-top: 0.2rem; }}
    .inference-badge {{ background: #1f1a00; border: 1px solid #5a4500; border-radius: 3px; padding: 0.15rem 0.4rem; font-size: 0.7rem; color: #c8a000; font-family: 'Space Mono', monospace; display: inline-block; margin-bottom: 0.3rem; }}
    .footer {{ margin-top: 2rem; font-family: 'Space Mono', monospace; font-size: 0.7rem; color: #444; border-top: 1px solid #2a2a2a; padding-top: 1rem; }}
  </style>
</head>
<body>
  <div class="logo">TacticShare</div>
  <div class="meta">
    <h2>Precedent: {deep_dive['precedent_name']}</h2>
    <p>Your campaign: {user_inputs['topic']} — {user_inputs['jurisdiction']}</p>
    <p>Desired outcome: {user_inputs['outcome']}</p>
    <p class="state">Precedent outcome: {deep_dive['final_state']} &nbsp;|&nbsp; Time horizon: {deep_dive['time_horizon']}</p>
  </div>

  <div class="section">
    <h3>{s['parallels']['title']}</h3>
    <p class="intro">{s['parallels']['intro']}</p>
    {parallels_html}
  </div>

  <div class="section">
    <h3>{s['differences']['title']}</h3>
    <p class="intro">{s['differences']['intro']}</p>
    {differences_html}
  </div>

  <div class="section">
    <h3>{s['recommendations']['title']}</h3>
    <p class="intro">{s['recommendations']['intro']}</p>
    {recommendations_html}
  </div>

  <div class="footer">Generated by TacticShare &nbsp;|&nbsp; Evidence drawn from campaign database &nbsp;|&nbsp; ⚡ marks inferred recommendations</div>
</body>
</html>"""

# ─── App ──────────────────────────────────────────────────────────────────────

def main():
    df = load_database()
    db_string = database_to_string(df)

    # Hero
    st.markdown("""
    <div class="hero">
      <h1>TacticShare</h1>
      <p>Strategic intelligence for campaigners. Learn from movements that came before yours.</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Stage init
    if 'stage' not in st.session_state:
        st.session_state.stage = 'input'

    # ── INPUT STAGE ────────────────────────────────────────────────────────────
    if st.session_state.stage in ['input', 'clarify']:

        st.markdown('<div class="section-label">Your Campaign</div>', unsafe_allow_html=True)

        topic = st.text_input(
            "What is your campaign about?",
            placeholder="e.g. Ending the use of battery cages for hens in Queensland",
            key="topic"
        )
        jurisdiction = st.text_input(
            "Where are you campaigning?",
            placeholder="e.g. Queensland, Australia",
            key="jurisdiction"
        )
        outcome = st.text_input(
            "What outcome would you like to see?",
            placeholder="e.g. State legislation banning battery cages by 2028",
            key="outcome"
        )
        known = st.text_area(
            "What do you know about your campaign so far?",
            placeholder="e.g. We have support from two animal welfare NGOs. The egg industry lobby is well-funded. Public awareness is low.",
            height=120,
            key="known"
        )

        # Show clarification question if needed
        if st.session_state.stage == 'clarify' and 'clarification' in st.session_state:
            st.markdown(f"""
            <div class="clarify-box">
              <strong>Before we match:</strong> {st.session_state.clarification}
            </div>
            """, unsafe_allow_html=True)

        col1, col2 = st.columns([2, 1])
        with col1:
            find = st.button("Find Precedents ⚡")
        with col2:
            if st.session_state.stage != 'input':
                if st.button("Start over"):
                    reset_to_input()
                    st.rerun()

        if find:
            if not topic or not jurisdiction or not outcome:
                st.warning("Please fill in at least the first three fields.")
            else:
                with st.spinner("Analysing your campaign..."):
                    prompt = RANKING_PROMPT.format(
                        database=db_string,
                        topic=topic,
                        jurisdiction=jurisdiction,
                        outcome=outcome,
                        known=known or "Nothing specific yet."
                    )
                    response = call_llm(prompt)
                    result = parse_json_response(response)

                    if result is None:
                        st.error("Something went wrong parsing the response. Please try again.")
                    elif result.get('is_vague'):
                        # Ask clarifying question
                        clarify_prompt = CLARIFICATION_PROMPT.format(
                            topic=topic, jurisdiction=jurisdiction,
                            outcome=outcome, known=known or "Nothing yet."
                        )
                        clarification = call_llm(clarify_prompt)
                        st.session_state.clarification = clarification
                        st.session_state.stage = 'clarify'
                        st.rerun()
                    else:
                        st.session_state.matches = result['matches']
                        st.session_state.user_inputs = {
                            'topic': topic, 'jurisdiction': jurisdiction,
                            'outcome': outcome, 'known': known
                        }
                        st.session_state.stage = 'results'
                        st.rerun()

    # ── RESULTS STAGE ──────────────────────────────────────────────────────────
    elif st.session_state.stage == 'results':

        ui = st.session_state.user_inputs
        st.markdown(f"""
        <div class="section-label">Matching precedents for: {ui['topic']} — {ui['jurisdiction']}</div>
        """, unsafe_allow_html=True)

        st.markdown("Select a precedent to explore in depth.")

        matches = st.session_state.matches
        selected = None

        for m in matches:
            with st.container():
                st.markdown(f"""
                <div class="match-card">
                  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <h3>#{m['rank']} — {m['campaign']}</h3>
                    <span class="score">{m['fit_score']}%</span>
                  </div>
                  <p style="color:#f0ece0; font-size:0.9rem; margin:0.4rem 0;">{m['summary']}</p>
                  <p class="parallel">Key parallel: {m['key_parallel']}</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"Deep dive →", key=f"select_{m['rank']}"):
                    selected = m['campaign']

        if selected:
            with st.spinner(f"Building deep dive for {selected}..."):
                precedent_data = get_precedent_string(df, selected)
                ui = st.session_state.user_inputs
                prompt = DEEP_DIVE_PROMPT.format(
                    topic=ui['topic'],
                    jurisdiction=ui['jurisdiction'],
                    outcome=ui['outcome'],
                    known=ui['known'] or "Nothing specific yet.",
                    precedent_data=precedent_data
                )
                response = call_llm(prompt)
                result = parse_json_response(response)
                if result:
                    st.session_state.deep_dive = result
                    st.session_state.stage = 'deep_dive'
                    st.rerun()
                else:
                    st.error("Something went wrong. Please try again.")

        st.divider()
        if st.button("← Refine my inputs"):
            st.session_state.stage = 'input'
            st.rerun()

    # ── DEEP DIVE STAGE ────────────────────────────────────────────────────────
    elif st.session_state.stage == 'deep_dive':

        dd = st.session_state.deep_dive
        ui = st.session_state.user_inputs
        s = dd['sections']

        st.markdown(f"""
        <div class="section-label">Deep Dive</div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="match-card">
          <div style="display:flex; justify-content:space-between;">
            <h3>{dd['precedent_name']}</h3>
            <span class="score">{dd['fit_score']}%</span>
          </div>
          <p style="color:#a0998a; font-size:0.85rem; margin-top:0.4rem;">
            Outcome: {dd['final_state']} &nbsp;|&nbsp; Time horizon: {dd['time_horizon']}
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Parallels
        st.markdown(f"""
        <div class="dive-section">
          <h3>{s['parallels']['title']}</h3>
          <p style="color:#a0998a; font-style:italic; font-size:0.9rem; margin-bottom:1rem;">{s['parallels']['intro']}</p>
        """, unsafe_allow_html=True)
        for p in s['parallels']['points']:
            st.markdown(f"""
            <div class="point-block">
              <h4>{p['heading']}</h4>
              <p>{p['evidence']}</p>
              <p style="color:#7a9a7a; margin-top:0.2rem;">↳ {p['relevance']}</p>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Differences
        st.markdown(f"""
        <div class="dive-section">
          <h3>{s['differences']['title']}</h3>
          <p style="color:#a0998a; font-style:italic; font-size:0.9rem; margin-bottom:1rem;">{s['differences']['intro']}</p>
        """, unsafe_allow_html=True)
        for p in s['differences']['points']:
            st.markdown(f"""
            <div class="point-block">
              <h4>{p['heading']}</h4>
              <p>{p['evidence']}</p>
              <p style="color:#c07070; margin-top:0.2rem;">⚠ {p['risk']}</p>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Recommendations
        st.markdown(f"""
        <div class="dive-section">
          <h3>{s['recommendations']['title']}</h3>
          <p style="color:#a0998a; font-style:italic; font-size:0.9rem; margin-bottom:1rem;">{s['recommendations']['intro']}</p>
        """, unsafe_allow_html=True)
        for p in s['recommendations']['points']:
            if p['type'] == 'inference':
                st.markdown(f"""
                <div class="point-block">
                  <span class="inference-flag">⚡ INFERENCE</span>
                  <h4>{p['heading']}</h4>
                  <p>{p['content']}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="point-block">
                  <h4>{p['heading']}</h4>
                  <p>{p['content']}</p>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Export
        st.divider()
        html_report = generate_html_report(ui, dd)
        st.download_button(
            label="⬇ Download HTML Report",
            data=html_report,
            file_name=f"tacticshare_{dd['precedent_name'].replace(' ', '_')[:30]}.html",
            mime="text/html"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back to matches"):
                st.session_state.stage = 'results'
                st.rerun()
        with col2:
            if st.button("Start a new search"):
                reset_to_input()
                st.rerun()

if __name__ == "__main__":
    main()
