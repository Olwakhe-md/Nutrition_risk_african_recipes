import pandas as pd

risk = pd.read_csv('data/outputs/recipe_risk_scores.csv')
rif  = pd.read_csv('data/interim/recipe_ingredient_final.csv')
im   = pd.read_csv('data/interim/ingredients_master.csv')
rc   = pd.read_csv('data/interim/recipes_clean.csv')

insuf_ids = risk[risk['data_status'] == 'insufficient_data']['recipe_id'].tolist()

ings = (
    rif[rif['recipe_id'].isin(insuf_ids)]
    .merge(im[['ingredient_id', 'ingredient_name', 'base_ingredient']], on='ingredient_id', how='left')
)

ing_agg = (
    ings.groupby('recipe_id')
    .apply(lambda g: ' ; '.join(g['base_ingredient'].dropna().tolist()))
    .reset_index()
    .rename(columns={0: 'ingredients'})
)

ing_count = ings.groupby('recipe_id').size().reset_index(name='ingredient_count')

insuf_meta = risk[risk['data_status'] == 'insufficient_data'][
    ['recipe_id', 'recipe_name', 'servings', 'ingredient_coverage_pct']
].copy()

insuf_meta = insuf_meta.merge(rc[['recipe_id', 'recipe_url', 'cuisine']], on='recipe_id', how='left')
insuf_meta = insuf_meta.merge(ing_agg,   on='recipe_id', how='left')
insuf_meta = insuf_meta.merge(ing_count, on='recipe_id', how='left')
insuf_meta = insuf_meta.sort_values('recipe_id').reset_index(drop=True)

out_path = 'data/outputs/insufficient_data_recipes_inspection.csv'
insuf_meta.to_csv(out_path, index=False, encoding='utf-8-sig')

avg_ings = insuf_meta['ingredient_count'].mean()
print(f"Done. {len(insuf_meta)} recipes saved to {out_path}")
print(f"Columns: {list(insuf_meta.columns)}")
print(f"Avg ingredients per recipe: {avg_ings:.1f}")
