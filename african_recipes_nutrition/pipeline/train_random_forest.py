"""
pipeline/train_random_forest.py
================================
Phase 3 — Step 2: Random Forest classifier.

WHY WE MERGE HIGH + VERY HIGH INTO ONE CLASS
---------------------------------------------
Very High has only 32 recipes.  That is too few for a model to learn a
reliable pattern.  The model would either ignore that class entirely or
overfit to those 32 specific recipes.

We merge:
  High (100) + Very High (32) → Elevated Risk (132)

This gives us three balanced-enough classes:
  Low       : 879  (74%)  — rule-based score 0-49
  Medium    : 168  (14%)  — rule-based score 50-74
  Elevated  : 132  (11%)  — rule-based score 75-100

132 is enough for a reliable pattern.  The scientific loss is minimal:
High and Very High are driven by the same nutrients — the difference is
only degree.  Feature importance across 3 classes is still informative.

WHY NO FEATURE SCALING
-----------------------
Random Forest splits data with threshold questions: "is sodium > 500 mg?"
The answer to that question is the same whether sodium is measured in mg
or in standardised units.  Scale does not affect splits, so StandardScaler
adds no value.  This is a key contrast with Logistic Regression.

WHY HYPERPARAMETER TUNING
--------------------------
Random Forest has several settings that affect performance:
  n_estimators      — how many trees to build
  max_depth         — how deep each tree can grow (None = unlimited)
  min_samples_split — minimum recipes needed at a node before it can split
  min_samples_leaf  — minimum recipes required in a leaf node
  max_features      — how many features considered at each split

We use RandomizedSearchCV: try 30 random combinations, each evaluated on
5 cross-validation folds of the training data.  This finds good settings
without exhaustively testing every possible combination.

Outputs:
  models/random_forest.pkl         — trained model (best params)
  models/random_forest_report.txt  — results + feature importance

Run from african_recipes_nutrition/:
    py pipeline/train_random_forest.py
"""

import datetime
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble        import RandomForestClassifier
from sklearn.metrics         import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, train_test_split

sys.stdout.reconfigure(encoding='utf-8')

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORES_FILE = os.path.join(BASE, 'data', 'outputs', 'recipe_risk_scores.csv')
MODELS_DIR  = os.path.join(BASE, 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

FEATURES   = [
    'energy_kcal',
    'protein_g',
    'fat_g',
    'carbohydrate_g',
    'sugars_g',
    'sodium_mg',
    'ingredient_coverage_pct',
]
TARGET     = 'weighted_risk_level'
RISK_ORDER = ['Low', 'Medium', 'Elevated']   # 3-class after merger


def print_section(title):
    print(f'\n{"=" * 60}')
    print(f'  {title}')
    print(f'{"=" * 60}')


def load_and_prepare():
    df = pd.read_csv(SCORES_FILE)
    df = df[df['data_status'] == 'calculated'].copy()
    for col in FEATURES:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=FEATURES + [TARGET])

    X = df[FEATURES].to_numpy(dtype=float)
    y = df[TARGET].to_numpy()

    # ── Merge High + Very High → Elevated ─────────────────────────────────────
    # np.where(condition, value_if_true, value_if_false):
    #   wherever y is 'High' or 'Very High', replace with 'Elevated'
    #   everywhere else, keep the original value
    y = np.where(np.isin(y, ['High', 'Very High']), 'Elevated', y)

    return X, y


def main():

    # ── 1. Load and inspect data ──────────────────────────────────────────────
    print_section('1. Loading data and merging classes')
    X, y = load_and_prepare()
    print(f'Total recipes  : {len(X)}')
    print()

    classes, counts = np.unique(y, return_counts=True)
    total = len(y)
    print('Class distribution after merging High + Very High → Elevated:')
    for cls, cnt in sorted(zip(classes, counts), key=lambda x: RISK_ORDER.index(x[0])):
        bar = '█' * int(cnt / total * 40)
        print(f'  {cls:<12} {cnt:>5}  ({cnt/total*100:>5.1f}%)  {bar}')
    print()
    print('Elevated class (was High=100, Very High=32) now has 132 examples.')
    print('This is enough for the model to learn a reliable pattern.')

    # ── 2. Train / test split ─────────────────────────────────────────────────
    print_section('2. Train / test split  (same seed as Logistic Regression)')
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size    = 0.2,
        random_state = 42,
        stratify     = y,
    )
    print(f'Train : {len(X_train)}  |  Test : {len(X_test)}')
    print('No feature scaling — Random Forest is scale-invariant.')

    # ── 3. Baseline Random Forest ─────────────────────────────────────────────
    print_section('3. Baseline Random Forest  (default hyperparameters, 200 trees)')
    baseline = RandomForestClassifier(
        n_estimators = 200,
        class_weight = 'balanced',
        random_state = 42,
        n_jobs       = -1,
    )
    baseline.fit(X_train, y_train)
    y_pred_base   = baseline.predict(X_test)
    macro_f1_base = f1_score(y_test, y_pred_base, average='macro', zero_division=0)
    print(f'Baseline Macro-F1 : {macro_f1_base:.3f}')
    print(f'(LR baseline was 0.797 on 4 classes — not directly comparable)')

    # ── 4. Hyperparameter tuning ──────────────────────────────────────────────
    print_section('4. Hyperparameter tuning  (30 random combinations, 5-fold CV)')
    print()
    print('Parameters being searched:')
    print('  n_estimators      : how many trees to build')
    print('  max_depth         : maximum depth per tree (None = grow fully)')
    print('  min_samples_split : minimum recipes to split a node')
    print('  min_samples_leaf  : minimum recipes required in a leaf')
    print('  max_features      : features considered at each split')
    print()

    param_grid = {
        'n_estimators'     : [100, 200, 300, 500],
        'max_depth'        : [None, 10, 20, 30],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf' : [1, 2, 4],
        'max_features'     : ['sqrt', 'log2'],
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    search = RandomizedSearchCV(
        estimator  = RandomForestClassifier(
            class_weight = 'balanced',
            random_state = 42,
            n_jobs       = -1,
        ),
        param_distributions = param_grid,
        n_iter       = 30,
        scoring      = 'f1_macro',
        cv           = cv,
        random_state = 42,
        n_jobs       = -1,
        verbose      = 1,
    )

    print('Searching... (30 combinations × 5 folds = 150 model fits)')
    search.fit(X_train, y_train)

    print(f'\nBest cross-validated Macro-F1 (on training folds) : {search.best_score_:.3f}')
    print('Best hyperparameters found:')
    for param, value in sorted(search.best_params_.items()):
        print(f'  {param:<22} : {value}')

    # ── 5. Final evaluation ───────────────────────────────────────────────────
    print_section('5. Final evaluation on held-out test set')
    best_model = search.best_estimator_
    y_pred     = best_model.predict(X_test)
    macro_f1   = f1_score(y_test, y_pred, average='macro', zero_division=0)

    print(f'Baseline RF Macro-F1  : {macro_f1_base:.3f}  (default params, 3 classes)')
    print(f'Tuned RF Macro-F1     : {macro_f1:.3f}  (best params, 3 classes)')
    print()

    present_classes = [l for l in RISK_ORDER if l in best_model.classes_]
    print('Classification report:')
    print(classification_report(
        y_test, y_pred,
        labels       = present_classes,
        zero_division = 0,
    ))

    cm = confusion_matrix(y_test, y_pred, labels=present_classes)
    print('Confusion matrix:')
    header = ''.join(f'{c[:8]:>10}' for c in present_classes)
    print(f'{"Actual \\ Predicted":<18}{header}')
    for i, row_label in enumerate(present_classes):
        row = ''.join(f'{v:>10}' for v in cm[i])
        print(f'  {row_label:<16}{row}')

    # ── 6. Feature importance ─────────────────────────────────────────────────
    print_section('6. Feature importance  (Gini impurity reduction, all trees)')
    importances = best_model.feature_importances_
    ranked = sorted(zip(FEATURES, importances), key=lambda x: x[1], reverse=True)

    print(f'  {"Feature":<30}  {"Importance":>10}  Bar')
    print(f'  {"-"*58}')
    for feat, imp in ranked:
        bar = '█' * int(imp * 100)
        print(f'  {feat:<30}  {imp:>10.4f}  {bar}')

    print()
    print('Cross-check with Logistic Regression |coefficients| for High risk:')
    print('  LR ranking: energy_kcal > sodium_mg > fat_g > sugars_g > protein_g')
    print('  RF ranking above — do they agree?')

    # ── 7. Save ───────────────────────────────────────────────────────────────
    print_section('7. Saving model and report')
    model_path = os.path.join(MODELS_DIR, 'random_forest.pkl')
    joblib.dump(best_model, model_path)
    print(f'Model saved : {model_path}')

    _save_report(
        macro_f1_base   = macro_f1_base,
        macro_f1        = macro_f1,
        best_params     = search.best_params_,
        best_cv_score   = search.best_score_,
        y_test          = y_test,
        y_pred          = y_pred,
        cm              = cm,
        present_classes = present_classes,
        ranked          = ranked,
    )


def _save_report(macro_f1_base, macro_f1, best_params, best_cv_score,
                 y_test, y_pred, cm, present_classes, ranked):
    from sklearn.metrics import classification_report as cr

    report_path = os.path.join(MODELS_DIR, 'random_forest_report.txt')
    lines = []

    def h(title):
        lines.append('')
        lines.append('=' * 65)
        lines.append(f'  {title}')
        lines.append('=' * 65)

    lines.append('RANDOM FOREST — NUTRITIONAL RISK CLASSIFIER')
    lines.append(f'Generated : {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}')
    lines.append('Classes   : Low / Medium / Elevated  (High + Very High merged)')

    h('CLASS MERGER RATIONALE')
    lines.append('High (100) + Very High (32) merged into Elevated Risk (132).')
    lines.append('32 examples is too few for a reliable minority-class pattern.')
    lines.append('132 combined examples gives the model enough signal to learn from.')

    h('BEST HYPERPARAMETERS  (RandomizedSearchCV, 30 iter, 5-fold CV)')
    for param, value in sorted(best_params.items()):
        lines.append(f'  {param:<22} : {value}')
    lines.append(f'\nBest cross-validated Macro-F1 : {best_cv_score:.3f}')

    h('EVALUATION RESULTS  (held-out test set)')
    lines.append(f'Baseline RF Macro-F1  : {macro_f1_base:.3f}')
    lines.append(f'Tuned RF Macro-F1     : {macro_f1:.3f}')
    lines.append('')
    lines.append(cr(y_test, y_pred, labels=present_classes, zero_division=0))

    lines.append('Confusion matrix:')
    header = ''.join(f'{c[:8]:>10}' for c in present_classes)
    lines.append(f'{"Actual \\ Predicted":<20}{header}')
    for i, row_label in enumerate(present_classes):
        row = ''.join(f'{v:>10}' for v in cm[i])
        lines.append(f'  {row_label:<18}{row}')

    h('FEATURE IMPORTANCE')
    lines.append(f'  {"Feature":<30}  {"Importance":>10}  Bar')
    lines.append(f'  {"-"*58}')
    for feat, imp in ranked:
        bar = '█' * int(imp * 100)
        lines.append(f'  {feat:<30}  {imp:>10.4f}  {bar}')

    h('FILES')
    lines.append('  models/random_forest.pkl          — trained model')
    lines.append('  models/random_forest_report.txt   — this file')

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'Report saved : {report_path}')


if __name__ == '__main__':
    main()
