"""
dashboard.py
============
Streamlit dashboard for the African Recipes Nutritional Risk project.

Four pages (st.navigation):
  🏠 Home             — landing page
  🧪 Check a recipe   — live recipe input form
  📖 Explore recipes  — search/browse the scored dataset
  📊 Insights         — dataset-wide analytics

Run from african_recipes_nutrition/:
    streamlit run dashboard.py
"""

import base64
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "African Recipes — Nutritional Risk Analyser & Explorer",
    page_icon   = "🍲",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

# ── PotWise look: fonts + component CSS (injected once) ────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Caprasimo&family=Figtree:wght@400;600;700&display=swap');

html, body, [class*="css"], .stMarkdown { font-family: 'Figtree', sans-serif; }
h1, h2, h3, h4 { font-family: 'Caprasimo', serif !important; font-weight: 400 !important; }

/* pill buttons */
.stButton > button {
  border-radius: 999px !important;
  font-family: 'Caprasimo', serif;
  padding: 0.6rem 1.6rem;
}
/* rounded inputs */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
  border-radius: 16px !important; background: #ebddc5 !important;
}
/* hide Streamlit chrome for a cleaner look */
#MainMenu, footer { visibility: hidden; }

/* reusable classes for HTML cards */
.pw-card { background:#ebddc5; border-radius:32px; padding:20px 24px; }
.pw-badge { display:inline-block; border-radius:12px; padding:3px 10px;
            font-size:12px; font-weight:700; color:#fff; }
.pw-low { background:#728157; }
.pw-med { background:#d67f48; }
.pw-high { background:#643312; color:#ffe1d0; }
.pw-vhigh { background:#2e2b25; color:#ffc6a5; }
.pw-photo { width:100%; height:150px; object-fit:cover; border-radius:24px 24px 0 0; }
</style>
""", unsafe_allow_html=True)

BASE         = os.path.dirname(os.path.abspath(__file__))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
DATA_OUTPUT  = os.path.join(BASE, 'data', 'outputs')

# ── Colour palette ────────────────────────────────────────────────────────────
RISK_COLOURS = {
    "Low"            : "#27ae60",
    "Medium"         : "#f39c12",
    "High"           : "#e74c3c",
    "Very High"      : "#922b21",
    "insufficient_data": "#95a5a6",
    "n/a"            : "#bdc3c7",
}
NUTRIENT_COLOURS = {
    "low"    : "#27ae60",
    "medium" : "#f39c12",
    "high"   : "#e74c3c",
}

# ── Per-nutrient thresholds (mirrors scoring script) ──────────────────────────
_THRESH = {
    'energy_kcal': dict(medium=500,  high=800),
    'sodium_mg'  : dict(medium=400,  high=700),
    'fat_g'      : dict(medium=15,   high=25),
    'sugars_g'   : dict(medium=12,   high=20),
    'protein_g'  : dict(medium=15,   high=8),   # inverted
}

RISK_CLASS = {"Low": "pw-low", "Medium": "pw-med", "High": "pw-high", "Very High": "pw-vhigh"}
DOT_COLOUR = {"low": "#728157", "medium": "#d67f48", "high": "#643312"}

# Plain-English sentence per nutrient per risk band ('low' risk = good, 'high' risk = bad —
# already true for protein_risk too, since classify_nutrient() inverts the comparison).
NUTRIENT_SENTENCES = {
    "energy_kcal": {
        "low":    "Energy is in a comfortable range for one serving.",
        "medium": "A little calorie-dense — fine occasionally, not an everyday portion.",
        "high":   "Very calorie-dense per serving — a smaller portion or lighter sides would help.",
    },
    "sodium_mg": {
        "low":    "Salt is well within a healthy range.",
        "medium": "Salt is creeping up — go easy on extra bouillon or added salt next time.",
        "high":   "Very salty per serving — worth watching, given how common high blood pressure is across Africa.",
    },
    "fat_g": {
        "low":    "Fat content is modest.",
        "medium": "Moderately rich — keep an eye on how much oil goes in.",
        "high":   "High in fat — likely from oil, palm oil, or fatty cuts of meat.",
    },
    "sugars_g": {
        "low":    "Sugar is low — good.",
        "medium": "Some added sugar in there — not alarming, just worth noting.",
        "high":   "Quite sugary for a savoury dish — worth checking where the sugar's coming from.",
    },
    "protein_g": {
        "low":    "Good protein content — this will be filling.",
        "medium": "Decent protein, but not a stand-out source.",
        "high":   "Low on protein — this dish alone won't be very filling.",
    },
}

# Tip shown when a nutrient comes back flagged
NUTRIENT_TIPS = {
    "sodium_mg":  "Try halving the bouillon cube (or using a low-sodium one) and lean on herbs and spices instead of extra salt.",
    "fat_g":      "Cut the oil or palm oil by about a third, or trim visible fat off the meat before cooking.",
    "energy_kcal":"Serve with a lighter side — salad or steamed greens instead of extra starch — to bring the calories down.",
    "sugars_g":   "Check whether the sugar is doing anything for the dish — many savoury stews don't need it.",
    "protein_g":  "Add a handful of beans, lentils, or extra meat/fish to boost the protein.",
}


def _plain_verdict(risk):
    """One-sentence, jargon-free summary of a recipe's risk profile."""
    order = [
        ("sodium_risk", "salty"),
        ("fat_risk",    "fatty"),
        ("energy_risk", "calorie-dense"),
        ("sugar_risk",  "sugary"),
        ("protein_risk","low on protein"),
    ]
    high = [word for col, word in order if risk.get(col) == "high"]
    med  = [word for col, word in order if risk.get(col) == "medium"]

    def _join(words):
        if len(words) == 1:
            return words[0]
        return ", ".join(words[:-1]) + f", and {words[-1]}"

    if risk["weighted_risk_level"] == "Low":
        return "A well-balanced dish — nothing here stands out as a concern."
    if high:
        return f"A good meal overall, but quite {_join(high)}."
    if med:
        return f"A decent meal — just a little {_join(med)}."
    return "A reasonably balanced dish."


def _nutrient_risk_score(nutrient, value):
    """0.0 = no risk → 1.0 = maximum risk (same logic as scoring script)."""
    t = _THRESH[nutrient]
    if nutrient == 'protein_g':
        if value >= t['medium']:  return 0.0
        elif value >= t['high']:  return 0.5 * (t['medium'] - value) / (t['medium'] - t['high'])
        else:                     return min(0.5 + 0.5 * (t['high'] - value) / max(t['high'], 1e-9), 1.0)
    else:
        if value <= t['medium']:  return 0.0
        elif value <= t['high']:  return 0.5 * (value - t['medium']) / (t['high'] - t['medium'])
        else:                     return min(0.5 + 0.5 * (value - t['high']) / max(t['high'], 1e-9), 1.0)


def _render_nutrition_label(nutrition, risk, servings):
    """
    Return an HTML string styled as an FDA 2020 Nutrition Facts panel.

    Each nutrient row gets a traffic-light dot (green / amber / red) driven
    by the same _nutrient_risk_score() thresholds used everywhere else in the
    dashboard — so the colours are always consistent.
    """
    # FDA 2020 daily reference values for a 2 000 kcal diet
    DV = {
        'energy_kcal':   2000.0,
        'fat_g':           78.0,
        'carbohydrate_g': 275.0,
        'sugars_g':        50.0,
        'protein_g':       50.0,
        'sodium_mg':     2300.0,
    }

    def _dot(key, val):
        """Coloured circle indicating low / moderate / high risk for one nutrient."""
        if key not in _THRESH:
            return ""
        score = _nutrient_risk_score(key, val)
        colour = "#27ae60" if score < 0.25 else "#f39c12" if score < 0.5 else "#e74c3c"
        return (
            f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background:{colour};margin-right:5px;vertical-align:middle;"></span>'
        )

    def _pct(key, val):
        return f"{round(val / DV[key] * 100)}%" if DV.get(key) else ""

    kcal = float(nutrition['energy_kcal'])
    fat  = float(nutrition['fat_g'])
    carb = float(nutrition['carbohydrate_g'])
    sug  = float(nutrition['sugars_g'])
    prot = float(nutrition['protein_g'])
    sod  = float(nutrition['sodium_mg'])

    # Each tuple: (display name, raw value, threshold key, formatted amount, % DV, is-indented)
    nutrient_rows = [
        ("Total Fat",       fat,  "fat_g",          f"{fat:.1f} g",   _pct("fat_g",  fat),           False),
        ("Sodium",          sod,  "sodium_mg",       f"{sod:.0f} mg",  _pct("sodium_mg",       sod),  False),
        ("Carbohydrate",    carb, "carbohydrate_g",  f"{carb:.1f} g",  _pct("carbohydrate_g",  carb), False),
        ("Total Sugars",    sug,  "sugars_g",        f"{sug:.1f} g",   "",                            True),
        ("Protein",         prot, "protein_g",       f"{prot:.1f} g",  _pct("protein_g",       prot), False),
    ]

    rows_html = ""
    for name, val, key, amt, dv_pct, indented in nutrient_rows:
        dot  = _dot(key, val)
        bold = "" if indented else "font-weight:700;"
        pad  = "padding-left:14px;" if indented else ""
        rows_html += (
            f'<tr style="border-top:1px solid #000;">'
            f'<td style="padding:3px 2px;font-size:13px;{bold}{pad}">{dot}{name}</td>'
            f'<td style="padding:3px 2px;font-size:13px;white-space:nowrap;text-align:right;">{amt}</td>'
            f'<td style="padding:3px 2px;font-size:13px;font-weight:700;white-space:nowrap;text-align:right;">{dv_pct}</td>'
            f'</tr>'
        )

    legend_dot = lambda c: (
        f'<span style="display:inline-block;width:9px;height:9px;'
        f'border-radius:50%;background:{c};margin-right:4px;vertical-align:middle;"></span>'
    )

    return f"""
<div style="border:3px solid #000;padding:10px 12px;width:100%;box-sizing:border-box;
            font-family:Arial,Helvetica,sans-serif;background:#fff;color:#000;border-radius:2px;">
  <div style="font-size:24px;font-weight:900;line-height:1.05;">Nutrition Facts</div>
  <div style="font-size:12px;margin-top:3px;">{servings} serving(s) per recipe</div>
  <table style="width:100%;border-collapse:collapse;margin-top:2px;">
    <tr>
      <td style="font-size:12px;font-weight:700;">Serving size</td>
      <td style="font-size:12px;font-weight:700;text-align:right;">1 serving</td>
    </tr>
  </table>
  <div style="border-top:8px solid #000;margin:5px 0 3px 0;"></div>
  <div style="font-size:11px;font-weight:700;margin-bottom:1px;">Amount per serving</div>
  <table style="width:100%;border-collapse:collapse;">
    <tr>
      <td style="font-size:26px;font-weight:900;line-height:1.1;padding:0 2px;">Calories</td>
      <td style="font-size:38px;font-weight:900;line-height:1.1;text-align:right;padding:0 2px;">{kcal:.0f}</td>
    </tr>
  </table>
  <div style="border-top:4px solid #000;margin:4px 0 2px 0;"></div>
  <div style="text-align:right;font-size:11px;font-weight:700;">% Daily Value*</div>
  <table style="width:100%;border-collapse:collapse;">{rows_html}</table>
  <div style="border-top:6px solid #000;margin:5px 0 4px 0;"></div>
  <div style="font-size:10px;line-height:1.6;">
    * % Daily Values based on a 2,000 calorie diet.<br>
    Na 2,300 mg &middot; Fat 78 g &middot; Carbs 275 g &middot; Sugars 50 g &middot; Protein 50 g
  </div>
  <div style="margin-top:6px;font-size:11px;">
    {legend_dot("#27ae60")}Low &nbsp;
    {legend_dot("#f39c12")}Moderate &nbsp;
    {legend_dot("#e74c3c")}High risk
  </div>
</div>
"""


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv(os.path.join(DATA_OUTPUT, 'recipe_risk_scores.csv'))
    scored = df[df['data_status'] == 'calculated'].copy()
    insuf  = df[df['data_status'] == 'insufficient_data'].copy()
    num_cols = ['energy_kcal','protein_g','fat_g','carbohydrate_g',
                'sugars_g','sodium_mg','ingredient_coverage_pct',
                'flag_count','weighted_risk_score']
    for col in num_cols:
        scored[col] = pd.to_numeric(scored[col], errors='coerce')
    return df, scored, insuf


# ── Live analyser (cached so USDA data loads only once per session) ───────────
#
# TEACHING NOTE — why @st.cache_resource?
#   @st.cache_data  : caches pure data (DataFrames, dicts).  Re-runs when inputs change.
#   @st.cache_resource : caches objects like database connections or ML models that
#                        are expensive to create and should persist for the whole session.
#   LiveAnalyser loads food_nutrient.csv (~150 MB), so we definitely only want to do
#   that once.  @st.cache_resource is the right choice here.
@st.cache_resource
def get_live_analyser():
    from pipeline.live_analysis import LiveAnalyser
    return LiveAnalyser()


df_all, df, df_insuf = load_data()


def render_sidebar_filters():
    """Risk filters shown in the sidebar — only used by the Explore recipes page."""
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/cooking-pot.png", width=60)
        st.title("Filters")

        flag_filter = st.multiselect(
            "Flag-count risk level",
            options=["Low","Medium","High"],
            default=["Low","Medium","High"],
            key="flag_filter",
        )
        wt_filter = st.multiselect(
            "Weighted risk level",
            options=["Low","Medium","High","Very High"],
            default=["Low","Medium","High","Very High"],
            key="wt_filter",
        )
        coverage_min = st.slider(
            "Min ingredient coverage (%)",
            min_value=0, max_value=100, value=0, step=5,
            key="coverage_min",
        )
        show_insuf = st.checkbox("Include insufficient-data recipes in table", value=False, key="show_insuf")

        st.divider()
        st.caption("Scoring basis: WHO dietary guidelines per serving (⅓ daily intake). "
                   "Sodium weighted 30 % in weighted score due to high hypertension burden in Africa.")

    df_f = df[
        (df['flag_risk_level'].isin(flag_filter)) &
        (df['weighted_risk_level'].isin(wt_filter)) &
        (df['ingredient_coverage_pct'] >= coverage_min)
    ]
    return df_f, show_insuf


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Home
# ═════════════════════════════════════════════════════════════════════════════
def home():
    st.markdown(
        "<h1 style='margin-bottom:0'>Know what's in the pot.</h1>"
        "<p style='font-size:1.05rem;max-width:640px;color:#5b5650;'>"
        "Paste any African recipe's ingredient list and we'll tell you — in plain English — "
        f"how it stacks up against WHO nutrition guidelines. Or browse {len(df_all)} recipes "
        "we've already scored."
        "</p>",
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns(2)
    if b1.button("Check a recipe", type="primary", use_container_width=True):
        st.switch_page(pages["check"])
    if b2.button("Explore recipes", use_container_width=True):
        st.switch_page(pages["explore"])

    st.markdown("")

    s1, s2, s3, s4 = st.columns(4)
    stats = [
        (s1, f"{len(df_all)}",               "Recipes in the dataset"),
        (s2, f"{len(df)}",                   "Recipes fully scored"),
        (s3, f"{df['weighted_risk_score'].mean():.0f}/100", "Average risk score"),
        (s4, f"{int((df['flag_risk_level'] == 'High').sum())}", "Flagged high-risk"),
    ]
    for col, big, caption in stats:
        col.markdown(
            f'<div class="pw-card" style="text-align:center;">'
            f'<div style="font-family:\'Caprasimo\',serif;font-size:2rem;">{big}</div>'
            f'<div style="font-size:0.85rem;color:#5b5650;">{caption}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.markdown("### How it works")
    h1, h2, h3 = st.columns(3)
    steps = [
        (h1, "1", "Paste your ingredients",
         "One per line, with rough amounts — 2 cups rice, 500g chicken, that kind of thing."),
        (h2, "2", "We match them to real nutrition data",
         "Every ingredient is matched against the USDA food database and scaled to your servings."),
        (h3, "3", "Get a plain-English verdict",
         "No jargon — just what's high, what's fine, and simple tips to make it healthier."),
    ]
    for col, num, title, body in steps:
        col.markdown(
            f'<div class="pw-card">'
            f'<div style="display:inline-block;background:#c67139;color:#fff;border-radius:50%;'
            f'width:28px;height:28px;text-align:center;line-height:28px;font-weight:700;">{num}</div>'
            f'<h4 style="margin:10px 0 4px 0;">{title}</h4>'
            f'<p style="font-size:0.9rem;color:#5b5650;margin:0;">{body}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    good_pct = (df['weighted_risk_level'].isin(['Low', 'Medium'])).mean() * 100
    st.markdown(
        f'<div class="pw-card" style="background:#e1eecc;">'
        f"<b>The good news first:</b> {good_pct:.0f}% of the recipes we've scored come out Low or "
        f"Medium risk. Traditional African cooking isn't the problem — a handful of specific "
        f"ingredients (bouillon cubes, palm oil, added salt) are what push a dish into high-risk "
        f"territory, and they're usually easy to dial back."
        f'</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Insights (dataset-wide analytics, moved from the old Dataset Explorer tab)
# ═════════════════════════════════════════════════════════════════════════════
def insights():
    st.title("🍲 African Recipes — Insights")
    st.caption("What the data actually shows, in plain English. "
               "The technical methodology and model scores are in the expander at the bottom.")

    st.divider()

    # ── Stat strip ────────────────────────────────────────────────────────────
    s1, s2, s3, s4 = st.columns(4)
    stat_tiles = [
        (s1, f"{len(df_all)}", "Recipes in the dataset"),
        (s2, f"{len(df)}",     "Fully scored"),
        (s3, f"{df['weighted_risk_score'].mean():.0f}/100", "Average risk score"),
        (s4, f"{(df['weighted_risk_level'].isin(['Low', 'Medium'])).mean()*100:.0f}%", "Low or Medium risk"),
    ]
    for col, big, caption in stat_tiles:
        col.markdown(
            f'<div class="pw-card" style="text-align:center;">'
            f'<div style="font-family:\'Caprasimo\',serif;font-size:2rem;">{big}</div>'
            f'<div style="font-size:0.85rem;color:#5b5650;">{caption}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.markdown("### Findings")

    high_mask = df['weighted_risk_level'].isin(['High', 'Very High'])
    n_high = int(high_mask.sum())
    pct_fat_among_high    = (df.loc[high_mask, 'fat_risk'] == 'high').mean() * 100 if n_high else 0
    pct_sodium_among_high = (df.loc[high_mask, 'sodium_risk'] == 'high').mean() * 100 if n_high else 0
    pct_low_medium   = (df['weighted_risk_level'].isin(['Low', 'Medium'])).mean() * 100
    pct_low_protein  = (df['protein_risk'] == 'high').mean() * 100
    sodium_high      = df['sodium_risk'] == 'high'
    pct_fat_given_na = (df.loc[sodium_high, 'fat_risk'] == 'high').mean() * 100 if sodium_high.any() else 0

    findings = [
        ("FINDING 01", f"{pct_low_medium:.0f}% of recipes are already fine",
         "Most traditional African dishes come out Low or Medium risk once you look at them "
         "per serving. The high-risk cases are the exception, not the rule."),
        ("FINDING 02", "Fat and salt do almost all the damage",
         f"Among the {n_high} recipes that land in High or Very High risk, {pct_fat_among_high:.0f}% "
         f"are flagged for fat and {pct_sodium_among_high:.0f}% for sodium. Calories and sugar are "
         "rarely what tips a dish over — it's the oil and the seasoning."),
        ("FINDING 03", f"{pct_low_protein:.0f}% of recipes are light on protein",
         "Per serving, most dishes in the dataset don't hit a solid protein target — often because "
         "servings are generous and the meat, fish, or legumes get spread thin, not because the "
         "recipe itself is short on protein-rich ingredients."),
        ("FINDING 04", "Salt and fat travel together",
         f"When a recipe is flagged for high sodium, it's also flagged for high fat {pct_fat_given_na:.0f}% "
         "of the time — a sign both usually come from the same source: a bouillon-and-oil cooking base."),
    ]

    finding_cols = st.columns(2) + st.columns(2)
    for col, (kicker, title, body) in zip(finding_cols, findings):
        col.markdown(
            f'<div class="pw-card">'
            f'<div style="font-size:0.75rem;font-weight:700;letter-spacing:0.05em;color:#c67139;">{kicker}</div>'
            f'<div style="font-family:\'Caprasimo\',serif;font-size:1.1rem;margin:6px 0;">{title}</div>'
            f'<div style="color:#5b5650;font-size:0.9rem;">{body}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Risk distribution — plain HTML bars, no charting library needed ───────
    st.subheader("Risk Distribution")

    def _risk_bar_card(title, counts, order):
        total = counts.sum()
        rows = ""
        for level in order:
            count  = int(counts.get(level, 0))
            pct    = count / total * 100 if total else 0
            colour = RISK_COLOURS.get(level, '#95a5a6')
            rows += (
                '<div style="margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;font-size:0.85rem;">'
                f'<span>{level}</span><span>{count} ({pct:.0f}%)</span></div>'
                '<div style="background:#ded2ba;border-radius:6px;height:10px;overflow:hidden;">'
                f'<div style="width:{pct:.1f}%;background:{colour};height:100%;"></div></div>'
                '</div>'
            )
        return f'<div class="pw-card"><div style="font-weight:700;margin-bottom:10px;">{title}</div>{rows}</div>'

    c1, c2 = st.columns(2)
    c1.markdown(
        _risk_bar_card("Flag-Count Method", df['flag_risk_level'].value_counts(), ['Low', 'Medium', 'High']),
        unsafe_allow_html=True,
    )
    c2.markdown(
        _risk_bar_card("Weighted-Score Method", df['weighted_risk_level'].value_counts(),
                       ['Low', 'Medium', 'High', 'Very High']),
        unsafe_allow_html=True,
    )

    st.markdown("")

    # ── Per-nutrient risk breakdown — plain HTML stacked bars ─────────────────
    st.subheader("Per-Nutrient Risk Breakdown")

    total = len(df)
    nutrient_bars = ""
    for risk_col, label in [
        ('energy_risk', 'Energy'), ('sodium_risk', 'Sodium'), ('fat_risk', 'Fat'),
        ('sugar_risk', 'Sugars'), ('protein_risk', 'Protein'),
    ]:
        counts = df[risk_col].value_counts()
        pl = counts.get('low', 0) / total * 100 if total else 0
        pm = counts.get('medium', 0) / total * 100 if total else 0
        ph = counts.get('high', 0) / total * 100 if total else 0
        nutrient_bars += (
            '<div style="margin-bottom:12px;">'
            f'<div style="font-size:0.85rem;font-weight:700;margin-bottom:4px;">{label}</div>'
            '<div style="display:flex;border-radius:6px;overflow:hidden;height:14px;">'
            f'<div style="width:{pl:.1f}%;background:{NUTRIENT_COLOURS["low"]};"></div>'
            f'<div style="width:{pm:.1f}%;background:{NUTRIENT_COLOURS["medium"]};"></div>'
            f'<div style="width:{ph:.1f}%;background:{NUTRIENT_COLOURS["high"]};"></div>'
            '</div></div>'
        )
    st.markdown(f'<div class="pw-card">{nutrient_bars}</div>', unsafe_allow_html=True)
    st.caption("Each bar: share of recipes Low risk (green) · Medium (amber) · High (red) for that nutrient.")

    st.divider()

    # ── For the data-curious ────────────────────────────────────────────────────
    with st.expander("For the data-curious: methods & models"):
        st.markdown(
            "**Two risk-scoring methods**\n\n"
            "- **Flag Count** — counts how many of the 5 nutrients (energy, sodium, fat, sugar, protein) "
            "breach the WHO-derived high-risk threshold for that recipe. Simple and easy to explain.\n"
            "- **Weighted Score** — a 0–100 score that weights nutrients by public-health priority: "
            "**Sodium 30%, Energy 25%, Fat 20%, Sugar 15%, Protein 10%.** Sodium is weighted highest "
            "because of the high burden of hypertension across Africa.\n\n"
            "Thresholds are set per serving, at ⅓ of the WHO daily reference intake "
            "(e.g. sodium: 700 mg/serving, ⅓ of the 2 000 mg/day limit)."
        )

        st.markdown("**Predictive models** — can risk level be predicted from macros alone?")
        st.markdown(
            "- Logistic Regression — macro-F1 **0.797** on held-out test data\n"
            "- Random Forest (tuned) — macro-F1 **0.854** on held-out test data (best cross-validated: 0.895)\n\n"
            "Macro-F1, not accuracy, is the headline metric because risk levels are imbalanced — "
            "74.6% of recipes are Low risk, so a model that guessed \"Low\" every time would already "
            "look accurate without being useful."
        )

        st.markdown("**Limitations**")
        st.markdown(
            f"- {len(df_insuf)} recipes have *insufficient data* — too few ingredients matched the "
            "USDA database to score reliably — and are excluded from everything above.\n"
            "- Nutrition totals depend on ingredient-to-USDA matching quality; low-coverage recipes "
            "will under-estimate their true nutrient content.\n"
            "- Scores are per serving as written in the recipe — unrealistically large serving sizes "
            "will make a recipe look artificially healthy."
        )

        st.divider()
        st.markdown("**Deeper drill-down charts**")

        fig_scatter = px.scatter(
            df,
            x='energy_kcal', y='sodium_mg',
            size='fat_g', size_max=40,
            color='weighted_risk_level',
            color_discrete_map=RISK_COLOURS,
            hover_name='recipe_name',
            hover_data={
                'energy_kcal': ':.0f',
                'sodium_mg'  : ':.0f',
                'fat_g'      : ':.1f',
                'protein_g'  : ':.1f',
                'weighted_risk_score': ':.1f',
                'weighted_risk_level': True,
            },
            labels={
                'energy_kcal'         : 'Energy (kcal / serving)',
                'sodium_mg'           : 'Sodium (mg / serving)',
                'fat_g'               : 'Fat (g)',
                'weighted_risk_level' : 'Risk Level',
                'weighted_risk_score' : 'Weighted Score',
            },
            category_orders={'weighted_risk_level': ['Low', 'Medium', 'High', 'Very High']},
            title="Energy vs Sodium per Serving (bubble size = fat)",
        )
        fig_scatter.add_vline(x=800, line_dash='dash', line_color='#e74c3c', line_width=1)
        fig_scatter.add_hline(y=700, line_dash='dash', line_color='#e74c3c', line_width=1)
        fig_scatter.update_layout(height=500, legend_title_text='Weighted Risk', margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_scatter, use_container_width=True)

        t1, t2, t3 = st.columns(3)

        def top_bar(data, x_col, title, x_label, n=10):
            top = data.nlargest(n, x_col)[['recipe_name', x_col, 'weighted_risk_level']].copy()
            top['recipe_name'] = top['recipe_name'].str[:40]
            fig = px.bar(
                top, x=x_col, y='recipe_name', orientation='h',
                color='weighted_risk_level',
                color_discrete_map=RISK_COLOURS,
                title=title,
                labels={x_col: x_label, 'recipe_name': '', 'weighted_risk_level': 'Risk'},
                category_orders={'weighted_risk_level': ['Low', 'Medium', 'High', 'Very High']},
            )
            fig.update_layout(
                yaxis={'categoryorder': 'total ascending'}, showlegend=False,
                margin=dict(t=40, b=0, l=0, r=20), height=350,
            )
            return fig

        t1.plotly_chart(top_bar(df, 'weighted_risk_score', 'Top 10 by Weighted Score', 'Score (0–100)'),
                         use_container_width=True)
        t2.plotly_chart(top_bar(df, 'sodium_mg', 'Top 10 by Sodium (mg)', 'Sodium (mg/serving)'),
                         use_container_width=True)
        t3.plotly_chart(top_bar(df, 'energy_kcal', 'Top 10 by Calories (kcal)', 'kcal / serving'),
                         use_container_width=True)

        flag_cols   = ['energy_risk', 'sodium_risk', 'fat_risk', 'sugar_risk', 'protein_risk']
        flag_labels = ['Energy', 'Sodium', 'Fat', 'Sugars', 'Protein']
        flag_matrix = (df[flag_cols] == 'high').astype(int)
        flag_matrix.columns = flag_labels
        cooc = flag_matrix.T.dot(flag_matrix)

        fig_heat = px.imshow(
            cooc, text_auto=True, color_continuous_scale='Reds',
            title='High-Risk Flag Co-occurrence (recipe count)', aspect='auto',
        )
        fig_heat.update_layout(coloraxis_showscale=False, margin=dict(t=40, b=0, l=0, r=0), height=320)
        st.plotly_chart(fig_heat, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Explore recipes (search + browse, moved from the old Dataset Explorer tab)
# ═════════════════════════════════════════════════════════════════════════════
def _load_photo_manifest():
    path = os.path.join(BASE, 'assets', 'photos', 'manifest.csv')
    if not os.path.exists(path):
        return {}
    m = pd.read_csv(path)
    ok = m[m['status'] == 'ok']
    return dict(zip(ok['recipe_id'].astype(str), ok['local_path']))


def _render_recipe_card(col, row, photo_map):
    recipe_id  = str(row['recipe_id'])
    name       = str(row['recipe_name']).title()
    is_scored  = row['data_status'] == 'calculated'
    level      = str(row['weighted_risk_level']) if is_scored else 'insufficient_data'
    badge_class = RISK_CLASS.get(level, 'pw-med')
    stats = (f"{row['energy_kcal']:.0f} kcal · {row['sodium_mg']:.0f} mg salt"
             if is_scored else "Not enough data to score")

    photo_html = None
    local_path = photo_map.get(recipe_id)
    if local_path:
        abs_path = os.path.join(BASE, local_path)
        if os.path.exists(abs_path):
            with open(abs_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            photo_html = f'<img class="pw-photo" src="data:image/jpeg;base64,{b64}">'
    if not photo_html:
        header_colour = RISK_COLOURS.get(level, '#95a5a6')
        photo_html = f'<div class="pw-photo" style="background:{header_colour};"></div>'

    col.markdown(
        f'<div class="pw-card" style="padding:0;overflow:hidden;margin-bottom:16px;">'
        f'{photo_html}'
        f'<div style="padding:14px 16px;">'
        f'<div style="font-weight:700;">{name}</div>'
        f'<div style="margin:6px 0;"><span class="pw-badge {badge_class}">{level.upper()}</span></div>'
        f'<div style="font-size:0.85rem;color:#5b5650;">{stats}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_recipe_detail(row):
    name = str(row['recipe_name']).title()
    is_scored = row['data_status'] == 'calculated'

    if not is_scored:
        st.markdown(f"#### {name}")
        st.warning("Insufficient ingredient-to-USDA matches to calculate nutrition for this recipe.")
        return

    level  = str(row['weighted_risk_level'])
    colour = RISK_COLOURS.get(level, '#95a5a6')
    score  = float(row['weighted_risk_score'])
    risk_bands = {
        'sodium_risk': row['sodium_risk'], 'fat_risk': row['fat_risk'],
        'energy_risk': row['energy_risk'], 'sugar_risk': row['sugar_risk'],
        'protein_risk': row['protein_risk'], 'weighted_risk_level': level,
    }
    sentence = _plain_verdict(risk_bands)

    st.markdown(
        f'<div class="pw-card" style="display:flex;align-items:center;gap:20px;">'
        f'<div style="flex-shrink:0;width:84px;height:84px;border-radius:50%;'
        f'background:{colour};color:#fff;display:flex;align-items:center;'
        f'justify-content:center;font-family:\'Caprasimo\',serif;font-size:1.6rem;">'
        f'{score:.0f}</div>'
        f'<div>'
        f'<div style="font-family:\'Caprasimo\',serif;font-size:1.4rem;">{name} '
        f'<span class="pw-badge {RISK_CLASS.get(level, "pw-med")}">{level.upper()}</span></div>'
        f'<div style="color:#5b5650;margin-top:4px;">{sentence}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    url  = str(row.get('recipe_url', ''))
    meta = [f"Servings: **{row['servings']}**",
            f"Ingredient coverage: **{float(row['ingredient_coverage_pct']):.0f}%**"]
    if url and url != 'nan':
        meta.append(f"[View source]({url})")
    st.markdown("  ·  ".join(meta))

    rows_html = ""
    for col, risk_col, label in [
        ('energy_kcal', 'energy_risk', 'Energy'), ('sodium_mg', 'sodium_risk', 'Sodium'),
        ('fat_g', 'fat_risk', 'Fat'), ('sugars_g', 'sugar_risk', 'Sugars'),
        ('protein_g', 'protein_risk', 'Protein'),
    ]:
        band = row[risk_col]
        dot  = DOT_COLOUR.get(band, '#95a5a6')
        rows_html += (
            '<div style="display:flex;align-items:center;gap:10px;padding:8px 0;'
            'border-bottom:1px solid #ded2ba;">'
            f'<span style="width:12px;height:12px;border-radius:50%;background:{dot};flex-shrink:0;"></span>'
            f'<span style="font-weight:700;min-width:75px;">{label}</span>'
            f'<span style="color:#5b5650;">{NUTRIENT_SENTENCES[col][band]}</span>'
            '</div>'
        )
    st.markdown(f'<div class="pw-card">{rows_html}</div>', unsafe_allow_html=True)


def explore_recipes():
    df_f, show_insuf = render_sidebar_filters()
    photo_map = _load_photo_manifest()

    st.title("📖 Explore Recipes")
    st.caption("Search, filter, and browse the recipes we've already scored.")

    c_search, c_pills, c_view = st.columns([3, 3, 2])
    with c_search:
        search = st.text_input(
            "Search recipe name", placeholder="e.g. jollof, tagine, egusi, stew…",
            label_visibility="collapsed",
        )
    with c_pills:
        risk_pill = st.pills(
            "Risk", ["All", "Low", "Medium", "High", "Very High"], default="All",
        )
    with c_view:
        view = st.segmented_control("View", ["Cards", "Table"], default="Cards")

    base_df = df_all if show_insuf else df_f
    matches = base_df.copy()
    if search:
        matches = matches[matches['recipe_name'].str.contains(search, case=False, na=False)]
    if risk_pill and risk_pill != "All":
        matches = matches[matches['weighted_risk_level'] == risk_pill]

    st.markdown(f"**{len(matches)}** recipe(s)")

    # ── Single-recipe detail (only when a search narrows to a specific dish) ──
    if search and len(matches) > 0:
        if len(matches) == 1:
            sel_row = matches.iloc[0]
        else:
            selected_name = st.selectbox(
                "Select a recipe to inspect:",
                options=matches['recipe_name'].tolist(),
                format_func=lambda x: x.title(),
            )
            sel_row = matches[matches['recipe_name'] == selected_name].iloc[0]
        _render_recipe_detail(sel_row)
        st.divider()
    elif search and len(matches) == 0:
        st.info(f"No recipes found matching **'{search}'**. Try a shorter term like 'jollof', 'egusi' or 'tagine'.")

    # ── Cards / Table ──────────────────────────────────────────────────────────
    if view == "Table":
        table_cols = [
            'recipe_id', 'recipe_name', 'servings',
            'energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'sugars_g', 'sodium_mg',
            'ingredient_coverage_pct',
            'energy_risk', 'sodium_risk', 'fat_risk', 'sugar_risk', 'protein_risk',
            'flag_count', 'flag_risk_level',
            'weighted_risk_score', 'weighted_risk_level',
            'data_status',
        ]
        sort_col = st.selectbox(
            "Sort by",
            options=['weighted_risk_score', 'energy_kcal', 'sodium_mg', 'fat_g', 'sugars_g', 'protein_g', 'flag_count'],
            index=0,
        )
        display_df_sorted = matches[table_cols].copy()
        numeric_sort = pd.to_numeric(display_df_sorted[sort_col], errors='coerce')
        display_df_sorted = display_df_sorted.loc[numeric_sort.sort_values(ascending=False).index]

        st.dataframe(
            display_df_sorted.reset_index(drop=True),
            use_container_width=True,
            height=420,
            column_config={
                'recipe_id'              : st.column_config.NumberColumn('ID',       width='small'),
                'recipe_name'            : st.column_config.TextColumn('Recipe',     width='large'),
                'servings'               : st.column_config.NumberColumn('Serv',     width='small'),
                'energy_kcal'            : st.column_config.NumberColumn('kcal',     format='%.1f'),
                'protein_g'              : st.column_config.NumberColumn('Protein g',format='%.1f'),
                'fat_g'                  : st.column_config.NumberColumn('Fat g',    format='%.1f'),
                'carbohydrate_g'         : st.column_config.NumberColumn('Carbs g',  format='%.1f'),
                'sugars_g'               : st.column_config.NumberColumn('Sugar g',  format='%.1f'),
                'sodium_mg'              : st.column_config.NumberColumn('Na mg',    format='%.0f'),
                'ingredient_coverage_pct': st.column_config.ProgressColumn('Coverage', min_value=0, max_value=100, format='%.0f%%'),
                'flag_count'             : st.column_config.NumberColumn('Flags',    width='small'),
                'weighted_risk_score'    : st.column_config.ProgressColumn('W.Score', min_value=0, max_value=100, format='%.1f'),
                'data_status'            : st.column_config.TextColumn('Status',     width='medium'),
            },
        )
        st.caption(f"Showing {len(display_df_sorted)} of {len(df_all)} total recipes  ·  "
                   f"Active sidebar filters match {len(df_f)} recipes")
    else:
        CARDS_PER_ROW = 4
        MAX_CARDS = 48
        shown = matches.head(MAX_CARDS)
        for i in range(0, len(shown), CARDS_PER_ROW):
            cols = st.columns(CARDS_PER_ROW)
            chunk = shown.iloc[i:i + CARDS_PER_ROW]
            for col, (_, row) in zip(cols, chunk.iterrows()):
                _render_recipe_card(col, row, photo_map)
        if len(matches) > MAX_CARDS:
            st.caption(
                f"Showing the first {MAX_CARDS} of {len(matches)} matches — "
                "narrow your search or switch to Table view to see the rest."
            )

    st.divider()

    st.caption(
        "**Scoring methodology** · Thresholds based on WHO dietary guidelines per serving "
        "(⅓ of 2 000 kcal/day). Sodium threshold: 700 mg/serving (⅓ of 2 000 mg/day WHO limit). "
        "Weighted score weights: Sodium 30%, Energy 25%, Fat 20%, Sugar 15%, Protein 10%. "
        "Recipes with energy = 0 kcal are labelled *insufficient data* — ingredient-to-USDA "
        "matching was not possible for those recipes."
    )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Analyse a Recipe (Phase 1: live input form)
# ═════════════════════════════════════════════════════════════════════════════
#
# TEACHING NOTE — how this tab works end-to-end:
#
#   1. User types a recipe name + ingredient list + servings count
#   2. They click "Analyse ▶"
#   3. We call get_live_analyser() — returns the cached LiveAnalyser object
#      (first call takes ~3s to load USDA data; subsequent calls are instant)
#   4. analyser.analyse(lines, servings) runs the pipeline in memory:
#        parse line → clean ingredient name → fuzzy-match to USDA → scale by grams → sum
#   5. We display the same risk cards/radar/gauge as the Dataset Explorer tab
#   6. We also show a per-ingredient breakdown table so the user can see
#      exactly which ingredients were matched and what they contributed.
def check_a_recipe():
    st.title("🧪 Check a Recipe")
    st.subheader("Analyse a Recipe")
    st.caption(
        "Paste your ingredient list below — one ingredient per line with quantities.  "
        "We'll match each ingredient to the USDA FoodData Central database and calculate "
        "per-serving nutrition and risk scores using the same method as the dataset."
    )

    st.divider()

    # ── Input form ────────────────────────────────────────────────────────────
    # WHY st.form?
    #   Without a form, every keypress (including Enter) triggers a Streamlit
    #   page rerun, which interrupts multiline text entry in the textarea.
    #   st.form batches all inputs and only reruns when the submit button is
    #   clicked, so Enter in the textarea correctly adds a new line.
    with st.form("recipe_form"):
        col_form, col_settings = st.columns([3, 1])

        with col_form:
            recipe_name_input = st.text_input(
                "Recipe name (optional)",
                placeholder="e.g. Jollof Rice, Egusi Soup, Tagine…",
            )
            ingredients_input = st.text_area(
                "Ingredients — one per line",
                placeholder=(
                    "2 cups rice\n"
                    "500g chicken thighs\n"
                    "1 tbsp palm oil\n"
                    "1 onion, chopped\n"
                    "3 cloves garlic\n"
                    "1 tsp salt\n"
                    "2 cups chicken stock\n"
                    "1 tsp curry powder"
                ),
                height=240,
            )

        with col_settings:
            servings_input = st.number_input(
                "Servings", min_value=1, max_value=30, value=4, step=1,
            )
            st.markdown("")   # spacer
            analyse_clicked = st.form_submit_button(
                "Analyse ▶", type="primary", use_container_width=True,
            )
            st.caption(
                "**Tip:** Include amounts (e.g. *2 cups*, *500g*, *1 tbsp*) for the best results. "
                "Ingredients without quantities will be skipped."
            )

    st.divider()

    # ── Results ───────────────────────────────────────────────────────────────
    if analyse_clicked:
        lines = [ln for ln in ingredients_input.split("\n") if ln.strip()]

        if not lines:
            st.warning("Please enter at least one ingredient before clicking Analyse.")
        else:
            analyser = get_live_analyser()

            with st.spinner("Matching ingredients to USDA database…"):
                result = analyser.analyse(lines, int(servings_input))

            nutrition    = result["nutrition"]
            risk         = result["risk"]
            coverage     = result["coverage"]
            recipe_label = recipe_name_input.strip() or "Your Recipe"

            risk_level  = risk["weighted_risk_level"]
            risk_colour = RISK_COLOURS.get(risk_level, "#95a5a6")

            # ── Verdict banner ────────────────────────────────────────────────
            verdict_class    = RISK_CLASS.get(risk_level, "pw-med")
            verdict_sentence = _plain_verdict(risk)
            w_score = float(risk["weighted_risk_score"])
            st.markdown(
                f'<div class="pw-card" style="display:flex;align-items:center;gap:20px;">'
                f'<div style="flex-shrink:0;width:84px;height:84px;border-radius:50%;'
                f'background:{risk_colour};color:#fff;display:flex;align-items:center;'
                f'justify-content:center;font-family:\'Caprasimo\',serif;font-size:1.6rem;">'
                f'{w_score:.0f}</div>'
                f'<div>'
                f'<div style="font-family:\'Caprasimo\',serif;font-size:1.4rem;">{recipe_label} '
                f'<span class="pw-badge {verdict_class}">{risk_level.upper()}</span></div>'
                f'<div style="color:#5b5650;margin-top:4px;">{verdict_sentence}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            n_matched = sum(1 for i in result["ingredients"] if i["status"] == "matched")
            n_total   = len(result["ingredients"])
            st.markdown(
                f"Servings: **{servings_input}** · "
                f"Ingredient coverage: **{coverage:.0f}%** "
                f"({n_matched} of {n_total} ingredients matched to USDA)"
            )

            if coverage < 30:
                st.warning(
                    "⚠ Coverage is below 30% — fewer than a third of ingredients matched the "
                    "USDA database.  The nutrition totals are likely a significant underestimate.  "
                    "Check the ingredient breakdown below to see what was missed."
                )
            elif coverage < 60:
                st.info(
                    "ℹ Coverage is moderate (30–60%).  Some ingredients weren't matched.  "
                    "Results give a useful directional estimate."
                )

            st.markdown("")

            # ── Nutrient rows (plain-English) | Nutrition Facts label ────────
            col_rows, col_label = st.columns([3, 2])

            with col_rows:
                nutrient_display = [
                    ("energy_kcal", "energy_risk",  "Energy"),
                    ("sodium_mg",   "sodium_risk",  "Sodium"),
                    ("fat_g",       "fat_risk",     "Fat"),
                    ("sugars_g",    "sugar_risk",   "Sugars"),
                    ("protein_g",   "protein_risk", "Protein"),
                ]
                rows_html = ""
                for col, risk_col, label in nutrient_display:
                    band = risk[risk_col]
                    dot  = DOT_COLOUR.get(band, "#95a5a6")
                    sentence = NUTRIENT_SENTENCES[col][band]
                    rows_html += (
                        '<div style="display:flex;align-items:center;gap:10px;padding:8px 0;'
                        'border-bottom:1px solid #ded2ba;">'
                        f'<span style="width:12px;height:12px;border-radius:50%;background:{dot};'
                        'flex-shrink:0;"></span>'
                        f'<span style="font-weight:700;min-width:75px;">{label}</span>'
                        f'<span style="color:#5b5650;">{sentence}</span>'
                        '</div>'
                    )
                st.markdown(f'<div class="pw-card">{rows_html}</div>', unsafe_allow_html=True)

                flagged = [col for col, risk_col, _ in nutrient_display if risk[risk_col] == "high"]
                if flagged:
                    st.markdown("**Tips to make this healthier:**")
                    for col in flagged:
                        st.markdown(f"- {NUTRIENT_TIPS[col]}")

            with col_label:
                st.markdown(
                    _render_nutrition_label(nutrition, risk, int(servings_input)),
                    unsafe_allow_html=True,
                )

            st.divider()

            # ── Curious how we worked this out? ───────────────────────────────
            with st.expander("Curious how we worked this out?"):

                def _hex_rgb2(h):
                    h = h.lstrip("#")
                    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                r_rgb = _hex_rgb2(risk_colour)

                col_radar, col_gauge = st.columns(2)

                with col_radar:
                    rad_nutrients = ["energy_kcal", "sodium_mg", "fat_g", "sugars_g", "protein_g"]
                    rad_labels    = ["Energy",      "Sodium",    "Fat",   "Sugars",   "Protein"]
                    scores   = [_nutrient_risk_score(n, float(nutrition[n])) for n in rad_nutrients]
                    scores_c = scores + [scores[0]]
                    labels_c = rad_labels + [rad_labels[0]]

                    fig_radar = go.Figure()
                    fig_radar.add_trace(go.Scatterpolar(
                        r=[0.5] * 6, theta=labels_c,
                        mode="lines",
                        line=dict(color="#e74c3c", width=1.5, dash="dash"),
                        name="High-risk threshold",
                    ))
                    fig_radar.add_trace(go.Scatterpolar(
                        r=scores_c, theta=labels_c,
                        fill="toself",
                        fillcolor=f"rgba({r_rgb[0]},{r_rgb[1]},{r_rgb[2]},0.25)",
                        line=dict(color=risk_colour, width=2),
                        name="Risk profile",
                    ))
                    fig_radar.update_layout(
                        polar=dict(
                            radialaxis=dict(
                                visible=True, range=[0, 1],
                                tickvals=[0, 0.25, 0.5, 0.75, 1.0],
                                ticktext=["0", "", "High", "", "Max"],
                                gridcolor="#ddd",
                            ),
                            angularaxis=dict(gridcolor="#ddd"),
                            bgcolor="rgba(0,0,0,0)",
                        ),
                        showlegend=False,
                        height=300,
                        margin=dict(t=30, b=10, l=40, r=40),
                        title=dict(
                            text="Nutrient Risk Profile (dashed = high-risk boundary)",
                            font_size=12,
                        ),
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                with col_gauge:
                    fig_gauge = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=w_score,
                        number={"suffix": " / 100", "font": {"size": 26}},
                        gauge={
                            "axis": {"range": [0, 100], "tickwidth": 1},
                            "bar":  {"color": risk_colour, "thickness": 0.25},
                            "steps": [
                                {"range": [0,  25], "color": RISK_COLOURS["Low"]},
                                {"range": [25, 50], "color": RISK_COLOURS["Medium"]},
                                {"range": [50, 75], "color": RISK_COLOURS["High"]},
                                {"range": [75, 100], "color": RISK_COLOURS["Very High"]},
                            ],
                        },
                        title={
                            "text": f"Weighted Risk Score<br><b>{risk_level}</b>",
                            "font": {"size": 14},
                        },
                    ))
                    fig_gauge.update_layout(height=250, margin=dict(t=60, b=10, l=20, r=20))
                    st.plotly_chart(fig_gauge, use_container_width=True)

                    flag_count = int(risk["flag_count"])
                    flag_level = risk["flag_risk_level"]
                    flag_col   = RISK_COLOURS.get(flag_level, "#95a5a6")
                    flag_badge = (
                        f'<span style="background:{flag_col};color:white;padding:3px 10px;'
                        f'border-radius:10px;font-weight:600">{flag_level}</span>'
                    )
                    st.markdown(
                        f"**Flag count:** {flag_count} high-risk nutrient(s)  \n"
                        f"**Flag risk level:** {flag_badge}",
                        unsafe_allow_html=True,
                    )

                st.divider()

                # ── Ingredient breakdown table ─────────────────────────────────
                st.subheader("Ingredient Breakdown")
                st.caption(
                    "How each ingredient was parsed, matched to the USDA database, "
                    "and what it contributed to the per-serving totals."
                )

                STATUS_LABEL = {
                    "matched":       "✅ Matched",
                    "no_grams":      "⚠ No quantity",
                    "no_usda_match": "❌ No USDA match",
                    "no_usda_data":  "❌ No USDA data",
                }

                table_rows = []
                for ing in result["ingredients"]:
                    contrib = ing.get("nutrition") or {}
                    table_rows.append({
                        "As typed":         ing["raw"],
                        "Cleaned name":     ing["name_cleaned"],
                        "USDA food":        ing["food_name"] or "—",
                        "Match":            ing["match_type"],
                        "Grams (recipe)":   f"{ing['grams']:.0f} g" if ing["grams"] else "—",
                        "Status":           STATUS_LABEL.get(ing["status"], ing["status"]),
                        "kcal/serving":     f"{contrib.get('energy_kcal', 0):.1f}" if contrib else "—",
                        "Protein g":        f"{contrib.get('protein_g',   0):.1f}" if contrib else "—",
                        "Fat g":            f"{contrib.get('fat_g',       0):.1f}" if contrib else "—",
                        "Sodium mg":        f"{contrib.get('sodium_mg',   0):.1f}" if contrib else "—",
                    })

                st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

                st.caption(
                    "**Grams (recipe)** = total gram weight across all servings.  "
                    "Per-serving values = Grams ÷ servings ÷ 100 × USDA nutrient per 100 g.  "
                    "Ingredients with *No quantity* or *No USDA match* are excluded from the totals — "
                    "this is why low coverage = underestimated nutrition."
                )

    else:
        # Shown before the user clicks Analyse — explains what to do
        st.info(
            "👈 Enter your recipe ingredients on the left, set the number of servings, "
            "then click **Analyse ▶** to see the nutrition and risk score."
        )
        st.markdown(
            """
**Format guide — how to write ingredients:**

| What you type | How it's parsed |
|---|---|
| `2 cups rice` | 2 × 240 g = 480 g of rice |
| `500g chicken thighs` | 500 g of chicken |
| `1 tbsp palm oil` | 1 × 15 g = 15 g of palm oil |
| `3 cloves garlic` | 3 × 4 g = 12 g of garlic |
| `1 onion, chopped` | 1 × 150 g = 150 g (prep notes after comma are ignored) |
| `½ tsp cayenne pepper` | 0.5 × 5 g = 2.5 g |
| `salt to taste` | ⚠ Skipped — no quantity |
"""
        )


# ═════════════════════════════════════════════════════════════════════════════
# Navigation
# ═════════════════════════════════════════════════════════════════════════════
pages = {
    "home":    st.Page(home,            title="Home",             icon="🏠", default=True),
    "check":   st.Page(check_a_recipe,  title="Check a recipe",   icon="🧪"),
    "explore": st.Page(explore_recipes, title="Explore recipes",  icon="📖"),
    "insights": st.Page(insights,       title="Insights",         icon="📊"),
}
pg = st.navigation(list(pages.values()))
pg.run()
