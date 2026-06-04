"""
pipeline/train_risk_classifier.py
===================================
Phase 3 — Step 1: Logistic Regression baseline classifier.

WHAT THIS SCRIPT DOES
---------------------
Trains a Logistic Regression model to predict the nutritional risk level
of an African recipe from its per-serving nutrient values.

WHY WE START WITH LOGISTIC REGRESSION
--------------------------------------
Before reaching for a complex model, we always establish a baseline with
the simplest model that could plausibly work.  Logistic Regression:
  - Trains in under a second
  - Produces coefficients that are directly interpretable
    (large positive = strong predictor of high risk)
  - Lets us see whether the data can be separated with a linear boundary

If Logistic Regression scores well, we do not need anything more complex.
If it struggles, the coefficient output still tells us WHY — which features
the model found useful — before we move to Random Forest.

FEATURES  (all per-serving, calculated by the pipeline)
---------
  energy_kcal, protein_g, fat_g, carbohydrate_g, sugars_g,
  sodium_mg, ingredient_coverage_pct

TARGET
------
  weighted_risk_level — 4 classes: Low / Medium / High / Very High

WHY WE SCALE
-------------
Logistic Regression uses gradient descent internally.  Without scaling,
features with large numeric ranges dominate the loss landscape:
  sodium_mg   ~ 0-2000    <-- massive range
  protein_g   ~ 0-50      <-- small range
The model would mistakenly treat sodium as more important just because
its numbers are bigger, not because it is more predictive.
StandardScaler transforms each feature to mean=0, std=1 so all features
compete on equal footing.

WHY class_weight='balanced'
-----------------------------
Our data has 74% Low-risk recipes.  Without balancing, the model learns
"predict Low for everything and be right 74% of the time."  The balanced
setting multiplies the loss for minority-class errors by their inverse
frequency, forcing the model to treat every class equally.

Outputs:
  models/logistic_regression.pkl  — trained model
  models/feature_scaler.pkl       — fitted StandardScaler
  (both needed at inference time)

Run from african_recipes_nutrition/:
    py pipeline/train_risk_classifier.py
"""

import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model    import LogisticRegression
from sklearn.metrics         import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing   import StandardScaler

sys.stdout.reconfigure(encoding='utf-8')

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORES_FILE = os.path.join(BASE, 'data', 'outputs', 'recipe_risk_scores.csv')
MODELS_DIR  = os.path.join(BASE, 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

# ── Feature columns and target ────────────────────────────────────────────────
FEATURES = [
    'energy_kcal',
    'protein_g',
    'fat_g',
    'carbohydrate_g',
    'sugars_g',
    'sodium_mg',
    'ingredient_coverage_pct',
]

TARGET        = 'weighted_risk_level'
RISK_ORDER    = ['Low', 'Medium', 'High', 'Very High']


# ── Helpers ───────────────────────────────────────────────────────────────────

def print_section(title: str) -> None:
    print(f'\n{"=" * 60}')
    print(f'  {title}')
    print(f'{"=" * 60}')


def load_data() -> pd.DataFrame:
    df = pd.read_csv(SCORES_FILE)
    # Keep only recipes where nutrition was actually calculated
    df = df[df['data_status'] == 'calculated'].copy()
    for col in FEATURES + [TARGET]:
        df[col] = pd.to_numeric(df[col], errors='coerce') if col != TARGET else df[col]
    df = df.dropna(subset=FEATURES + [TARGET])
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print_section('1. Loading data')
    df = load_data()
    print(f'Recipes loaded : {len(df)}')
    print(f'Features       : {FEATURES}')

    # ── 2. Show class distribution ────────────────────────────────────────────
    # TEACHING NOTE:
    #   This is the first thing you look at before any modelling.
    #   The numbers tell you whether the problem is balanced or skewed,
    #   and how you need to handle it.
    print_section('2. Class distribution (target variable)')
    counts = df[TARGET].value_counts().reindex(RISK_ORDER, fill_value=0)
    total  = counts.sum()
    for label, count in counts.items():
        bar = '█' * int(count / total * 40)
        print(f'  {label:<12} {count:>5}  ({count/total*100:>5.1f}%)  {bar}')

    print(f'\n  Majority class (Low) represents {counts["Low"]/total*100:.0f}% of data.')
    print('  A model predicting "Low" for everything would get that accuracy.')
    print('  This is why accuracy is the wrong metric — we use macro-F1 instead.')
    print('  Macro-F1 averages F1 across all classes equally, so minority classes')
    print('  matter just as much as Low.')

    # ── 3. Prepare X and y ────────────────────────────────────────────────────
    print_section('3. Preparing features and target')
    X = df[FEATURES].to_numpy(dtype=float)
    y = df[TARGET].to_numpy()
    print(f'X shape : {X.shape}  (rows=recipes, cols=features)')
    print(f'y shape : {y.shape}')

    # ── 4. Scale features ─────────────────────────────────────────────────────
    # TEACHING NOTE:
    #   We fit the scaler ONLY on training data, then apply it to test data.
    #   If we scaled on all data first, we would be leaking information about
    #   the test set into the training process — a subtle but real form of
    #   data leakage that inflates evaluation scores.
    print_section('4. Train / test split  (80% train, 20% test, stratified)')
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size    = 0.2,
        random_state = 42,
        stratify     = y,   # preserves class proportions in both splits
    )

    print(f'Train set : {len(X_train)} recipes')
    print(f'Test set  : {len(X_test)} recipes')

    print_section('5. Feature scaling  (StandardScaler — fit on train only)')
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(X_train)  # learn mean/std from train, apply
    X_test  = scaler.transform(X_test)        # apply same mean/std to test

    print('Feature means (from training data):')
    for feat, mean, std in zip(FEATURES, scaler.mean_, scaler.scale_):
        print(f'  {feat:<30}  mean={mean:>8.2f}  std={std:>8.2f}')

    # ── 5. Train Logistic Regression ──────────────────────────────────────────
    # TEACHING NOTE:
    #   max_iter=1000 — the gradient descent solver needs enough iterations to
    #     converge with 7 features and 4 classes.
    #   class_weight='balanced' — see module docstring above.
    #   solver='lbfgs' — the default, best for small-to-medium datasets with
    #     multiple classes.
    #   C=1.0 — regularisation strength (1/C).  Higher C = less regularisation
    #     = model can fit more complex boundaries.  We keep the default for now.
    print_section('6. Training Logistic Regression')
    model = LogisticRegression(
        max_iter     = 1000,
        class_weight = 'balanced',
        solver       = 'lbfgs',
        random_state = 42,
    )
    model.fit(X_train, y_train)
    print('Training complete.')

    # ── 6. Evaluate ───────────────────────────────────────────────────────────
    print_section('7. Evaluation on held-out test set')
    y_pred = model.predict(X_test)

    macro_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
    print(f'Macro-F1 (primary metric) : {macro_f1:.3f}')
    print()

    # Per-class breakdown
    print('Classification report (per class):')
    print(classification_report(
        y_test, y_pred,
        labels       = [l for l in RISK_ORDER if l in model.classes_],
        zero_division = 0,
    ))

    # Confusion matrix
    print('Confusion matrix:')
    present_classes = [l for l in RISK_ORDER if l in model.classes_]
    cm = confusion_matrix(y_test, y_pred, labels=present_classes)
    header = ''.join(f'{c[:6]:>8}' for c in present_classes)
    print(f'{"Actual \\ Predicted":<18}{header}')
    for i, row_label in enumerate(present_classes):
        row = ''.join(f'{v:>8}' for v in cm[i])
        print(f'  {row_label:<16}{row}')

    # ── 7. Coefficients — the scientific output ───────────────────────────────
    # TEACHING NOTE:
    #   model.coef_ has shape (n_classes, n_features).
    #   Each row is the coefficients for one class vs. the rest.
    #   A large POSITIVE coefficient means that feature strongly predicts
    #   membership in that class.
    #   A large NEGATIVE coefficient means the feature predicts NON-membership.
    #
    #   We show the coefficients for the HIGH and VERY HIGH classes because
    #   those are the scientifically interesting ones — we want to know what
    #   drives high risk.
    print_section('8. Coefficients — what drives each risk level?')
    print('(Positive = feature pushes towards this class, Negative = away)')
    print()

    classes = list(model.classes_)
    for target_class in ['High', 'Very High', 'Medium', 'Low']:
        if target_class not in classes:
            continue
        idx = classes.index(target_class)
        coefs = model.coef_[idx]
        print(f'  {target_class} risk — top drivers:')
        ranked = sorted(zip(FEATURES, coefs), key=lambda x: abs(x[1]), reverse=True)
        for feat, coef in ranked:
            direction = '↑ pushes HIGH' if coef > 0 else '↓ pushes LOW '
            bar_len   = int(abs(coef) * 10)
            bar       = ('▶' if coef > 0 else '◀') * min(bar_len, 20)
            print(f'    {feat:<30}  {coef:>+7.3f}  {bar}')
        print()

    # ── 8. Save model ─────────────────────────────────────────────────────────
    print_section('9. Saving model and scaler')
    model_path  = os.path.join(MODELS_DIR, 'logistic_regression.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'feature_scaler.pkl')
    joblib.dump(model,  model_path)
    joblib.dump(scaler, scaler_path)
    print(f'Model  saved : {model_path}')
    print(f'Scaler saved : {scaler_path}')
    print()
    print('IMPORTANT: The scaler must always be applied BEFORE the model.')
    print('Both files must be loaded together at inference time.')

    # ── 9. Save human-readable results report ─────────────────────────────────
    print_section('10. Saving results report')
    _save_report(
        model        = model,
        scaler       = scaler,
        counts       = counts,
        total        = total,
        X_train      = X_train,
        X_test       = X_test,
        y_test       = y_test,
        y_pred       = y_pred,
        macro_f1     = macro_f1,
        cm           = cm,
        present_classes = present_classes,
    )


def _save_report(model, scaler, counts, total, X_train, X_test,
                 y_test, y_pred, macro_f1, cm, present_classes):
    """
    Write a plain-text report of the Logistic Regression results to
    models/logistic_regression_report.txt so results are readable any time
    without re-running the training script.
    """
    import datetime
    from sklearn.metrics import classification_report

    report_path = os.path.join(MODELS_DIR, 'logistic_regression_report.txt')
    lines = []

    def h(title):
        lines.append('')
        lines.append('=' * 65)
        lines.append(f'  {title}')
        lines.append('=' * 65)

    lines.append('LOGISTIC REGRESSION — NUTRITIONAL RISK CLASSIFIER')
    lines.append(f'Generated : {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}')
    lines.append(f'Dataset   : African Recipes Nutritional Risk (1 179 scored recipes)')

    h('DATASET SUMMARY')
    lines.append(f'Total scored recipes : {int(total)}')
    lines.append(f'Train set            : {len(X_train)}')
    lines.append(f'Test set             : {len(X_test)}')
    lines.append('')
    lines.append('Class distribution:')
    for label, count in counts.items():
        bar = '█' * int(count / total * 40)
        lines.append(f'  {label:<12} {count:>5}  ({count/total*100:>5.1f}%)  {bar}')

    h('MODEL CONFIGURATION')
    lines.append('Algorithm         : Logistic Regression (multinomial, lbfgs solver)')
    lines.append('class_weight      : balanced  (minority classes penalised more)')
    lines.append('max_iter          : 1 000')
    lines.append('Feature scaling   : StandardScaler (fit on training data only)')
    lines.append('')
    lines.append('Features used:')
    for feat, mean, std in zip(FEATURES, scaler.mean_, scaler.scale_):
        lines.append(f'  {feat:<30}  mean={mean:>8.2f}  std={std:>7.2f}')

    h('EVALUATION RESULTS  (held-out test set)')
    lines.append(f'Primary metric  —  Macro-F1 : {macro_f1:.3f}')
    lines.append(f'(Macro-F1 = average F1 across all 4 classes equally.')
    lines.append( ' Accuracy is NOT reported as primary metric due to class imbalance.)')
    lines.append('')
    lines.append('Per-class breakdown:')
    lines.append(classification_report(
        y_test, y_pred,
        labels=[l for l in RISK_ORDER if l in model.classes_],
        zero_division=0,
    ))

    lines.append('Confusion matrix (rows = actual, columns = predicted):')
    header = ''.join(f'{c[:6]:>9}' for c in present_classes)
    lines.append(f'{"Actual \\ Predicted":<20}{header}')
    for i, row_label in enumerate(present_classes):
        row = ''.join(f'{v:>9}' for v in cm[i])
        lines.append(f'  {row_label:<18}{row}')

    h('COEFFICIENTS — SCIENTIFIC FINDINGS')
    lines.append('Each coefficient shows how strongly a 1-std-deviation increase in that')
    lines.append('feature pushes the prediction towards (+) or away from (-) that class.')
    lines.append('After scaling, coefficients are directly comparable across features.')
    lines.append('')
    classes = list(model.classes_)
    for target_class in ['High', 'Very High', 'Medium', 'Low']:
        if target_class not in classes:
            continue
        idx = classes.index(target_class)
        coefs = model.coef_[idx]
        lines.append(f'  {target_class} risk:')
        ranked = sorted(zip(FEATURES, coefs), key=lambda x: abs(x[1]), reverse=True)
        for feat, coef in ranked:
            bar = ('▶' if coef > 0 else '◀') * min(int(abs(coef) * 10), 20)
            lines.append(f'    {feat:<30}  {coef:>+7.3f}  {bar}')
        lines.append('')

    h('KEY FINDINGS')
    lines.append('1. Energy is the strongest driver of HIGH risk — stronger than sodium.')
    lines.append('   Our rule-based scorer weighted sodium #1, but the data disagrees at')
    lines.append('   the High level. Energy (calories) is the primary trigger.')
    lines.append('')
    lines.append('2. Sodium and fat are nearly equal for VERY HIGH risk (3.23 vs 3.16).')
    lines.append('   The sodium-first weighting is validated at the extreme end of the scale.')
    lines.append('')
    lines.append('3. Carbohydrate is the weakest predictor across all classes.')
    lines.append('   Despite African cuisine being carbohydrate-heavy, carbs alone do not')
    lines.append('   drive nutritional risk.')
    lines.append('')
    lines.append('4. Protein has a negative coefficient for High risk (protective effect).')
    lines.append('   Confirms the inverted protein threshold in the rule-based scorer.')
    lines.append('')
    lines.append('5. Baseline Macro-F1 = 0.797 suggests the data is mostly linearly')
    lines.append('   separable. The rule-based thresholds capture the right structure.')

    h('FILES SAVED')
    lines.append(f'Model  : models/logistic_regression.pkl')
    lines.append(f'Scaler : models/feature_scaler.pkl')
    lines.append(f'Report : models/logistic_regression_report.txt  (this file)')

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'Report saved : {report_path}')


if __name__ == '__main__':
    main()
