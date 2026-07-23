import streamlit as st
import anthropic
import pandas as pd
import json
import os
import re
import html
import hashlib
import pathlib
from dotenv import load_dotenv

from prompt import INTAKE_PROMPT, RANKING_PROMPT, DEEP_DIVE_PROMPT, SYSTEM_PROMPT, INTAKE_SYSTEM_PROMPT

# ─── Configuration ────────────────────────────────────────────────────────────
load_dotenv()

MODEL = "claude-haiku-4-5"          # Swap to "claude-sonnet-4-6" for production
DATA_PATH = "data/campaign_database_v1.csv"
LIST_B_CONF_PATH = "data/list_b_extraction.csv"       # has oracle_campaign join key
CONCENTRATION_PATH = "data/concentration_levels.csv"  # pinned 3-level concentration sidecar
ENABLERS_PATH = "data/campaign_enablers.csv"          # pinned IE enablers (count varies per campaign)
OPPOSITION_PATH = "data/opposition_levels.csv"        # pinned 3-level opposition strength sidecar
CACHE_DIR = "cache"                                   # reproducibility: cached ranking results
PROMPT_VERSION = "2026-07-18-v3"                      # bump when prompts change to invalidate cache

# Ranking is sent in batches to keep each call well under the output token cap.
RANKING_BATCH_SIZE = 5

# Clean category vocabularies
TARGET_TYPES = ["Corporation", "Government", "Consumer"]
MECHANISMS = ["Market pressure", "Policy/legal", "Cultural shift"]
CONCENTRATION_LEVELS = ["Highly concentrated", "Moderately concentrated", "Diffuse"]
CONCENTRATION_ORDER = {"highly concentrated": 0, "moderately concentrated": 1, "diffuse": 2}
OPPOSITION_LEVELS = ["Low", "Moderate", "High"]
OPPOSITION_ORDER = {"low": 0, "moderate": 1, "high": 2}

# Public sentiment categories (must match the Persuasion Architecture threshold wording)
PUBLIC_SENTIMENT_CATEGORIES = ["Near-zero/unaware", "Latently sympathetic", "Actively concerned"]

# Deterministic map from the intake awareness dropdown -> pinned PA category.
PUBLIC_SENTIMENT_MAP = {
    "Not aware at all — it's invisible or unknown to most people": "Near-zero/unaware",
    "Somewhat aware, but not activated or engaged":                "Latently sympathetic",
    "Broadly aware and generally sympathetic":                     "Latently sympathetic",
    "Actively concerned and already demanding change":             "Actively concerned",
}

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="TacticShare", page_icon="⚡", layout="centered")

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@400,500,700&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono&display=swap');

  html, body, [class*="css"] { font-family: 'Cabinet Grotesk', sans-serif; }
  .stApp { background-color: #f5f5f0; color: #1a1a1a; }
  .block-container {
    max-width: 900px !important;
    padding-left: 3rem !important;
    padding-right: 3rem !important;
    padding-top: 2rem !important;
  }
  .hero {
    padding: 2.5rem 0 1.5rem 0;
    border-bottom: 2px solid #ff4500;
    margin-bottom: 2rem;
  }
  .hero h1 { font-size: 4.5rem; font-weight: 700; color: #ff4500; letter-spacing: -2px; margin: 0; line-height: 1; }
  .hero p { font-size: 1.1rem; color: #6b6560; margin-top: 0.5rem; }
  .section-label {
    font-family: 'Cabinet Grotesk', sans-serif;
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.3px;
    text-transform: none;
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
  /* Ensure multi-line text areas are white like the single-line inputs */
  .stTextArea textarea, .stTextInput input,
  [data-baseweb="textarea"], [data-baseweb="base-input"], [data-baseweb="input"] {
    background-color: #ffffff !important;
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
  /* Partial parallels get a muted left border to distinguish them */
  .match-card.partial { border-left: 3px solid #b0a89a; background: #edeae0; }

  /* Per-variable verdict chips */
  .var-chip {
    display: inline-block;
    font-family: 'Cabinet Grotesk', sans-serif;
    font-size: 0.66rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    margin: 0.15rem 0.25rem 0.15rem 0;
    white-space: nowrap;
  }
  .var-eq   { background: #E4EFE0; color: #2E7D32; border: 1px solid #A5D6A7; }
  .var-div  { background: #FBE7EF; color: #AD1457; border: 1px solid #F8BBD0; }

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
  .dive-section {
    background: #e8e4d8;
    border-radius: 4px;
    padding: 1.4rem;
    margin-bottom: 1.2rem;
  }
  /* FIX #20 — deep dive section headings: bold and much larger */
  .dive-section h3 {
    font-family: 'Cabinet Grotesk', sans-serif;
    color: #ff4500;
    font-size: 1.45rem;
    font-weight: 700;
    text-transform: none;
    letter-spacing: -0.3px;
    line-height: 1.25;
    margin: 0 0 0.7rem 0;
  }
  .dive-section .intro {
    color: #4a453f;
    font-style: italic;
    font-size: 0.95rem;
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
  .confidence-badge {
    font-family: 'Cabinet Grotesk', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 0.5px;
    padding: 0.1rem 0.35rem;
    border-radius: 2px;
    display: inline-block;
    margin-bottom: 0.25rem;
  }
  /* FIX #24 — data quality uses a NEUTRAL slate scale. It deliberately shares no
     colour vocabulary with match alignment, which owns green / amber / pink.
     Evidence quality and match strength are different things and must not read alike. */
  .conf-high { background: #e6e9ee; color: #2f3d52; border: 1px solid #9aa6b8; }
  .conf-medium { background: #edeff3; color: #55617a; border: 1px solid #b9c2d0; }
  .conf-low { background: #f4f5f7; color: #7c8598; border: 1px dashed #c3c9d4; }
  .inference-flag {
    background: #fffbe8;
    border: 1px solid #c8a000;
    border-radius: 3px;
    padding: 0.15rem 0.4rem;
    font-size: 0.7rem;
    color: #8a6e00;
    font-family: 'Cabinet Grotesk', sans-serif;
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


# ─── Small helpers ────────────────────────────────────────────────────────────
def esc(s):
    """HTML-escape any value before injecting it into an unsafe_allow_html block."""
    return html.escape(str(s if s is not None else ""))


def _norm(s):
    return str(s or "").strip().lower()


def _idx(options, value, default=0):
    v = _norm(value)
    for i, o in enumerate(options):
        if _norm(o) == v:
            return i
    return default


PROFILE_LABELS = {
    "target_type":                   "Target type (who must change)",
    "decision_making_concentration": "Concentration of decision-making power",
    "strength_of_opposition":        "Strength of opposition",
    "type_of_opposition":            "Type of opposition",
    "visibility_of_harm":            "Visibility of harm to the public",
    "behaviour_change_required":     "Degree of behaviour change required",
    "primary_mechanism":             "Role of policy vs market pressure vs cultural shift",
    "coalition_potential":           "Coalition size, type, and non-obvious allies",
    "economic_disruption":           "Economic disruption required",
    "speed_potential":               "Speed of change (anticipated)",
    "scale_potential":               "Scale of change (anticipated)",
    "public_sentiment_start":        "Public sentiment starting point",
    "legal_regulatory_landscape":    "Legal / regulatory landscape",
    "narrative_dominance":           "Narrative dominance by opposition",
}


# ─── Data loading ─────────────────────────────────────────────────────────────
@st.cache_data
def load_database():
    return pd.read_csv(DATA_PATH)


@st.cache_data
def load_confidence_csv():
    try:
        return pd.read_csv(LIST_B_CONF_PATH)
    except FileNotFoundError:
        st.warning(f"Confidence CSV not found at {LIST_B_CONF_PATH}. Deep dive confidence data will be unavailable.")
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"Could not read confidence CSV: {e}")
        return pd.DataFrame()


@st.cache_data
def load_concentration_levels():
    """Pinned 3-level concentration, keyed by exact oracle campaign name."""
    try:
        cdf = pd.read_csv(CONCENTRATION_PATH)
        return {str(r['oracle_campaign']): str(r['concentration_level']) for _, r in cdf.iterrows()}
    except FileNotFoundError:
        st.warning(f"Concentration sidecar not found at {CONCENTRATION_PATH}. "
                   f"Concentration comparison will fall back to the LLM's own verdict.")
        return {}
    except Exception as e:
        st.warning(f"Could not read concentration sidecar: {e}")
        return {}


@st.cache_data
def load_opposition_levels():
    """Pinned 3-level opposition strength (Low/Moderate/High), keyed by exact oracle name."""
    try:
        odf = pd.read_csv(OPPOSITION_PATH)
        return {str(r['oracle_campaign']): str(r['opposition_level']) for _, r in odf.iterrows()}
    except FileNotFoundError:
        st.warning(f"Opposition sidecar not found at {OPPOSITION_PATH}. "
                   f"Opposition strength will fall back to the LLM's own verdict.")
        return {}
    except Exception as e:
        st.warning(f"Could not read opposition sidecar: {e}")
        return {}


@st.cache_data
def load_enablers():
    """Pinned institutional-environment enablers, extracted once and quote-verified at
    extraction time. Returns {oracle_campaign: [(name, quote), ...]}.

    The COUNT VARIES per campaign. Only categories the precedent actually relied on are
    scored: rows marked status == 'relied_on'. A category the precedent did not rely on
    must never reach the prompt, because under the directional rule the user cannot
    diverge from an enabler the precedent never had.

    Quotes are de-duplicated within a campaign. Two categories can legitimately rest on
    the same sentence (a coalition fact that is also an unexpected-ally fact), and
    scoring it twice would charge a single gap as two divergences."""
    CATEGORY_ORDER = ['regulatory_legal_position', 'coalition',
                      'institutional_political_backing', 'financial_resources',
                      'expert_technical_validation']
    try:
        edf = pd.read_csv(ENABLERS_PATH)
        if 'status' in edf.columns:
            edf = edf[edf['status'].astype(str).str.strip().str.lower() == 'relied_on']
        edf = edf[edf['source_quote'].notna() & (edf['source_quote'].astype(str).str.strip() != '')]
        rank_of = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        edf = edf.assign(_o=edf['enabler_name'].map(lambda x: rank_of.get(str(x), 99)))
        edf = edf.sort_values(['oracle_campaign', '_o', 'enabler_name'])
        out = {}
        for _, r in edf.iterrows():
            camp, name = str(r['oracle_campaign']), str(r['enabler_name'])
            quote = " ".join(str(r['source_quote']).split())
            bucket = out.setdefault(camp, [])
            low = quote.lower()
            if any(low == q.lower() or low in q.lower() or q.lower() in low for _, q in bucket):
                continue
            bucket.append((name, quote))
        return out
    except FileNotFoundError:
        st.warning(f"Enabler sidecar not found at {ENABLERS_PATH}. Institutional Environment "
                   f"will fall back to model-named enablers (less reproducible).")
        return {}
    except Exception as e:
        st.warning(f"Could not read enabler sidecar: {e}")
        return {}


# ─── Campaign name resolution (single source of truth) ────────────────────────
_STOPWORDS = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'from'}


def resolve_oracle_name(df, campaign_name):
    """Resolve an LLM-returned campaign name to the exact oracle name, or None."""
    if campaign_name is None:
        return None
    exact = df[df['Campaign'] == campaign_name]
    if not exact.empty:
        return exact.iloc[0]['Campaign']
    ci = df[df['Campaign'].str.lower() == str(campaign_name).lower()]
    if not ci.empty:
        return ci.iloc[0]['Campaign']
    query_words = set(re.findall(r'\w+', str(campaign_name).lower())) - _STOPWORDS
    best_name, best_score = None, 0
    for _, name in df['Campaign'].items():
        name_words = set(re.findall(r'\w+', str(name).lower())) - _STOPWORDS
        score = len(query_words & name_words)
        if score > best_score:
            best_score, best_name = score, name
    return best_name if best_score >= 2 else None


def _get_campaign_row(df, campaign_name):
    oracle_name = resolve_oracle_name(df, campaign_name)
    if oracle_name is None:
        return None
    return df[df['Campaign'] == oracle_name].iloc[0]


# ─── Confidence lookups (exact join on oracle_campaign key) ───────────────────
_CONF_VAR_COLS = [
    'Target Type', 'Concentration of Decision-Making Power', 'Strength of Opposition',
    'Type of Opposition', 'Visibility of Harm', 'Degree of Behaviour Change Required',
    'Role of Policy vs Market vs Cultural Shift', 'Coalition Size/Type/Non-Obvious Allies',
    'Economic Disruption Required', 'Speed of Change Achieved', 'Scale of Change Achieved',
    'Public Sentiment Starting Point', 'Legal/Regulatory Landscape', 'Narrative Dominance',
    'Notable Tactics',
]


def _conf_row_for_oracle(conf_df, oracle_name):
    if conf_df.empty or oracle_name is None or 'oracle_campaign' not in conf_df.columns:
        return None
    hit = conf_df[conf_df['oracle_campaign'] == oracle_name]
    return hit.iloc[0] if not hit.empty else None


def get_confidence_for_campaign(conf_df, oracle_name):
    if conf_df.empty:
        return "Confidence data not available."
    row = _conf_row_for_oracle(conf_df, oracle_name)
    if row is None:
        return f"Confidence data not found for '{oracle_name}'."
    lines = [
        f"Overall confidence: {row.get('Overall Confidence Flag', 'Not stated')}",
        f"Overall explanation: {row.get('Overall Confidence Explanation', 'Not stated')}",
        "",
        "Per-variable confidence:",
    ]
    for col in _CONF_VAR_COLS:
        lines.append(f"  {col}: {row.get(col, 'Not stated')}")
    return "\n".join(lines)


def get_overall_confidence(conf_df, oracle_name):
    row = _conf_row_for_oracle(conf_df, oracle_name)
    if row is None:
        return None, None
    return row.get('Overall Confidence Flag'), row.get('Overall Confidence Explanation')


RANKING_COLUMNS = [
    'Campaign', 'Target type', 'Concentration of decision-making power',
    'Strength of opposition', 'Type of opposition', 'Visibility of harm to the public',
    'Degree of behaviour change required', 'Role of policy vs market pressure vs cultural shift',
    'Coalition size, type, and presence of non-obvious allies', 'Economic disruption required',
    'Speed of change achieved', 'Scale of change achieved', 'Public sentiment starting point',
    'Legal/regulatory landscape', 'Narrative dominance',
]


def database_to_ranking_string(df, campaign_names, conc_map, enabler_map=None, opp_map=None):
    """Lean database string for the ranking prompt, for the given campaigns only.
    Injects the PINNED concentration level so the model narrates from our classification
    rather than any level word inside the narrative field (fix #17)."""
    wanted = set(campaign_names)
    rows = []
    for _, row in df.iterrows():
        name = row['Campaign']
        if name not in wanted:
            continue
        entry = f"CAMPAIGN: {name}\n"
        level = conc_map.get(name)
        if level:
            entry += f"  Concentration level [PINNED — authoritative]: {level}\n"
        opp = (opp_map or {}).get(name)
        if opp:
            entry += f"  Opposition strength [PINNED — authoritative]: {opp}\n"
        for i, (en, quote) in enumerate((enabler_map or {}).get(name, []), 1):
            entry += f"  Structural enabler [PINNED] {i}: {en} — \"{quote}\"\n"
        for col in RANKING_COLUMNS:
            if col != 'Campaign' and col in df.columns:
                entry += f"  {col}: {row[col]}\n"
        rows.append(entry)
    return "\n---\n".join(rows)


# ─── Compatibility gates (Python — generalised for any target type/mechanism) ──
def compute_gates(df, user_target, user_mechanism):
    """Gate 1 (binary): precedent Primary target type must equal the user's target type.
    Gate 2 (flag only): mechanism equal = 'clear', otherwise 'marginal'. Gate 2 never excludes."""
    ut, um = _norm(user_target), _norm(user_mechanism)
    classifications, passing, excluded, flag_map = [], [], [], {}
    for _, row in df.iterrows():
        name = row['Campaign']
        p_target = row.get('Primary target type', 'Unknown')
        p_mech = row.get('Primary mechanism', 'Unknown')
        if not ((_norm(p_target) == ut) and ut != ""):
            classifications.append({
                'campaign': name, 'gate_result': 'fail', 'gate_flag': None,
                'gate_reasoning': f"Gate 1: {p_target} target — incompatible with your {user_target} target."
            })
            excluded.append(f"{name} — Gate 1: {p_target} target incompatible with your {user_target} target")
            continue
        if _norm(p_mech) == um and um != "":
            flag, g2 = 'clear', f"{p_mech} — compatible"
        else:
            flag, g2 = 'marginal', f"{p_mech} — marginal vs your {user_mechanism}"
        classifications.append({
            'campaign': name, 'gate_result': 'pass', 'gate_flag': flag,
            'gate_reasoning': f"Gate 1: {p_target} — compatible. Gate 2: {g2}."
        })
        passing.append(name)
        flag_map[name] = flag
    return classifications, passing, excluded, flag_map


# ─── Ranking scoring ──────────────────────────────────────────────────────────

ALIGNMENT_SCORES = {'Strong': 2, 'Moderate': 1, 'Weak': 0}
DIMENSION_WEIGHTS = {
    'change_architecture':       0.35,
    'resistance_architecture':   0.25,
    'persuasion_architecture':   0.20,
    'institutional_environment': 0.20,
}
TIER_ORDER = {'Strong structural match': 3, 'Moderate structural match': 2,
              'Limited structural match': 1}


def concentration_verdict(user_level, precedent_level):
    """distance 0 -> 'equivalent'; >=2 -> 'diverges'; 1 or unknown -> None (leave LLM verdict)."""
    a = CONCENTRATION_ORDER.get(_norm(user_level))
    b = CONCENTRATION_ORDER.get(_norm(precedent_level))
    if a is None or b is None:
        return None
    d = abs(a - b)
    if d == 0:
        return 'equivalent'
    if d >= 2:
        return 'diverges'
    return None


def opposition_verdict(user_level, precedent_level):
    """STRICT rule (deliberately stricter than concentration): same pinned level -> 'equivalent',
    any different level -> 'diverges'. Opposition strength is strategically decisive at every
    step, so a one-level gap counts as a divergence. Returns None only if a level is unknown."""
    a = OPPOSITION_ORDER.get(_norm(user_level))
    b = OPPOSITION_ORDER.get(_norm(precedent_level))
    if a is None or b is None:
        return None
    return 'equivalent' if a == b else 'diverges'


def _count_divergences(variables):
    n = 0
    for v in (variables or {}).values():
        verdict = v.get('verdict') if isinstance(v, dict) else v
        if _norm(verdict) == 'diverges':
            n += 1
    return n


# ─── Institutional Environment provenance check (#23) ─────────────────────────
# IE enablers are pinned per campaign, and the count varies. Each carries a verbatim
# source_quote from the precedent's own record, verified at extraction time.
# An instruction to the model is a preference; a check here is a guarantee.
def validate_pinned_enablers(campaign_name, variables, enabler_map, oracle_name):
    """The enablers are pinned, so the model must return verdicts under exactly those
    names. Anything else is a naming drift or an invented enabler — reported, and any
    unpinned entry is dropped so it cannot influence the score."""
    pinned = [n for n, _ in (enabler_map or {}).get(oracle_name or campaign_name, [])]
    if not pinned or not isinstance(variables, dict):
        return [], variables
    issues, kept = [], {}
    lower = {p.lower(): p for p in pinned}
    for name, val in variables.items():
        canon = lower.get(str(name).strip().lower())
        if canon:
            kept[canon] = val
        else:
            issues.append(f"{campaign_name}: returned unpinned enabler '{name}' — dropped")
    for p in pinned:
        if p not in kept:
            issues.append(f"{campaign_name}: pinned enabler '{p}' missing from response — "
                          f"counted as diverges")
            kept[p] = 'diverges'
    return issues, kept


def _alignment_from_count(count):
    return 'Strong' if count == 0 else ('Moderate' if count == 1 else 'Weak')


def derive_dimension(dim_block):
    """Re-derive (count, alignment) in Python from the variables block."""
    llm_alignment = dim_block.get('alignment', 'Weak')
    variables = dim_block.get('variables')
    if not variables:
        return dim_block.get('divergence_count', None), llm_alignment, llm_alignment, False
    count = _count_divergences(variables)
    alignment = _alignment_from_count(count)
    return count, alignment, llm_alignment, (alignment != llm_alignment)


def assign_tier(dim_scores, weighted_score):
    """Strong: no Weak AND score >= 1.60. Moderate: score >= 0.75, CA != Weak, at most one Weak.
    Limited: score >= 0.50 and CA != Weak. None: below that, or CA = Weak."""
    change = dim_scores.get('change_architecture', {}).get('alignment', 'Weak')
    if change == 'Weak':
        return None
    alignments = [dim_scores.get(d, {}).get('alignment', 'Weak') for d in DIMENSION_WEIGHTS]
    weak_count = sum(1 for a in alignments if a == 'Weak')
    if weak_count == 0 and weighted_score >= 1.60:
        return 'Strong structural match'
    elif weighted_score >= 0.75 and weak_count <= 1:
        return 'Moderate structural match'
    elif weighted_score >= 0.50:
        return 'Limited structural match'
    return None


def compute_weighted_score(dim_scores):
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        alignment = dim_scores.get(dim, {}).get('alignment', 'Weak')
        total += ALIGNMENT_SCORES.get(alignment, 0) * weight
    return round(total, 4)


def _card_payload(c, rank):
    return {
        'rank': rank,
        'campaign': c['campaign'],
        'match_tier': c['computed_tier'],
        'gate_flag': c.get('gate_flag', 'clear'),
        'dimension_alignment': {
            dim: {
                'alignment': c['dimension_scores'].get(dim, {}).get('alignment', 'Weak'),
                'reasoning': c['dimension_scores'].get(dim, {}).get('reasoning', ''),
                'variables': c['dimension_scores'].get(dim, {}).get('variables', {}),
            }
            for dim in DIMENSION_WEIGHTS
        },
        'match_summary': c.get('match_summary', ''),
        'weighted_score': c['weighted_score'],
    }


def process_all_scores(all_scores_raw, df, conc_map, user_conc_level, gate_flag_map, enabler_map=None,
                       opp_map=None, user_opp_level=None):
    """Concentration override -> Python alignment recompute -> weighted score -> tier.
    Returns (scored, rankings, partials, below_threshold, mismatch_notes, provenance_issues)."""
    scored, below_threshold, mismatch_notes, provenance_issues = [], [], [], []

    for c in all_scores_raw:
        dim_scores = c.get('dimension_scores', {}) or {}
        oracle_name = resolve_oracle_name(df, c.get('campaign', ''))

        # 1) Deterministic concentration verdict (fix #3)
        ca = dim_scores.get('change_architecture', {})
        ca_vars = ca.get('variables') if isinstance(ca, dict) else None
        prec_level = conc_map.get(oracle_name) if oracle_name else None
        cv = concentration_verdict(user_conc_level, prec_level)
        if cv is not None and isinstance(ca_vars, dict):
            ca_vars['decision_making_concentration'] = cv

        # 1a2) Deterministic opposition strength verdict (pinned, strict rule)
        ra = dim_scores.get('resistance_architecture', {})
        ra_vars = ra.get('variables') if isinstance(ra, dict) else None
        prec_opp = (opp_map or {}).get(oracle_name) if oracle_name else None
        ov = opposition_verdict(user_opp_level, prec_opp)
        if ov is not None and isinstance(ra_vars, dict):
            ra_vars['strength_of_opposition'] = ov

        # 1b) Verify IE enabler provenance against the campaign's own record (#23)
        ie = dim_scores.get('institutional_environment')
        if isinstance(ie, dict):
            ie_issues, ie_vars = validate_pinned_enablers(
                c.get('campaign', ''), ie.get('variables'), enabler_map, oracle_name)
            ie['variables'] = ie_vars
            if ie_issues:
                provenance_issues.extend(ie_issues)

        # 2) Re-derive alignment from verdicts (fix #2)
        for dim in DIMENSION_WEIGHTS:
            block = dim_scores.get(dim)
            if not isinstance(block, dict):
                dim_scores[dim] = block = {'alignment': 'Weak', 'reasoning': ''}
            count, alignment, llm_alignment, mismatch = derive_dimension(block)
            block['alignment'] = alignment
            block['llm_alignment'] = llm_alignment
            if count is not None:
                block['divergence_count'] = count
            if mismatch:
                mismatch_notes.append(f"{c.get('campaign','?')} · {dim}: "
                                      f"LLM said {llm_alignment}, derived {alignment}")

        wscore = compute_weighted_score(dim_scores)
        tier = assign_tier(dim_scores, wscore)
        change_align = dim_scores.get('change_architecture', {}).get('alignment', 'Weak')

        record = {
            **c,
            'dimension_scores': dim_scores,
            'computed_tier': tier,
            'weighted_score': wscore,
            'change_score': ALIGNMENT_SCORES.get(change_align, 0),
            'gate_flag': gate_flag_map.get(oracle_name, gate_flag_map.get(c.get('campaign', ''), 'clear')),
        }

        if tier is None:
            # FIX #14 — keep these so they can be inspected in the debug expander
            record['exclusion_reason'] = ("Change Architecture = Weak" if change_align == 'Weak'
                                          else f"weighted score {wscore:.2f} below 0.50 threshold")
            below_threshold.append(record)
            continue

        scored.append(record)

    scored.sort(key=lambda x: (TIER_ORDER.get(x['computed_tier'], 0), x['weighted_score'], x['change_score']),
                reverse=True)
    main = [c for c in scored if c['computed_tier'] in ('Strong structural match', 'Moderate structural match')]
    limited = [c for c in scored if c['computed_tier'] == 'Limited structural match']
    rankings = [_card_payload(c, i) for i, c in enumerate(main[:5], 1)]
    partials = [_card_payload(c, i) for i, c in enumerate(limited[:3], 1)]  # FIX #15
    return scored, rankings, partials, below_threshold, mismatch_notes, provenance_issues


# ─── Deep-dive data helpers ───────────────────────────────────────────────────
def get_notable_tactics(df, campaign_name):
    row = _get_campaign_row(df, campaign_name)
    if row is None:
        return None
    col = next((c for c in df.columns if c.strip().lower() == 'notable tactics'), None)
    if col is None:
        print("[Variable 15] Notable tactics column not found in database.")
        return None
    return str(row[col])


def parse_tactic_entries(raw_tactics_text):
    if not raw_tactics_text:
        return []
    parts = re.split(r'\s+[a-z]\.\s+', raw_tactics_text.strip())
    parts = [re.sub(r'^[a-z]\.\s+', '', p).strip() for p in parts]
    return [p for p in parts if p]


def check_tactic_hallucinations(tactics_from_llm, raw_tactics_text):
    if not raw_tactics_text or not tactics_from_llm:
        return []
    entries = parse_tactic_entries(raw_tactics_text)
    targets = [t.lower() for t in (entries if entries else [raw_tactics_text])]
    suspicious = []
    for tactic in tactics_from_llm:
        name = (tactic.get('name', '') or '').strip()
        if name and not any(name.lower() in t for t in targets):
            suspicious.append(name)
    return suspicious


def get_time_window_and_outcome(df, campaign_name):
    row = _get_campaign_row(df, campaign_name)
    if row is None:
        return None, None
    return (str(row.get('Time window', '') or '').strip() or None,
            str(row.get('Outcome', '') or '').strip() or None)


def get_list_a_string(df, campaign_name):
    row = _get_campaign_row(df, campaign_name)
    if row is None:
        raise ValueError(
            f"Campaign '{campaign_name}' not found in campaign_database_v1.csv. "
            f"Available campaigns: {list(df['Campaign'])}"
        )
    return "\n".join(f"{col}: {row[col]}" for col in df.columns)


# ─── LLM calls ────────────────────────────────────────────────────────────────
def call_llm(prompt_text, max_tokens=8192, system=None, label=""):
    """Call the Claude API. Logs output tokens and warns on truncation."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY not found. Check your .env file.")
        st.stop()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = dict(model=MODEL, max_tokens=max_tokens, temperature=0,
                      messages=[{"role": "user", "content": prompt_text}])
        if system:
            kwargs["system"] = system
        message = client.messages.create(**kwargs)

        usage = getattr(message, "usage", None)
        stop_reason = getattr(message, "stop_reason", None)
        if usage is not None:
            entry = {
                'label': label or 'call',
                'input_tokens': getattr(usage, 'input_tokens', None),
                'output_tokens': getattr(usage, 'output_tokens', None),
                'max_tokens': max_tokens,
                'stop_reason': stop_reason,
            }
            st.session_state['last_usage'] = entry
            st.session_state.setdefault('usage_log', []).append(entry)
            print(f"[LLM usage] {label} in={entry['input_tokens']} "
                  f"out={entry['output_tokens']}/{max_tokens} stop={stop_reason}")

        if stop_reason == "max_tokens":
            st.warning(
                f"⚠ The model hit its output token limit on {label or 'this call'} and the response "
                f"was cut off. Results may be incomplete — reduce RANKING_BATCH_SIZE or raise max_tokens."
            )

        for block in message.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return message.content[0].text if message.content else ""
    except Exception as e:
        st.error(f"API call failed: {type(e).__name__}: {e}")
        raise


def parse_json(text, label="response"):
    try:
        clean = (text or "").strip()
        if "```" in clean:
            for part in clean.split("```"):
                candidate = part.strip()
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
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


# ─── Result cache (reproducibility) ───────────────────────────────────────────
# Identical inputs must return an identical result, or users cannot trust the tool.
# The LLM is not bit-deterministic even at temperature 0, so we cache on an input hash.
# The key includes the data files and prompt version, so updating either recomputes.
@st.cache_data
def _data_version():
    h = hashlib.sha256()
    for p in (DATA_PATH, LIST_B_CONF_PATH, CONCENTRATION_PATH, ENABLERS_PATH, OPPOSITION_PATH):
        try:
            h.update(pathlib.Path(p).read_bytes())
        except Exception:
            h.update(b"missing")
    return h.hexdigest()[:16]


def cache_key(raw_inputs, categories):
    """Key the cache on the user's RAW typed input plus the confirmed categories, not on the
    LLM-generated profile. The profile varies slightly run to run, so keying on it meant the
    same typed campaign produced a fresh (and slightly different) score every time. Keying on
    the raw text makes identical input return an identical, reproducible result."""
    payload = json.dumps({
        'raw_inputs': raw_inputs or {},
        'categories': categories,
        'model': MODEL,
        'prompt_version': PROMPT_VERSION,
        'data_version': _data_version(),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def cache_load(key):
    try:
        f = pathlib.Path(CACHE_DIR) / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[cache] read failed: {e}")
    return None


def cache_save(key, scores):
    try:
        d = pathlib.Path(CACHE_DIR); d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.json").write_text(json.dumps(scores, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f"[cache] write failed: {e}")


def run_ranking_in_batches(df, passing, conc_map, intake, user_conc, user_sentiment, enabler_map=None,
                           opp_map=None, user_opposition=None):
    """FIX #16 — score gate-passing campaigns in batches so no single call approaches
    the output token cap. Returns the merged all_scores list."""
    profile_text = json.dumps(intake, indent=2)
    merged = []
    batches = [passing[i:i + RANKING_BATCH_SIZE] for i in range(0, len(passing), RANKING_BATCH_SIZE)]
    for n, batch in enumerate(batches, 1):
        db_string = database_to_ranking_string(df, batch, conc_map, enabler_map, opp_map)
        prompt = RANKING_PROMPT.format(
            database=db_string,
            structural_profile=profile_text,
            user_concentration=user_conc,
            user_public_sentiment=user_sentiment,
            user_opposition=user_opposition,
        )
        resp = call_llm(prompt, max_tokens=8192, system=SYSTEM_PROMPT,
                        label=f"ranking batch {n}/{len(batches)}")
        parsed = parse_json(resp, label=f"precedent ranking (batch {n})")
        if parsed is None:
            st.warning(f"⚠ Batch {n} failed to parse — its campaigns are missing from the results.")
            continue
        merged.extend(parsed.get('all_scores', []))
    return merged


# ─── Render helpers ───────────────────────────────────────────────────────────
def confidence_badge(level):
    """FIX #24 — data quality. Neutral slate plus a filled-bar glyph, so the level reads
    without relying on colour and cannot be mistaken for a match-alignment verdict."""
    lvl = (level or "").strip().lower()
    if "high" in lvl:
        return '<span class="confidence-badge conf-high">Evidence strength: High &#9646;&#9646;&#9646;</span>'
    elif "medium" in lvl:
        return '<span class="confidence-badge conf-medium">Evidence strength: Medium &#9646;&#9646;&#9647;</span>'
    elif "low" in lvl:
        return '<span class="confidence-badge conf-low">Evidence strength: Low &#9646;&#9647;&#9647;</span>'
    return ''


def _pretty_var(key):
    return str(key).replace('_', ' ').strip().capitalize()


def variable_chips_html(variables):
    """FIX #19 — show the per-variable verdicts so the reader can see what drove the score.
    FIX #26 — ✓ / ✕ are a matched pair at the same visual weight."""
    if not variables:
        return ''
    chips = []
    for key, val in variables.items():
        verdict = val.get('verdict') if isinstance(val, dict) else val
        diverges = _norm(verdict) == 'diverges'
        cls = 'var-div' if diverges else 'var-eq'
        mark = '✕' if diverges else '✓'
        chips.append(f'<span class="var-chip {cls}">{esc(_pretty_var(key))} {mark}</span>')
    return ''.join(chips)


def reset():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ─── App ──────────────────────────────────────────────────────────────────────
def main():
    df = load_database()
    conf_df = load_confidence_csv()
    conc_map = load_concentration_levels()
    opp_map = load_opposition_levels()
    enabler_map = load_enablers()

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
        st.markdown('<div class="section-label">Your campaign</div>', unsafe_allow_html=True)

        with st.form("intake_form"):
            topic_and_goal = st.text_area(
                "What is your campaign about, and what specific change are you trying to achieve?",
                placeholder="e.g. We are campaigning to end the live export of sheep from Australia. "
                            "We want the federal government to pass legislation banning live sheep exports by 2026.",
                height=110, key="topic_and_goal")

            jurisdiction = st.text_input("Where are you campaigning?",
                                         placeholder="e.g. Australia (federal)", key="jurisdiction")

            decision_maker = st.text_input(
                "Who has the power to make that change happen?",
                placeholder="e.g. The federal Agriculture Minister and Senate — legislation requires a majority vote.",
                key="decision_maker")

            opposition = st.text_area(
                "Who or what is likely to oppose you, and how powerful are they?",
                placeholder="e.g. The live export industry and rural lobby — well-funded, strong relationships "
                            "with the National Party, actively run counter-campaigns.",
                height=90, key="opposition")

            campaign_backing = st.text_area(
                "Does your campaign have any of these yet? (optional)",
                placeholder="Briefly state any of the following:\n"
                            "• Any other groups or organisations working with you\n"
                            "• Money or funding already secured\n"
                            "• Scientists or experts supportive of this campaign\n"
                            "• Politicians, officials, or government bodies supportive of this campaign\n\n"
                            "Don't have these yet? That's fine — write 'not yet' or leave it blank.",
                height=130, key="campaign_backing")

            public_awareness = st.selectbox(
                "How aware is the general public of the problem you're addressing?",
                options=list(PUBLIC_SENTIMENT_MAP.keys()), key="public_awareness")

            campaign_stage = st.selectbox(
                "What stage is your campaign at?",
                options=[
                    "Just starting out — early research and planning",
                    "Some groundwork done — some allies, some public presence",
                    "Already active — running, with momentum building"
                ], key="campaign_stage")

            additional_context = st.text_area(
                "Anything else we should know? (optional)",
                placeholder="e.g. We have support from two major welfare organisations. "
                            "A Senate inquiry is underway. Public awareness spiked after a recent media exposé.",
                height=80, key="additional_context")

            st.markdown("")
            submitted = st.form_submit_button("Find Precedents ⚡")

        if submitted:
            if not topic_and_goal or not jurisdiction or not decision_maker:
                st.warning("Please fill in the first three questions before continuing: "
                           "what your campaign is about, where you are campaigning, and who has "
                           "the power to make the change. The rest are optional.")
            else:
                with st.spinner("Analysing your campaign structure..."):
                    intake_prompt = INTAKE_PROMPT.format(
                        topic_and_goal=topic_and_goal, jurisdiction=jurisdiction,
                        decision_maker=decision_maker, opposition=opposition or "Not specified.",
                        public_awareness=public_awareness, campaign_stage=campaign_stage,
                        campaign_backing=campaign_backing or "None listed — treat institutional supports as not yet established (early-stage campaign).",
                        additional_context=additional_context or "None provided.")
                    intake_response = call_llm(intake_prompt, max_tokens=8192,
                                               system=INTAKE_SYSTEM_PROMPT, label="intake")
                    intake_result = parse_json(intake_response, label="intake analysis")
                    if intake_result is None:
                        return

                    profile = intake_result.get('profile', {})
                    unclear_warnings = []
                    if opposition and "unclear" in profile.get('strength_of_opposition', '').lower():
                        unclear_warnings.append("Strength of opposition (you provided this — the LLM missed it)")
                    if opposition and "unclear" in profile.get('type_of_opposition', '').lower():
                        unclear_warnings.append("Type of opposition (you provided this — the LLM missed it)")
                    if decision_maker and "unclear" in profile.get('decision_making_concentration', '').lower():
                        unclear_warnings.append("Decision-making concentration (you provided this — the LLM missed it)")
                    if unclear_warnings:
                        st.warning("⚠ The analysis missed some information you provided. "
                                   "Go back and re-run — this occasionally happens and should resolve:\n\n"
                                   + "\n".join(f"- {w}" for w in unclear_warnings))
                        return

                    # FIX #11 — public sentiment category derived deterministically from the dropdown
                    intake_result.setdefault('categories', {})
                    intake_result['categories']['public_sentiment'] = PUBLIC_SENTIMENT_MAP.get(
                        public_awareness, "Near-zero/unaware")

                    st.session_state.intake = intake_result
                    st.session_state.raw_inputs = {
                        'topic_and_goal': topic_and_goal, 'jurisdiction': jurisdiction,
                        'decision_maker': decision_maker, 'opposition': opposition,
                        'public_awareness': public_awareness, 'campaign_stage': campaign_stage,
                        'campaign_backing': campaign_backing,
                        'additional_context': additional_context}
                    st.session_state.stage = 'review'
                    st.rerun()

    # ── REVIEW STAGE ──────────────────────────────────────────────────────────
    elif st.session_state.stage == 'review':
        intake = st.session_state.intake
        st.markdown('<div class="section-label">Review: how we read your campaign</div>', unsafe_allow_html=True)
        st.markdown("Before we search for precedents, check that we've understood your campaign correctly. "
                    "Confirm the matching categories below, and if anything else looks wrong, go back and adjust.")

        st.markdown(f"""
        <div class="profile-box">
          <strong>Campaign summary:</strong> {esc(intake.get('campaign_summary', ''))}
        </div>
        """, unsafe_allow_html=True)

        cats = intake.get('categories', {}) or {}
        st.markdown('<div class="section-label" style="font-size:0.9rem;">Matching categories — confirm or adjust</div>',
                    unsafe_allow_html=True)

        with st.expander("What do these mean?"):
            st.markdown("""
**Target type** — who has to change for you to win. A *Corporation* (a company or group of
companies), a *Government* (parliament, a minister, a regulator), or *Consumers* (many members
of the public). This is the single most important classification: precedents with a different
target type are excluded, because a campaign to move a supermarket works nothing like a campaign
to move a parliament.

**Primary mechanism** — the main lever you are pulling. *Market pressure* (reputational or
commercial pressure on a business), *Policy/legal* (legislation, regulation, the courts), or
*Cultural shift* (changing what the public believes or expects).

**Decision-making concentration** — how many people must say yes. *Highly concentrated* is one
or a few decision-makers, *Diffuse* is very many independent ones.

**Public sentiment starting point** — where the public was before you began, not where you
hope to get them.
""")

        cc1, cc2 = st.columns(2)
        with cc1:
            conf_target = st.selectbox("Who must change? (target type)", TARGET_TYPES,
                                       index=_idx(TARGET_TYPES, cats.get('target_type')), key="cat_target")
            conf_conc = st.selectbox("Decision-making concentration", CONCENTRATION_LEVELS,
                                     index=_idx(CONCENTRATION_LEVELS, cats.get('concentration')), key="cat_conc")
            conf_opp = st.selectbox("Strength of opposition", OPPOSITION_LEVELS,
                                    index=_idx(OPPOSITION_LEVELS, cats.get('opposition_strength')),
                                    key="cat_opp",
                                    help="How resourced and entrenched is the opposition. "
                                         "Set from your answer; change it here if it's wrong.")
        with cc2:
            conf_mech = st.selectbox("Primary mechanism", MECHANISMS,
                                     index=_idx(MECHANISMS, cats.get('primary_mechanism')), key="cat_mech")
            conf_sent = st.selectbox("Public sentiment starting point", PUBLIC_SENTIMENT_CATEGORIES,
                                     index=_idx(PUBLIC_SENTIMENT_CATEGORIES, cats.get('public_sentiment')),
                                     key="cat_sent",
                                     help="Set from your awareness answer. Change it here if it's wrong.")

        profile = intake.get('profile', {})
        with st.expander("See how we read your campaign across all 14 dimensions"):
            st.markdown(
                "This is how your campaign has been read across the fourteen dimensions we use "
                "to find precedents. You can adjust the four key categories directly in the "
                "dropdowns above. If any of the other dimensions look wrong, go back and reword "
                "your original answers, then search for precedents.")
            st.markdown("")
            for key, label in PROFILE_LABELS.items():
                value = profile.get(key, "Not assessed")
                col1, col2 = st.columns([2, 3])
                with col1:
                    st.markdown(f'<p style="color:#6b6560; font-size:0.85rem; margin:0; padding:0.4rem 0;">{esc(label)}</p>',
                                unsafe_allow_html=True)
                with col2:
                    st.markdown(f'<p style="color:#1a1a1a; font-size:0.85rem; margin:0; padding:0.4rem 0;">{esc(value)}</p>',
                                unsafe_allow_html=True)
                st.markdown('<hr style="margin:0; border:none; border-top:1px solid #d8d4c8;">', unsafe_allow_html=True)

        st.markdown("")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✓ This looks right — find precedents", key="review_continue"):
                with st.spinner("Matching against precedents..."):
                    classifications, passing, excluded, flag_map = compute_gates(df, conf_target, conf_mech)
                    if not passing:
                        st.warning(f"No precedent campaigns share your campaign's target type "
                                   f"({conf_target}), so there is nothing structurally comparable to show yet.")
                        with st.expander("Gate detail (all campaigns)"):
                            for g in classifications:
                                st.markdown(f"✕ **{g['campaign']}** — {g['gate_reasoning']}")
                        return

                    st.session_state['usage_log'] = []
                    cats = {'target': conf_target, 'mechanism': conf_mech,
                            'concentration': conf_conc, 'public_sentiment': conf_sent,
                            'opposition': conf_opp}
                    ckey = cache_key(st.session_state.get("raw_inputs", {}), cats)
                    all_scores_raw = cache_load(ckey)
                    if all_scores_raw is not None:
                        st.session_state['cache_status'] = f"HIT ({ckey[:8]}) — identical inputs, stored result reused"
                    else:
                        all_scores_raw = run_ranking_in_batches(
                            df, passing, conc_map, intake, conf_conc, conf_sent, enabler_map,
                            opp_map, conf_opp)
                        if all_scores_raw:
                            cache_save(ckey, all_scores_raw)
                        st.session_state['cache_status'] = f"MISS ({ckey[:8]}) — scored fresh and stored"

                    if not all_scores_raw:
                        st.error("Ranking returned no scored campaigns.")
                        return

                    scored_names = {resolve_oracle_name(df, c.get('campaign', '')) for c in all_scores_raw}
                    missing = [n for n in passing if n not in scored_names]
                    if missing:
                        st.warning("⚠ These gate-passing campaigns were not scored: " + ", ".join(missing))

                    (all_scores_processed, rankings, partials, below_threshold,
                     mismatch_notes, provenance_issues) = process_all_scores(
                        all_scores_raw, df, conc_map, conf_conc, flag_map, enabler_map,
                        opp_map, conf_opp)

                    if provenance_issues:
                        st.warning(
                            f"⚠ **Institutional Environment:** {len(provenance_issues)} enabler "
                            f"naming issue(s). Unpinned entries were dropped so they cannot affect "
                            f"the score. See the debug expander.")

                    if not rankings and not partials:
                        st.warning("No campaigns met the matching threshold for your campaign profile.")

                    st.session_state.rankings = rankings
                    st.session_state.partials = partials
                    st.session_state.all_scores_processed = all_scores_processed
                    st.session_state.below_threshold = below_threshold
                    st.session_state.excluded_by_gate = excluded
                    st.session_state.gate_classifications = classifications
                    st.session_state.alignment_mismatches = mismatch_notes
                    st.session_state.provenance_issues = provenance_issues
                    st.session_state.user_categories = {
                        'target': conf_target, 'mechanism': conf_mech,
                        'concentration': conf_conc, 'public_sentiment': conf_sent,
                        'opposition': conf_opp}
                    st.session_state.stage = 'results'
                    st.rerun()
        with col2:
            if st.button("← Go back and adjust inputs", key="review_back"):
                st.session_state.stage = 'input'
                st.rerun()

    # ── RESULTS STAGE ─────────────────────────────────────────────────────────
    elif st.session_state.stage == 'results':
        intake = st.session_state.intake
        rankings = st.session_state.get('rankings', [])
        partials = st.session_state.get('partials', [])

        st.markdown('<div class="section-label">Precedent matches</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="profile-box">
          <strong>Your campaign:</strong> {esc(intake.get('campaign_summary', ''))}
        </div>
        """, unsafe_allow_html=True)

        # FIX #25 — concise guidance: the four dimensions, their variables, and the colour legend.
        with st.expander("How to read these results"):
            st.markdown("""
Each precedent is scored on **four dimensions**. Each dimension holds a few variables, and every
variable is judged **equivalent** or **diverges**. Fewer divergences means a closer structural match.

| Dimension | Weight | What it covers |
|---|---|---|
| **Change Architecture** | 35% | Target type · concentration of decision-making · primary mechanism · degree of behaviour change required |
| **Resistance Architecture** | 25% | Strength of opposition · type of opposition · economic disruption required |
| **Persuasion Architecture** | 20% | Public sentiment starting point · visibility of harm · narrative dominance |
| **Institutional Environment** | 20% | Regulatory position · coalition · institutional backing · financial resources · expert validation |

**Institutional Environment** compares only the supports that precedent actually relied on, so the
number of variables differs between precedents. If your profile doesn't mention one, it is treated
as absent and the reasoning says so — worth correcting if it's wrong.

**Colours**

- **Dimension alignment** — green **Strong** (no divergences) · amber **Moderate** (one) · pink **Weak** (two or more)
- **Match tier** — the overall verdict: green **Strong** · amber **Moderate** · blue **Limited** (a weaker fit, not a warning)
""")

        dim_labels = {
            'change_architecture':       ('Change Architecture',       '35%', 'Who is targeted and how the campaign aims to move them'),
            'resistance_architecture':   ('Resistance Architecture',   '25%', 'The strength and form of opposition your campaign will face'),
            'persuasion_architecture':   ('Persuasion Architecture',   '20%', 'The public and narrative environment your campaign operates in'),
            'institutional_environment': ('Institutional Environment', '20%', 'The structural conditions and allies available to your campaign'),
        }

        # FIX #18 — Strong muted green, Moderate muted yellow, Weak muted pink
        align_styles = {
            'Strong':   ('color:#2E7D32; font-weight:600;', '●', '#A5D6A7'),
            'Moderate': ('color:#8D6E00; font-weight:600;', '●', '#FFE082'),
            'Weak':     ('color:#AD1457; font-weight:600;', '●', '#F8BBD0'),
        }
        # FIX #27 — Limited is neutral stone. It means weaker fit, not warning.
        tier_styles = {
            'Strong structural match':   ('background:#2E7D32; color:#ffffff; border:1px solid #1B5E20;', '●'),
            'Moderate structural match': ('background:#FFCC02; color:#33261D; border:1px solid #F9A825;', '●'),
            'Limited structural match':  ('background:#5E7B99; color:#ffffff; border:1px solid #4A6480;', '●'),
        }

        def render_match_card(m, key_prefix, partial=False):
            match_tier = m.get('match_tier', 'Moderate structural match')
            tier_style, tier_dot = tier_styles.get(match_tier, tier_styles['Moderate structural match'])
            gate_html = ''
            if m.get('gate_flag') == 'marginal':
                gate_html = (' &nbsp;<span style="font-size:0.65rem; font-family:\'Cabinet Grotesk\',sans-serif; '
                             'background:#fffbe8; color:#8a6e00; border:0.5px solid #c8a000; '
                             'padding:0.1rem 0.35rem; border-radius:2px;">⚠ MARGINAL MECHANISM</span>')

            st.markdown(f"""
            <div class="match-card{' partial' if partial else ''}">
              <div class="card-header">
                <div>
                  <span style="font-size:1.4rem; font-weight:700; font-family:'Cabinet Grotesk',sans-serif;
                               color:#ff4500;">#{m['rank']}</span>{gate_html}<br>
                  <h3 style="margin:0.25rem 0 0.5rem 0; font-size:1.15rem;">{esc(m['campaign'])}</h3>
                  <span style="display:inline-block; font-size:0.85rem; font-weight:500;
                               padding:5px 14px; border-radius:20px; {tier_style}">
                    {tier_dot} &nbsp;{esc(match_tier)}
                  </span>
                </div>
              </div>
              <p style="font-size:0.9rem; color:#3a3530; margin:0.7rem 0 0.4rem 0;
                        font-style:italic; line-height:1.5;">{esc(m.get('match_summary',''))}</p>
            </div>
            """, unsafe_allow_html=True)

            dim_alignment = m.get('dimension_alignment', {})
            st.markdown('<div style="background:#e8e4d8; padding:0.1rem 1.4rem 0.8rem 1.4rem; '
                        'border-radius:0 0 4px 4px; margin-top:-0.5rem;">', unsafe_allow_html=True)

            for key, (label, weight, definition) in dim_labels.items():
                dim_data = dim_alignment.get(key, {})
                alignment = dim_data.get('alignment', 'Moderate') if isinstance(dim_data, dict) else 'Moderate'
                reasoning = dim_data.get('reasoning', '') if isinstance(dim_data, dict) else str(dim_data)
                variables = dim_data.get('variables', {}) if isinstance(dim_data, dict) else {}
                a_style, a_dot, dot_color = align_styles.get(alignment, align_styles['Moderate'])

                col1, col2 = st.columns([2, 5])
                with col1:
                    # FIX #21 — the verdict is the point of this column, so it sits directly
                    # under the dimension name. Definition and weight are reference detail below.
                    st.markdown(
                        f'<div style="padding:0.45rem 0 0.1rem 0; border-top:0.5px solid #d4d0c4;">'
                        f'<span style="font-size:0.88rem; font-weight:500; color:#3a3530;">{esc(label)}</span><br>'
                        f'<span style="font-size:0.95rem; {a_style}">'
                        f'<span style="color:{dot_color};">{a_dot}</span> &nbsp;{esc(alignment)}</span><br>'
                        f'<span style="font-size:0.75rem; color:#8b8580; font-style:italic;">{esc(definition)}</span><br>'
                        f'<span style="font-size:0.78rem; color:#9b958f;">{esc(weight)} weight</span></div>',
                        unsafe_allow_html=True)
                with col2:
                    st.markdown(
                        f'<div style="padding:0.45rem 0 0.1rem 0; border-top:0.5px solid #d4d0c4;">'
                        f'<span style="font-size:0.85rem; color:#6b6560; line-height:1.5;">{esc(reasoning)}</span>'
                        f'<div style="margin-top:0.35rem;">{variable_chips_html(variables)}</div></div>',
                        unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

            # Divergence callout — surface the specific variables that diverge on an
            # otherwise-close match, so the one thing to manage is visible without drilling in.
            if not partial:
                diverging = []
                for dkey in dim_labels:
                    dd = dim_alignment.get(dkey, {})
                    dvars = dd.get('variables', {}) if isinstance(dd, dict) else {}
                    for vk, vv in dvars.items():
                        verdict = vv.get('verdict') if isinstance(vv, dict) else vv
                        if _norm(verdict) == 'diverges':
                            diverging.append(_pretty_var(vk))
                if diverging:
                    plural = 'difference' if len(diverging) == 1 else 'differences'
                    st.markdown(
                        f'<div style="background:#f5efe0; border-left:3px solid #c99a2e; '
                        f'border-radius:0 4px 4px 0; padding:0.6rem 1rem; margin:0.2rem 0 0.6rem 0;">'
                        f'<span style="font-family:\'Cabinet Grotesk\',sans-serif; font-size:0.8rem; '
                        f'font-weight:700; letter-spacing:0.3px; color:#8a6e00;">'
                        f'⚑ Key {plural} to manage</span><br>'
                        f'<span style="font-size:0.86rem; color:#4a453f;">'
                        f'This is otherwise a close structural match, but it diverges on: '
                        f'<strong>{esc(", ".join(diverging))}</strong>. See the reasoning above for '
                        f'what each means for your campaign.</span></div>',
                        unsafe_allow_html=True)

            st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

            if st.button("Deep dive →", key=f"{key_prefix}_{m['rank']}"):
                run_deep_dive(m['campaign'], m.get('match_tier', ''), m.get('match_summary', ''),
                              df, conf_df, conc_map, intake)

        if rankings:
            for m in rankings:
                render_match_card(m, "dive")
        else:
            st.info("No Strong or Moderate structural matches were found for your campaign profile.")

        # FIX #15 — partial parallels, clearly caveated
        if partials:
            st.markdown("")
            st.markdown('<div class="section-label" style="font-size:1.3rem;">Partial parallels — weaker structural fit</div>',
                        unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:0.86rem; color:#6b6560; margin:-0.4rem 0 0.9rem 0;'>"
                "These share part of your campaign's structure but diverge on two or more dimensions. "
                "Useful for tactics and cautionary reading, not for strategic read-across.</p>",
                unsafe_allow_html=True)
            for m in partials:
                render_match_card(m, "pdive", partial=True)

        # ── Full scoring expander (transparency: how campaigns were selected)
        with st.expander("Show full scoring for all campaigns"):
            gate_classifications = st.session_state.get('gate_classifications', [])
            if gate_classifications:
                st.markdown("**Gate classification — all campaigns:**")
                for g in gate_classifications:
                    icon = '✓' if g.get('gate_result') == 'pass' else '✕'
                    flag = g.get('gate_flag', '')
                    flag_label = f' [{flag.upper()}]' if flag and flag != 'clear' else ''
                    st.markdown(f"{icon} **{g['campaign']}**{flag_label} — {g.get('gate_reasoning', '')}")
                st.markdown("")

            # FIX #14 / #22 — campaigns scored but cut below the tier threshold.
            # Now shows per-variable chips and full reasoning so the cut can be audited.
            below = st.session_state.get('below_threshold', [])
            if below:
                st.markdown("**Scored but excluded below threshold (not shown to users):**")
                for c in below:
                    st.markdown(f"**{esc(c['campaign'])}** — weighted {c.get('weighted_score', 0):.2f} · "
                                f"cut because {esc(c.get('exclusion_reason', 'below threshold'))}")
                    for dim, (lbl, w, _) in dim_labels.items():
                        d = c.get('dimension_scores', {}).get(dim, {})
                        st.markdown(
                            f"<div style='margin-left:1rem; font-size:0.82rem; color:#3a3530;'>"
                            f"<strong>{esc(lbl)} ({esc(w)}):</strong> {esc(d.get('alignment','?'))} — "
                            f"{esc(d.get('reasoning',''))}<br>{variable_chips_html(d.get('variables', {}))}</div>",
                            unsafe_allow_html=True)
                    st.markdown("")

            excluded = st.session_state.get('excluded_by_gate', [])
            if excluded:
                st.markdown("**Excluded by compatibility gate:**")
                for e in excluded:
                    st.markdown(f"- {e}")
                st.markdown("")

            all_scored = st.session_state.get('all_scores_processed', [])
            if all_scored:
                st.markdown("**All qualifying campaigns (ranked order):**")
                for c in all_scored:
                    st.markdown(f"**{esc(c['campaign'])}** &nbsp;·&nbsp; {c.get('computed_tier', '—')} "
                                f"&nbsp;·&nbsp; weighted score: {c.get('weighted_score', 0):.2f}")
                    for dim, (lbl, w, _) in dim_labels.items():
                        d = c.get('dimension_scores', {}).get(dim, {})
                        st.markdown(
                            f"<div style='margin-left:1rem; font-size:0.82rem; color:#3a3530;'>"
                            f"<strong>{esc(lbl)} ({esc(w)}):</strong> {esc(d.get('alignment','?'))} — "
                            f"{esc(d.get('reasoning',''))}<br>{variable_chips_html(d.get('variables', {}))}</div>",
                            unsafe_allow_html=True)
                    st.markdown("")

        st.divider()
        if st.button("← Refine my inputs"):
            st.session_state.stage = 'input'
            st.rerun()

    # ── DEEP DIVE STAGE ───────────────────────────────────────────────────────
    elif st.session_state.stage == 'deep_dive':
        dd = st.session_state.deep_dive
        s = dd.get('sections', {}) or {}

        st.markdown('<div class="section-label">Deep dive</div>', unsafe_allow_html=True)

        match_tier = dd.get('match_tier', '')
        # FIX #27 — Limited is neutral stone here too, matching the match card.
        dive_tier_styles = {
            'Strong structural match':   'background:#2E7D32; color:#ffffff; border:1px solid #1B5E20;',
            'Moderate structural match': 'background:#FFCC02; color:#33261D; border:1px solid #F9A825;',
            'Limited structural match':  'background:#5E7B99; color:#ffffff; border:1px solid #4A6480;',
        }
        tier_style = dive_tier_styles.get(match_tier, dive_tier_styles['Moderate structural match'])

        conf_flag = dd.get('overall_conf_flag') or ''
        conf_explanation = dd.get('overall_conf_explanation') or ''
        cfl = conf_flag.strip().lower()
        # Data-quality flag chip — purple, its own colour, distinct from the match palette
        # (green/amber/pink) and from the Limited-tier steel-blue. The per-point evidence
        # bars stay slate; this overall chip is the one deliberately coloured.
        conf_chip_style = 'background:#7A3B9E; color:#ffffff; border:1px solid #5F2E7C;'

        conf_html = ''
        if conf_flag:
            conf_html = f"""
          <div style="margin-top:0.8rem; padding-top:0.8rem; border-top:1px solid #c8c4b8;">
            <span style="font-family:'Cabinet Grotesk',sans-serif; font-size:1rem; font-weight:700;
                         letter-spacing:-0.2px; color:#4a453f;">Data quality</span>
            &nbsp;
            <span style="display:inline-block; font-size:0.7rem; font-weight:500;
                         padding:2px 8px; border-radius:20px; {conf_chip_style}">{esc(conf_flag)}</span>
            <p style="margin:0.4rem 0 0 0; font-size:0.8rem; color:#6b6560; line-height:1.5;">
              {esc(conf_explanation)}
            </p>
          </div>"""

        st.markdown(f"""
        <div class="dive-header">
          <h2>{esc(dd.get('precedent_name', ''))}</h2>
          <div style="margin:0.4rem 0 0.6rem 0;">
            <span style="display:inline-block; font-size:0.75rem; font-weight:500;
                         padding:3px 12px; border-radius:20px; {tier_style}">
              ● &nbsp;{esc(match_tier)}
            </span>
          </div>
          <div class="meta">Time window: {esc(dd.get('time_window', '—'))}</div>
          <div class="meta">Outcome: {esc(dd.get('outcome', '—'))}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("What do the ‘Evidence strength’ ratings mean?"):
            st.markdown("""
The slate **Evidence strength** bars show how well *this precedent's record* is sourced — data
quality, not how strong a match it is. A poorly evidenced precedent can still be a close match,
and a well-evidenced one can be a distant one.

- **High** ▮▮▮ — stated outright in multiple independent sources.
- **Medium** ▮▮▯ — a single source, an inference, or an imperfect fit to the campaign's dates.
- **Low** ▮▯▯ — thin or indirect evidence.
""")

        if match_tier == 'Limited structural match':
            st.info("This is a partial parallel — it diverges from your campaign on two or more "
                    "structural dimensions. Read it for tactics and cautionary detail rather than "
                    "as a close strategic template.")

        campaign_desc = dd.get('campaign_description', '')
        if campaign_desc:
            st.markdown(f"""
            <div class="profile-box" style="margin-bottom:1.2rem;">
              <strong>About this precedent:</strong> {esc(campaign_desc)}
            </div>
            """, unsafe_allow_html=True)

        par = s.get('parallels', {}) or {}
        if par:
            st.markdown(f"""
            <div class="dive-section">
              <h3>{esc(par.get('title', 'Why this precedent is relevant to your campaign'))}</h3>
              <div class="intro">{esc(par.get('intro', ''))}</div>
            """, unsafe_allow_html=True)
            for p in par.get('points', []):
                st.markdown(f"""
                <div class="point-block">
                  {confidence_badge(p.get('confidence', ''))}
                  <h4>{esc(p.get('heading', ''))}</h4>
                  <p>{esc(p.get('evidence', ''))}</p>
                  <p class="relevance">↳ {esc(p.get('relevance', ''))}</p>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        diff = s.get('differences', {}) or {}
        if diff:
            st.markdown(f"""
            <div class="dive-section">
              <h3>{esc(diff.get('title', 'Where your situation differs'))}</h3>
            """, unsafe_allow_html=True)
            for p in diff.get('points', []):
                st.markdown(f"""
                <div class="point-block">
                  <h4>{esc(p.get('heading', ''))}</h4>
                  <p>{esc(p.get('evidence', ''))}</p>
                  <p class="risk">⚠ {esc(p.get('risk', ''))}</p>
                </div>
                """, unsafe_allow_html=True)
            footer = diff.get('footer', '')
            if footer:
                st.markdown(f"""
                <p style="font-size:0.78rem; color:#6b6560; font-style:italic;
                          margin-top:0.8rem; padding-top:0.8rem; border-top:1px solid #c8c4b8;">
                  ⚡ {esc(footer)}
                </p>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        tkw = s.get('takeaways', {}) or {}
        if tkw:
            st.markdown(f"""
            <div class="dive-section">
              <h3>{esc(tkw.get('title', 'What to take from it'))}</h3>
            """, unsafe_allow_html=True)
            for item in tkw.get('items', []):
                inferred_html = ('<span class="inference-flag">INFERRED</span>'
                                 if item.get('action_inferred', False) else '')
                st.markdown(f"""
                <div class="point-block">
                  {confidence_badge(item.get('confidence', ''))}
                  <h4>{esc(item.get('number', ''))}. {esc(item.get('tactic_name', ''))}</h4>
                  <p><strong>Lesson:</strong> {esc(item.get('lesson', ''))}</p>
                  <p class="relevance"><strong>Action:</strong> {esc(item.get('action', ''))} {inferred_html}</p>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        if conf_html:
            st.markdown(conf_html, unsafe_allow_html=True)

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to all matches"):
                st.session_state.stage = 'results'
                st.rerun()
        with col2:
            if st.button("Start a new search"):
                reset()
                st.rerun()


def run_deep_dive(campaign_name, match_tier, match_summary, df, conf_df, conc_map, intake):
    with st.spinner(f"Building deep dive for {campaign_name}..."):
        oracle_name = resolve_oracle_name(df, campaign_name)
        try:
            list_a_data = get_list_a_string(df, campaign_name)
        except ValueError as e:
            st.error(f"Could not find campaign in database: {e}")
            return

        confidence_data = get_confidence_for_campaign(conf_df, oracle_name)
        overall_conf_flag, overall_conf_explanation = get_overall_confidence(conf_df, oracle_name)
        raw_tactics = get_notable_tactics(df, campaign_name) or "Not available."
        time_window, outcome = get_time_window_and_outcome(df, campaign_name)
        user_cats = st.session_state.get('user_categories', {})

        prompt = DEEP_DIVE_PROMPT.format(
            campaign_summary=intake.get('campaign_summary', ''),
            jurisdiction=intake.get('jurisdiction', ''),
            campaign_stage=intake.get('campaign_stage', ''),
            structural_profile=json.dumps(intake.get('profile', {}), indent=2),
            user_concentration=user_cats.get('concentration', 'Not stated'),
            match_summary=match_summary,
            precedent_list_a=list_a_data,
            precedent_concentration=conc_map.get(oracle_name, 'Not stated'),
            notable_tactics=raw_tactics,
            confidence_data=confidence_data)

        response = call_llm(prompt, max_tokens=8192, system=SYSTEM_PROMPT,
                            label=f"deep dive: {campaign_name[:40]}")
        result = parse_json(response, label=f"deep dive for {campaign_name}")

        if result:
            result['match_tier'] = match_tier
            result['overall_conf_flag'] = overall_conf_flag
            result['overall_conf_explanation'] = overall_conf_explanation
            result['time_window'] = time_window or '-'
            result['outcome'] = outcome or '-'

            tactics_in_response = [{'name': item.get('tactic_name', '')}
                                   for item in result.get('sections', {}).get('takeaways', {}).get('items', [])]
            suspicious = check_tactic_hallucinations(tactics_in_response, raw_tactics)
            if suspicious:
                st.warning(f"**Tactic name check:** {len(suspicious)} tactic(s) in the deep dive "
                           f"may be paraphrased or hallucinated - their names don't closely match "
                           f"Variable 15 in the database. Check these before using:\n\n"
                           + "\n".join(f"- *{t}*" for t in suspicious))

            st.session_state.deep_dive = result
            st.session_state.stage = 'deep_dive'
            st.rerun()


if __name__ == "__main__":
    main()