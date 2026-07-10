import streamlit as st
import anthropic
import pandas as pd
import json
import os
import re
from docx import Document
from dotenv import load_dotenv
from prompt import INTAKE_PROMPT, RANKING_PROMPT, DEEP_DIVE_PROMPT, SYSTEM_PROMPT, INTAKE_SYSTEM_PROMPT

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

MODEL = "claude-haiku-4-5"          # Swap to "claude-sonnet-4-6" for production
DATA_PATH = "data/campaign_database_v1.csv"
LIST_B_PATH = "data/list_b.docx"   # Place your "LIST B Evidence and more all campaigns.docx" here

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TacticShare",
    page_icon="⚡",
    layout="centered"
)

# ─── Styling ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@400,500,700&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono&display=swap');

  html, body, [class*="css"] { font-family: 'Cabinet Grotesk', sans-serif; }

  .stApp { background-color: #f5f5f0; color: #1a1a1a; }

  .hero {
    padding: 2.5rem 0 1.5rem 0;
    border-bottom: 2px solid #ff4500;
    margin-bottom: 2rem;
  }
  .hero h1 { font-size: 3rem; font-weight: 700; color: #ff4500; letter-spacing: -1px; margin: 0; line-height: 1; }
  .hero p { font-size: 1.1rem; color: #6b6560; margin-top: 0.5rem; }

  .section-label {
    font-family: 'Space Mono', monospace;
    font-size: 1.1rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #ff4500;
    margin-bottom: 1rem;
  }

  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea {
    background-color: #ffffff !important;
    color: #1a1a1a !important;
    border: 1px solid #bbb !important;
    border-radius: 4px !important;
    font-family: 'Cabinet Grotesk', sans-serif !important;
  }
  .stTextInput > div > div > input:focus,
  .stTextArea > div > div > textarea:focus {
    border-color: #ff4500 !important;
    box-shadow: 0 0 0 1px #ff4500 !important;
  }
  .stTextInput label, .stTextArea label,
  .stTextInput p, .stTextArea p,
  [data-testid="stTextInput"] p,
  [data-testid="stTextArea"] p {
    color: #1a1a1a !important;
    font-weight: 500 !important;
    font-size: 1rem !important;
    font-family: 'Cabinet Grotesk', sans-serif !important;
  }
  .stSelectbox label, .stSelectbox p { color: #1a1a1a !important; font-weight: 500 !important; }

  .stButton > button {
    background-color: #ff4500 !important;
    color: #ffffff !important;
    font-family: 'Cabinet Grotesk', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 0.6rem 2rem !important;
    font-size: 1rem !important;
    letter-spacing: 0.5px !important;
    transition: opacity 0.2s !important;
  }
  .stButton > button:hover { opacity: 0.85 !important; }

  /* Match cards */
  .match-card {
    background: #e8e4d8;
    border-left: 3px solid #ff4500;
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.6rem;
  }
  .match-card .card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.6rem;
  }
  .match-card h3 { margin: 0; font-size: 1.05rem; color: #1a1a1a; }
  .match-card .score {
    font-family: 'Space Mono', monospace;
    color: #ff4500;
    font-size: 1.3rem;
    font-weight: bold;
    white-space: nowrap;
    margin-left: 1rem;
  }
  .match-card .category-tag {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: #d4d0c4;
    color: #6b6560;
    padding: 0.15rem 0.4rem;
    border-radius: 2px;
    margin-bottom: 0.5rem;
    display: inline-block;
  }
  .match-card .category-tag.animal { background: #d4e8d4; color: #3a6a3a; }
  .match-card ul {
    margin: 0.4rem 0 0 1.1rem;
    padding: 0;
    color: #3a3530;
    font-size: 0.88rem;
    line-height: 1.6;
  }
  .match-card ul li { margin-bottom: 0.15rem; }
  .match-card .dive-hint {
    margin-top: 0.6rem;
    font-size: 0.8rem;
    color: #6b6560;
    font-style: italic;
  }

  /* Deep dive */
  .dive-header {
    background: #e8e4d8;
    border-left: 4px solid #ff4500;
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.5rem;
  }
  .dive-header h2 { margin: 0 0 0.3rem 0; font-size: 1.3rem; color: #1a1a1a; }
  .dive-header .meta { color: #6b6560; font-size: 0.88rem; }
  .dive-header .score-large {
    font-family: 'Space Mono', monospace;
    font-size: 2rem;
    color: #ff4500;
    font-weight: bold;
  }

  .dive-section {
    background: #e8e4d8;
    border-radius: 4px;
    padding: 1.4rem;
    margin-bottom: 1.2rem;
  }
  .dive-section h3 {
    font-family: 'Space Mono', monospace;
    color: #ff4500;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin: 0 0 0.4rem 0;
  }
  .dive-section .intro {
    color: #6b6560;
    font-style: italic;
    font-size: 0.9rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid #c8c4b8;
    padding-bottom: 0.8rem;
  }
  .point-block {
    border-left: 2px solid #c8c4b8;
    padding-left: 1rem;
    margin-bottom: 1rem;
  }
  .point-block h4 { color: #1a1a1a; margin: 0 0 0.3rem 0; font-size: 0.95rem; }
  .point-block p { color: #6b6560; font-size: 0.88rem; margin: 0 0 0.2rem 0; line-height: 1.5; }
  .point-block .relevance { color: #4a7a4a !important; }
  .point-block .risk { color: #c07070 !important; }
  .point-block .transferability { color: #4a6a8a !important; }
  .confidence-badge {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.5px;
    padding: 0.1rem 0.35rem;
    border-radius: 2px;
    display: inline-block;
    margin-bottom: 0.25rem;
  }
  .conf-high { background: #d4e8d4; color: #3a6a3a; border: 1px solid #9aaa9a; }
  .conf-medium { background: #fffbe8; color: #8a6e00; border: 1px solid #c8a000; }
  .conf-low { background: #f8e8e8; color: #8a3030; border: 1px solid #c07070; }
  .inference-flag {
    background: #fffbe8;
    border: 1px solid #c8a000;
    border-radius: 3px;
    padding: 0.15rem 0.4rem;
    font-size: 0.7rem;
    color: #8a6e00;
    font-family: 'Space Mono', monospace;
    display: inline-block;
    margin-bottom: 0.25rem;
  }

  /* Profile summary box */
  .profile-box {
    background: #f0ece0;
    border: 1px solid #c8c4b8;
    border-radius: 4px;
    padding: 1rem 1.4rem;
    margin-bottom: 1.2rem;
    font-size: 0.9rem;
    color: #3a3530;
  }
  .profile-box strong { color: #1a1a1a; }

  hr { border-color: #c8c4b8 !important; }
  #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data
def load_database():
    return pd.read_csv(DATA_PATH)

@st.cache_data
def load_list_b():
    """Read LIST B from a Word doc and parse into a dict keyed by normalised campaign name."""
    try:
        doc = Document(LIST_B_PATH)
        content = "\n".join(p.text for p in doc.paragraphs)
    except FileNotFoundError:
        return {}
    except Exception as e:
        st.warning(f"Could not read LIST B: {e}")
        return {}

    # Split on case section headers (e.g. "LOCKED CASE #1", "CASE 4:", etc.)
    sections = re.split(
        r'\n(?=(?:LOCKED\s+)?CASE\s*#?\d+[:\s])',
        content,
        flags=re.IGNORECASE
    )

    result = {}
    for section in sections[1:]:
        lines = section.strip().split('\n')
        header = lines[0]
        # Strip case number prefix to get a clean name key
        name = re.sub(r'(?:LOCKED\s+)?CASE\s*#?\d+[:\s*–—]+', '', header, flags=re.IGNORECASE)
        name = re.sub(r'\*+', '', name).strip()
        result[name.lower()] = section

    return result

def get_list_b_section(list_b_dict, campaign_name):
    """Fuzzy-match a CSV campaign name to its LIST B section.
    Requires at least 3 meaningful words to match to avoid false positives.
    Logs a warning if the match score is marginal.
    """
    if not list_b_dict:
        return "LIST B data not available — check that data/list_b.docx exists."

    stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for',
                 'from', 'by', 'with', 'its', 'their', 'campaign', 'ban', 'act'}
    campaign_words = set(re.findall(r'\w+', campaign_name.lower())) - stopwords

    best_key, best_score = None, 0
    for key in list_b_dict:
        key_words = set(re.findall(r'\w+', key.lower())) - stopwords
        score = len(campaign_words & key_words)
        if score > best_score:
            best_score, best_key = score, key

    if best_key and best_score >= 3:
        if best_score < 4:
            print(f"[LIST B match WARNING] '{campaign_name}' matched to '{best_key}' "
                  f"with only {best_score} words — verify this is correct.")
        return list_b_dict[best_key]
    elif best_key and best_score >= 1:
        print(f"[LIST B match FAILED] '{campaign_name}' best match was '{best_key}' "
              f"with only {best_score} word(s) — too low to use. Returning empty.")
    return (f"LIST B entry not found for '{campaign_name}'. "
            f"Best candidate was '{best_key}' (score: {best_score}). "
            f"Check that the campaign name in the CSV matches the LIST B section heading.")

def database_to_string(df):
    rows = []
    for _, row in df.iterrows():
        entry = f"CAMPAIGN: {row['Campaign']}\n"
        for col in df.columns:
            if col != 'Campaign':
                entry += f"  {col}: {row[col]}\n"
        rows.append(entry)
    return "\n---\n".join(rows)

def get_list_a_string(df, campaign_name):
    """Look up a campaign row by name. Tries exact match first, then fuzzy fallback."""
    # Exact match
    exact = df[df['Campaign'] == campaign_name]
    if not exact.empty:
        row = exact.iloc[0]
        return "\n".join(f"{col}: {row[col]}" for col in df.columns)

    # Case-insensitive match
    ci = df[df['Campaign'].str.lower() == campaign_name.lower()]
    if not ci.empty:
        row = ci.iloc[0]
        print(f"[CSV match] Case-insensitive match used for '{campaign_name}' → '{row['Campaign']}'")
        return "\n".join(f"{col}: {row[col]}" for col in df.columns)

    # Fuzzy word-overlap match
    stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'from'}
    query_words = set(re.findall(r'\w+', campaign_name.lower())) - stopwords
    best_idx, best_score = None, 0
    for idx, name in df['Campaign'].items():
        name_words = set(re.findall(r'\w+', name.lower())) - stopwords
        score = len(query_words & name_words)
        if score > best_score:
            best_score, best_idx = score, idx

    if best_idx is not None and best_score >= 2:
        row = df.loc[best_idx]
        print(f"[CSV match WARNING] Fuzzy match used: '{campaign_name}' → '{row['Campaign']}' (score: {best_score})")
        return "\n".join(f"{col}: {row[col]}" for col in df.columns)

    raise ValueError(
        f"Campaign '{campaign_name}' not found in campaign_database_v1.csv. "
        f"The LLM may have returned a name that doesn't match the database exactly. "
        f"Available campaigns: {list(df['Campaign'])}"
    )

# ─── LLM calls ────────────────────────────────────────────────────────────────

def call_llm(prompt_text, max_tokens=2000, system=None):
    """Call the Claude API. Pass system=SYSTEM_PROMPT for database calls,
    system=INTAKE_SYSTEM_PROMPT for intake, or system=None to use default."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY not found. Check your .env file.")
        st.stop()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = dict(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt_text}]
        )
        if system:
            kwargs["system"] = system
        message = client.messages.create(**kwargs)
        return message.content[0].text
    except Exception as e:
        st.error(f"API call failed: {type(e).__name__}: {e}")
        raise

def parse_json(text, label="response"):
    """Parse JSON from LLM response. On failure, show detailed debug info."""
    try:
        clean = text.strip()
        # Strip markdown code fences if present
        if "```" in clean:
            parts = clean.split("```")
            for part in parts:
                candidate = part.lstrip("json").strip()
                try:
                    return json.loads(candidate)
                except Exception:
                    continue
        return json.loads(clean)
    except Exception as e:
        st.error(f"Failed to parse JSON from {label}.")
        with st.expander(f"Debug: raw {label} (click to expand)"):
            st.text(f"Parse error: {type(e).__name__}: {e}")
            st.text("--- Raw LLM response ---")
            st.text(text[:5000] if text else "(empty response)")
        return None

# ─── Helpers ──────────────────────────────────────────────────────────────────

def confidence_badge(level):
    lvl = (level or "").strip().lower()
    if "high" in lvl:
        return '<span class="confidence-badge conf-high">HIGH</span>'
    elif "medium" in lvl:
        return '<span class="confidence-badge conf-medium">MEDIUM</span>'
    elif "low" in lvl:
        return '<span class="confidence-badge conf-low">LOW</span>'
    return ''

def reset():
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# ─── App ──────────────────────────────────────────────────────────────────────

def main():
    df = load_database()
    list_b = load_list_b()

    st.markdown("""
    <div class="hero">
      <h1>TacticShare</h1>
      <p>Strategic intelligence for campaigners. Learn from movements that came before yours.</p>
    </div>
    """, unsafe_allow_html=True)

    if 'stage' not in st.session_state:
        st.session_state.stage = 'input'

    # ── INPUT STAGE ───────────────────────────────────────────────────────────
    if st.session_state.stage == 'input':

        st.markdown('<div class="section-label">Your Campaign</div>', unsafe_allow_html=True)

        topic_and_goal = st.text_area(
            "What is your campaign about, and what specific change are you trying to achieve?",
            placeholder="e.g. We are campaigning to end the live export of sheep from Australia. "
                        "We want the federal government to pass legislation banning live sheep exports by 2026.",
            height=110,
            key="topic_and_goal"
        )
        jurisdiction = st.text_input(
            "Where are you campaigning?",
            placeholder="e.g. Australia (federal)",
            key="jurisdiction"
        )
        decision_maker = st.text_input(
            "Who has the power to make that change happen?",
            placeholder="e.g. The federal Agriculture Minister and Senate — legislation requires a majority vote.",
            key="decision_maker"
        )
        opposition = st.text_area(
            "Who or what is likely to oppose you, and how powerful are they?",
            placeholder="e.g. The live export industry and rural lobby — well-funded, strong relationships "
                        "with the National Party, actively run counter-campaigns.",
            height=90,
            key="opposition"
        )
        public_awareness = st.selectbox(
            "How aware is the general public of the problem you're addressing?",
            options=[
                "Not aware at all — it's invisible or unknown to most people",
                "Somewhat aware, but not activated or engaged",
                "Broadly aware and generally sympathetic",
                "Actively concerned and already demanding change"
            ],
            key="public_awareness"
        )
        campaign_stage = st.selectbox(
            "What stage is your campaign at?",
            options=[
                "Just starting out — early research and planning",
                "Some groundwork done — some allies, some public presence",
                "Already active — running, with momentum building"
            ],
            key="campaign_stage"
        )
        additional_context = st.text_area(
            "Anything else we should know? (optional)",
            placeholder="e.g. We have support from two major welfare organisations. "
                        "A Senate inquiry is underway. Public awareness spiked after a recent media exposé.",
            height=80,
            key="additional_context"
        )

        st.markdown("")
        if st.button("Find Precedents ⚡"):
            if not topic_and_goal or not jurisdiction or not decision_maker:
                st.warning("Please fill in at least the first three fields.")
            else:
                with st.spinner("Analysing your campaign structure..."):
                    intake_prompt = INTAKE_PROMPT.format(
                        topic_and_goal=topic_and_goal,
                        jurisdiction=jurisdiction,
                        decision_maker=decision_maker,
                        opposition=opposition or "Not specified.",
                        public_awareness=public_awareness,
                        campaign_stage=campaign_stage,
                        additional_context=additional_context or "None provided."
                    )
                    intake_response = call_llm(intake_prompt, max_tokens=1500,
                                               system=INTAKE_SYSTEM_PROMPT)
                    intake_result = parse_json(intake_response, label="intake analysis")

                    if intake_result is None:
                        return

                    st.session_state.intake = intake_result
                    st.session_state.raw_inputs = {
                        'topic_and_goal': topic_and_goal,
                        'jurisdiction': jurisdiction,
                        'decision_maker': decision_maker,
                        'opposition': opposition,
                        'public_awareness': public_awareness,
                        'campaign_stage': campaign_stage,
                        'additional_context': additional_context
                    }

                with st.spinner("Matching against precedents..."):
                    db_string = database_to_string(df)
                    profile_text = json.dumps(intake_result, indent=2)

                    ranking_prompt = RANKING_PROMPT.format(
                        database=db_string,
                        structural_profile=profile_text
                    )
                    ranking_response = call_llm(ranking_prompt, max_tokens=2000,
                                                system=SYSTEM_PROMPT)
                    ranking_result = parse_json(ranking_response, label="precedent ranking")

                    if ranking_result is None:
                        return

                    st.session_state.rankings = ranking_result['rankings']
                    st.session_state.stage = 'results'
                    st.rerun()

    # ── RESULTS STAGE ─────────────────────────────────────────────────────────
    elif st.session_state.stage == 'results':

        intake = st.session_state.intake
        rankings = st.session_state.rankings

        st.markdown('<div class="section-label">Precedent Matches</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="profile-box">
          <strong>Your campaign:</strong> {intake.get('campaign_summary', '')}
        </div>
        """, unsafe_allow_html=True)

        def render_match_card(m):
            cat_class = "animal" if m.get('category') == 'animal_welfare' else ""
            cat_label = "Animal Welfare" if m.get('category') == 'animal_welfare' else "Non-Animal Welfare"
            reasons_html = "".join(f"<li>{r}</li>" for r in m.get('match_reasons', []))

            st.markdown(f"""
            <div class="match-card">
              <div class="card-header">
                <div>
                  <span class="category-tag {cat_class}">{cat_label}</span><br>
                  <h3>#{m['rank']} — {m['campaign']}</h3>
                </div>
                <span class="score">{m['fit_score']}%</span>
              </div>
              <h4 style="font-size:0.72rem; font-family:'Space Mono',monospace; letter-spacing:1px;
                         text-transform:uppercase; color:#6b6560; margin:0 0 0.3rem 0;">Why it matches</h4>
              <ul>{reasons_html}</ul>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"Deep dive →", key=f"dive_{m['rank']}"):
                run_deep_dive(m['campaign'], df, list_b, intake)

        for m in rankings:
            render_match_card(m)

        st.divider()
        if st.button("← Refine my inputs"):
            st.session_state.stage = 'input'
            st.rerun()

    # ── DEEP DIVE STAGE ───────────────────────────────────────────────────────
    elif st.session_state.stage == 'deep_dive':

        dd = st.session_state.deep_dive
        s = dd['sections']

        st.markdown('<div class="section-label">Deep Dive</div>', unsafe_allow_html=True)

        # Header card
        st.markdown(f"""
        <div class="dive-header">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
              <h2>{dd['precedent_name']}</h2>
              <div class="meta">
                Outcome: {dd.get('final_state', '—')} &nbsp;|&nbsp; Time horizon: {dd.get('time_horizon', '—')}
              </div>
            </div>
            <div class="score-large">{dd['fit_score']}%</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Parallels
        par = s['parallels']
        st.markdown(f"""
        <div class="dive-section">
          <h3>{par['title']}</h3>
          <div class="intro">{par['intro']}</div>
        """, unsafe_allow_html=True)
        for p in par['points']:
            st.markdown(f"""
            <div class="point-block">
              {confidence_badge(p.get('confidence', ''))}
              <h4>{p['heading']}</h4>
              <p>{p['evidence']}</p>
              <p class="relevance">↳ {p['relevance']}</p>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Differences
        diff = s['differences']
        st.markdown(f"""
        <div class="dive-section">
          <h3>{diff['title']}</h3>
          <div class="intro">{diff['intro']}</div>
        """, unsafe_allow_html=True)
        for p in diff['points']:
            st.markdown(f"""
            <div class="point-block">
              <h4>{p['heading']}</h4>
              <p>{p['evidence']}</p>
              <p class="risk">⚠ {p['risk']}</p>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Notable Tactics
        tac = s['notable_tactics']
        st.markdown(f"""
        <div class="dive-section">
          <h3>{tac['title']}</h3>
          <div class="intro">{tac['intro']}</div>
        """, unsafe_allow_html=True)
        for t in tac['tactics']:
            st.markdown(f"""
            <div class="point-block">
              {confidence_badge(t.get('confidence', ''))}
              <h4>{t['name']}</h4>
              <p>{t['what_they_did']}</p>
              <p class="transferability">→ {t['transferability']}</p>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Recommendations
        rec = s['recommendations']
        st.markdown(f"""
        <div class="dive-section">
          <h3>{rec['title']}</h3>
          <div class="intro">{rec['intro']}</div>
        """, unsafe_allow_html=True)
        for p in rec['points']:
            if p.get('type') == 'inference':
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

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back to all matches"):
                st.session_state.stage = 'results'
                st.rerun()
        with col2:
            if st.button("Start a new search"):
                reset()
                st.rerun()


# ─── Deep dive runner (called from results stage) ─────────────────────────────

def run_deep_dive(campaign_name, df, list_b, intake):
    with st.spinner(f"Building deep dive for {campaign_name}..."):
        try:
            list_a_data = get_list_a_string(df, campaign_name)
        except ValueError as e:
            st.error(f"Could not find campaign in database: {e}")
            return

        list_b_data = get_list_b_section(list_b, campaign_name)

        # No character cap — Haiku has a 200k token context window.
        # The full LIST B section is passed so the LLM can use all confidence levels and tactics.
        prompt = DEEP_DIVE_PROMPT.format(
            campaign_summary=intake.get('campaign_summary', ''),
            jurisdiction=intake.get('jurisdiction', ''),
            campaign_stage=intake.get('campaign_stage', ''),
            structural_profile=json.dumps(intake.get('profile', {}), indent=2),
            precedent_list_a=list_a_data,
            precedent_list_b=list_b_data
        )
        response = call_llm(prompt, max_tokens=3000, system=SYSTEM_PROMPT)
        result = parse_json(response, label=f"deep dive for {campaign_name}")

        if result:
            st.session_state.deep_dive = result
            st.session_state.stage = 'deep_dive'
            st.rerun()


if __name__ == "__main__":
    main()