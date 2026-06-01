"""
dashboard.py
============
Streamlit dashboard for the African Recipes Nutritional Risk project.

Run from african_recipes_nutrition/:
    streamlit run dashboard.py
"""

import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "African Recipes — Nutritional Risk",
    page_icon   = "🍲",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

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

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv(os.path.join(DATA_OUTPUT, 'recipe_risk_scores.csv'))

    # Separate scored vs insufficient
    scored = df[df['data_status'] == 'calculated'].copy()
    insuf  = df[df['data_status'] == 'insufficient_data'].copy()

    # Coerce numeric columns
    num_cols = ['energy_kcal','protein_g','fat_g','carbohydrate_g',
                'sugars_g','sodium_mg','ingredient_coverage_pct',
                'flag_count','weighted_risk_score']
    for col in num_cols:
        scored[col] = pd.to_numeric(scored[col], errors='coerce')

    return df, scored, insuf


df_all, df, df_insuf = load_data()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/cooking-pot.png", width=60)
    st.title("Filters")

    flag_filter = st.multiselect(
        "Flag-count risk level",
        options=["Low","Medium","High"],
        default=["Low","Medium","High"],
    )
    wt_filter = st.multiselect(
        "Weighted risk level",
        options=["Low","Medium","High","Very High"],
        default=["Low","Medium","High","Very High"],
    )
    coverage_min = st.slider(
        "Min ingredient coverage (%)",
        min_value=0, max_value=100, value=0, step=5,
    )
    show_insuf = st.checkbox("Include insufficient-data recipes in table", value=False)

    st.divider()
    st.caption("Scoring basis: WHO dietary guidelines per serving (⅓ daily intake). "
               "Sodium weighted 30 % in weighted score due to high hypertension burden in Africa.")

# ── Apply filters ─────────────────────────────────────────────────────────────
df_f = df[
    (df['flag_risk_level'].isin(flag_filter)) &
    (df['weighted_risk_level'].isin(wt_filter)) &
    (df['ingredient_coverage_pct'] >= coverage_min)
]

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🍲 African Recipes — Nutritional Risk Dashboard")
st.caption("Per-serving risk scoring against WHO dietary guidelines · "
           "Two methods: Flag Count and Weighted Score (sodium-prioritised)")
st.divider()

# ── Row 1: KPI cards ──────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)

k1.metric("Total Recipes",        len(df_all))
k2.metric("Recipes Scored",       len(df),
          delta=f"{len(df)/len(df_all)*100:.0f}% of total")
k3.metric("Insufficient Data",    len(df_insuf))
k4.metric("Avg Weighted Score",   f"{df['weighted_risk_score'].mean():.1f} / 100")
k5.metric("High-Risk Recipes",
          int((df['flag_risk_level'] == 'High').sum()),
          delta=f"{(df['flag_risk_level']=='High').mean()*100:.0f}% of scored",
          delta_color="inverse")

st.divider()

# ── Row 2: Risk distribution ──────────────────────────────────────────────────
st.subheader("Risk Distribution")
c1, c2, c3 = st.columns([1,1,1])

# Flag-count pie
flag_counts = df['flag_risk_level'].value_counts().reindex(
    ['Low','Medium','High'], fill_value=0)
fig_flag = px.pie(
    names=flag_counts.index,
    values=flag_counts.values,
    color=flag_counts.index,
    color_discrete_map=RISK_COLOURS,
    hole=0.45,
    title="Flag-Count Risk Levels",
)
fig_flag.update_traces(textposition='outside', textinfo='percent+label')
fig_flag.update_layout(showlegend=False, margin=dict(t=40,b=0,l=0,r=0))
c1.plotly_chart(fig_flag, use_container_width=True)

# Weighted-score pie
wt_order = ['Low','Medium','High','Very High']
wt_counts = df['weighted_risk_level'].value_counts().reindex(wt_order, fill_value=0)
fig_wt = px.pie(
    names=wt_counts.index,
    values=wt_counts.values,
    color=wt_counts.index,
    color_discrete_map=RISK_COLOURS,
    hole=0.45,
    title="Weighted Score Risk Levels",
)
fig_wt.update_traces(textposition='outside', textinfo='percent+label')
fig_wt.update_layout(showlegend=False, margin=dict(t=40,b=0,l=0,r=0))
c2.plotly_chart(fig_wt, use_container_width=True)

# Weighted score histogram
fig_hist = px.histogram(
    df, x='weighted_risk_score', nbins=25,
    color_discrete_sequence=['#2980b9'],
    title="Weighted Score Distribution",
    labels={'weighted_risk_score': 'Weighted Risk Score (0–100)'},
)
fig_hist.add_vline(x=25, line_dash='dash', line_color=RISK_COLOURS['Medium'],
                   annotation_text='Medium', annotation_position='top right')
fig_hist.add_vline(x=50, line_dash='dash', line_color=RISK_COLOURS['High'],
                   annotation_text='High',   annotation_position='top right')
fig_hist.add_vline(x=75, line_dash='dash', line_color=RISK_COLOURS['Very High'],
                   annotation_text='Very High', annotation_position='top right')
fig_hist.update_layout(margin=dict(t=40,b=0,l=0,r=0))
c3.plotly_chart(fig_hist, use_container_width=True)

st.divider()

# ── Row 3: Per-nutrient risk breakdown ────────────────────────────────────────
st.subheader("Per-Nutrient Risk Breakdown")

nutrient_labels = {
    'energy_risk' : 'Energy',
    'sodium_risk' : 'Sodium',
    'fat_risk'    : 'Fat',
    'sugar_risk'  : 'Sugars',
    'protein_risk': 'Protein',
}
nutrient_rows = []
for col, label in nutrient_labels.items():
    counts = df[col].value_counts()
    for level in ['low','medium','high']:
        nutrient_rows.append({
            'Nutrient': label,
            'Risk Level': level.capitalize(),
            'Count': int(counts.get(level, 0)),
        })
df_nutr = pd.DataFrame(nutrient_rows)

fig_nutr = px.bar(
    df_nutr, x='Nutrient', y='Count', color='Risk Level',
    barmode='stack',
    color_discrete_map={k.capitalize(): v for k, v in NUTRIENT_COLOURS.items()},
    title="Recipe Count by Nutrient Risk Level",
    category_orders={'Risk Level': ['High','Medium','Low']},
)
fig_nutr.update_layout(
    legend_title_text='',
    xaxis_title='',
    yaxis_title='Number of Recipes',
    margin=dict(t=40,b=0,l=0,r=0),
)
st.plotly_chart(fig_nutr, use_container_width=True)

st.divider()

# ── Row 4: Scatter — Energy vs Sodium ─────────────────────────────────────────
st.subheader("Energy vs Sodium per Serving")
st.caption("Bubble size = fat (g/serving). Dashed lines show high-risk thresholds (800 kcal, 700 mg sodium).")

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
    category_orders={'weighted_risk_level': ['Low','Medium','High','Very High']},
)
fig_scatter.add_vline(x=800,  line_dash='dash', line_color='#e74c3c', line_width=1)
fig_scatter.add_hline(y=700,  line_dash='dash', line_color='#e74c3c', line_width=1)
fig_scatter.update_layout(
    height=500,
    legend_title_text='Weighted Risk',
    margin=dict(t=10,b=0,l=0,r=0),
)
st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# ── Row 5: Top risky recipes ──────────────────────────────────────────────────
st.subheader("Top Risky Recipes")
t1, t2, t3 = st.columns(3)

def top_bar(data, x_col, title, x_label, colour, n=10):
    top = data.nlargest(n, x_col)[['recipe_name', x_col, 'weighted_risk_level']].copy()
    top['recipe_name'] = top['recipe_name'].str[:40]
    fig = px.bar(
        top, x=x_col, y='recipe_name', orientation='h',
        color='weighted_risk_level',
        color_discrete_map=RISK_COLOURS,
        title=title,
        labels={x_col: x_label, 'recipe_name': '', 'weighted_risk_level': 'Risk'},
        category_orders={'weighted_risk_level': ['Low','Medium','High','Very High']},
    )
    fig.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        showlegend=False,
        margin=dict(t=40,b=0,l=0,r=20),
        height=350,
    )
    return fig

t1.plotly_chart(top_bar(df, 'weighted_risk_score', 'Top 10 by Weighted Score',
                         'Score (0–100)', '#922b21'), use_container_width=True)
t2.plotly_chart(top_bar(df, 'sodium_mg', 'Top 10 by Sodium (mg)',
                         'Sodium (mg/serving)', '#e74c3c'), use_container_width=True)
t3.plotly_chart(top_bar(df, 'energy_kcal', 'Top 10 by Calories (kcal)',
                         'kcal / serving', '#e67e22'), use_container_width=True)

st.divider()

# ── Row 6: Flag co-occurrence heatmap ─────────────────────────────────────────
st.subheader("Flag Co-occurrence — Which Risk Flags Appear Together?")
st.caption("Shows how often two nutrients are both flagged High in the same recipe.")

flag_cols = ['energy_risk','sodium_risk','fat_risk','sugar_risk','protein_risk']
flag_labels = ['Energy','Sodium','Fat','Sugars','Protein']

# Build binary matrix of high flags
flag_matrix = (df[flag_cols] == 'high').astype(int)
flag_matrix.columns = flag_labels

cooc = flag_matrix.T.dot(flag_matrix)

fig_heat = px.imshow(
    cooc,
    text_auto=True,
    color_continuous_scale='Reds',
    title='High-Risk Flag Co-occurrence (recipe count)',
    aspect='auto',
)
fig_heat.update_layout(
    coloraxis_showscale=False,
    margin=dict(t=40,b=0,l=0,r=0),
    height=320,
)
st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── Row 7: Recipe explorer ────────────────────────────────────────────────────
st.subheader("Recipe Explorer")
st.caption("Search for any recipe to see its full nutritional risk profile, then browse all matching results below.")

search = st.text_input("Search recipe name", placeholder="e.g. jollof, tagine, egusi, stew…")

if show_insuf:
    display_df = df_all.copy()
else:
    display_df = df_f.copy()

if search:
    matches = display_df[
        display_df['recipe_name'].str.contains(search, case=False, na=False)
    ].copy()
else:
    matches = display_df.copy()

# ── Risk card (only shown when search is active) ──────────────────────────────
if search and len(matches) > 0:
    st.markdown(f"**{len(matches)}** recipe(s) match **'{search}'**")

    selected_name = st.selectbox(
        "Select a recipe to inspect:",
        options=matches['recipe_name'].tolist(),
        format_func=lambda x: x.title(),
    )
    row = matches[matches['recipe_name'] == selected_name].iloc[0]
    is_scored = row['data_status'] == 'calculated'

    risk_level  = str(row['weighted_risk_level']) if is_scored else 'insufficient_data'
    risk_colour = RISK_COLOURS.get(risk_level, '#95a5a6')

    # Hex → rgb for semi-transparent fill in radar
    def hex_to_rgb(h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    r_rgb = hex_to_rgb(risk_colour)

    # ── Card header ───────────────────────────────────────────────────────────
    badge = (f'<span style="background:{risk_colour};color:white;padding:5px 14px;'
             f'border-radius:14px;font-weight:700;font-size:0.9rem">{risk_level.upper()}</span>')
    st.markdown(
        f"<h3 style='margin-bottom:4px'>{selected_name.title()} &nbsp; {badge}</h3>",
        unsafe_allow_html=True,
    )

    cov = row['ingredient_coverage_pct']
    serv = row['servings']
    url  = str(row.get('recipe_url', ''))
    meta = [f"Servings: **{serv}**", f"Ingredient coverage: **{float(cov):.0f}%**"]
    if url and url != 'nan':
        meta.append(f"[View source]({url})")
    st.markdown("  ·  ".join(meta))

    if not is_scored:
        st.warning("Insufficient ingredient-to-USDA matches to calculate nutrition for this recipe.")
    else:
        # ── Macros row ────────────────────────────────────────────────────────
        mc = st.columns(6)
        nutrient_meta = [
            ('energy_kcal',    'energy_risk',  'Energy',  '{:.0f} kcal'),
            ('protein_g',      'protein_risk', 'Protein', '{:.1f} g'),
            ('fat_g',          'fat_risk',     'Fat',     '{:.1f} g'),
            ('carbohydrate_g', None,           'Carbs',   '{:.1f} g'),
            ('sugars_g',       'sugar_risk',   'Sugars',  '{:.1f} g'),
            ('sodium_mg',      'sodium_risk',  'Sodium',  '{:.0f} mg'),
        ]
        for i, (col, risk_col, label, fmt) in enumerate(nutrient_meta):
            val   = float(row[col])
            delta = str(row[risk_col]).capitalize() if risk_col else None
            mc[i].metric(label, fmt.format(val), delta=delta, delta_color="off")

        st.markdown("")

        # ── Risk radar + weighted score gauge ─────────────────────────────────
        left, right = st.columns([3, 2])

        with left:
            # Radar: 5 nutrient risk scores (0→1)
            rad_nutrients = ['energy_kcal', 'sodium_mg', 'fat_g', 'sugars_g', 'protein_g']
            rad_labels    = ['Energy', 'Sodium', 'Fat', 'Sugars', 'Protein']
            scores = [_nutrient_risk_score(n, float(row[n])) for n in rad_nutrients]
            # Close the polygon
            scores_c = scores + [scores[0]]
            labels_c = rad_labels + [rad_labels[0]]

            fig_radar = go.Figure()
            # Threshold ring at 0.5
            fig_radar.add_trace(go.Scatterpolar(
                r=[0.5]*6, theta=labels_c,
                mode='lines',
                line=dict(color='#e74c3c', width=1.5, dash='dash'),
                name='High-risk threshold',
            ))
            # Recipe profile
            fig_radar.add_trace(go.Scatterpolar(
                r=scores_c, theta=labels_c,
                fill='toself',
                fillcolor=f"rgba({r_rgb[0]},{r_rgb[1]},{r_rgb[2]},0.25)",
                line=dict(color=risk_colour, width=2),
                name='Risk profile',
            ))
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 1], tickvals=[0, 0.25, 0.5, 0.75, 1.0],
                                    ticktext=['0','','High','','Max'], gridcolor='#ddd'),
                    angularaxis=dict(gridcolor='#ddd'),
                    bgcolor='rgba(0,0,0,0)',
                ),
                showlegend=False,
                height=300,
                margin=dict(t=30, b=10, l=40, r=40),
                title=dict(text='Nutrient Risk Profile (dashed = high-risk boundary)', font_size=12),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        with right:
            # Weighted score gauge
            w_score = float(row['weighted_risk_score'])
            fig_gauge = go.Figure(go.Indicator(
                mode='gauge+number',
                value=w_score,
                number={'suffix': ' / 100', 'font': {'size': 26}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1},
                    'bar':  {'color': risk_colour, 'thickness': 0.25},
                    'steps': [
                        {'range': [0,  25], 'color': RISK_COLOURS['Low']},
                        {'range': [25, 50], 'color': RISK_COLOURS['Medium']},
                        {'range': [50, 75], 'color': RISK_COLOURS['High']},
                        {'range': [75, 100],'color': RISK_COLOURS['Very High']},
                    ],
                },
                title={'text': f'Weighted Risk Score<br><b>{risk_level}</b>', 'font': {'size': 14}},
            ))
            fig_gauge.update_layout(height=250, margin=dict(t=60, b=10, l=20, r=20))
            st.plotly_chart(fig_gauge, use_container_width=True)

            flag_count = int(row['flag_count'])
            flag_level = str(row['flag_risk_level'])
            flag_col   = RISK_COLOURS.get(flag_level, '#95a5a6')
            flag_badge = (f'<span style="background:{flag_col};color:white;padding:3px 10px;'
                          f'border-radius:10px;font-weight:600">{flag_level}</span>')
            st.markdown(
                f"**Flag count:** {flag_count} high-risk nutrient(s)  \n"
                f"**Flag risk level:** {flag_badge}",
                unsafe_allow_html=True,
            )

    st.divider()

elif search and len(matches) == 0:
    st.info(f"No recipes found matching **'{search}'**. Try a shorter term like 'jollof', 'egusi' or 'tagine'.")
    st.divider()

# ── Results table ─────────────────────────────────────────────────────────────
table_label = f"All matches for '{search}'" if search else "All Recipes"
st.markdown(f"**{table_label}** — {len(matches)} recipe(s)")

table_cols = [
    'recipe_id','recipe_name','servings',
    'energy_kcal','protein_g','fat_g','carbohydrate_g','sugars_g','sodium_mg',
    'ingredient_coverage_pct',
    'energy_risk','sodium_risk','fat_risk','sugar_risk','protein_risk',
    'flag_count','flag_risk_level',
    'weighted_risk_score','weighted_risk_level',
    'data_status',
]

sort_col = st.selectbox(
    "Sort by",
    options=['weighted_risk_score','energy_kcal','sodium_mg','fat_g','sugars_g','protein_g','flag_count'],
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

st.divider()

# ── Footer ────────────────────────────────────────────────────────────────────
st.caption(
    "**Scoring methodology** · Thresholds based on WHO dietary guidelines per serving "
    "(⅓ of 2 000 kcal/day). Sodium threshold: 700 mg/serving (⅓ of 2 000 mg/day WHO limit). "
    "Weighted score weights: Sodium 30%, Energy 25%, Fat 20%, Sugar 15%, Protein 10%. "
    "Recipes with energy = 0 kcal are labelled *insufficient data* — ingredient-to-USDA "
    "matching was not possible for those recipes."
)
