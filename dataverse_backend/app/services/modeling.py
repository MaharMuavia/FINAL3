"""Safe deterministic regression/classification modeling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..core.config import settings
from .target_inference import infer_target_column, is_identifier_like, suggest_targets


PREDICTION_WORDS = ("predict", "forecast", "model", "classify", "regression", "classification", "estimate")


@dataclass
class TrainedModelBundle:
    model: Any
    preprocessor: Any
    X_test: pd.DataFrame
    y_test: pd.Series
    predictions: np.ndarray
    feature_names: list[str]
    task_type: str
    target_column: str


def _task_for_target(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series) and series.nunique(dropna=True) > max(20, int(len(series.dropna()) * 0.2)):
        return "regression"
    return "classification"


def should_train_prediction(
    query: str | None,
    target: dict[str, Any] | None,
    target_column: str | None,
    run_predictions: bool,
) -> bool:
    if target_column:
        return True
    if query and any(word in query.lower() for word in PREDICTION_WORDS):
        return True
    return bool(run_predictions and target and float(target.get("confidence", target.get("score", 0))) >= settings.AUTO_TRAIN_TARGET_CONFIDENCE)


def _safe_features(df: pd.DataFrame, target_column: str, limitations: list[str]) -> list[str]:
    target_norm = target_column.lower().replace("_", "")
    features: list[str] = []
    for col in df.columns:
        name = str(col)
        if name == target_column:
            continue
        if df[name].nunique(dropna=True) <= 1:
            limitations.append(f"Excluded constant column '{name}'.")
            continue
        if is_identifier_like(df[name], name):
            limitations.append(f"Excluded identifier-like column '{name}'.")
            continue
        normalized = name.lower().replace("_", "")
        if len(target_norm) > 3 and (target_norm in normalized or normalized in target_norm):
            limitations.append(f"Excluded possible leakage column '{name}'.")
            continue
        if not pd.api.types.is_numeric_dtype(df[name]) and df[name].nunique(dropna=True) > 50:
            limitations.append(f"Excluded high-cardinality categorical column '{name}'.")
            continue
        features.append(name)
    _append_leakage_warnings(df, target_column, features, limitations)
    return features


def train_prediction(
    df: pd.DataFrame,
    *,
    query: str | None = None,
    target_column: str | None = None,
    task_type: str | None = None,
    run_predictions: bool = True,
) -> tuple[dict[str, Any], TrainedModelBundle | None, list[dict[str, Any]]]:
    suggestions = suggest_targets(df)
    min_rows = int(settings.MIN_ROWS_FOR_PREDICTION)
    if run_predictions and len(df) < min_rows:
        return {
            "status": "skipped",
            "reason": (
                f"Prediction and XAI were skipped because the dataset has only {len(df)} rows. "
                f"This is fewer than {min_rows} rows, the minimum required for basic ML."
            ),
            "limitations": [f"minimum rows >= {min_rows}", f"actual rows = {len(df)}"],
            "upload_requirements": {"minimum_rows": min_rows, "actual_rows": int(len(df))},
        }, None, suggestions
    target = infer_target_column(df, query=query, selected_target=target_column)
    if not should_train_prediction(query, target, target_column, run_predictions):
        return {
            "status": "skipped",
            "reason": "Prediction was not requested or no inferred target met the confidence threshold.",
            "target_column": target["column"] if target else None,
            "task_type": target.get("task_type") if target else None,
            "limitations": [],
        }, None, suggestions
    if target is None:
        return {"status": "skipped", "reason": "No safe target column found.", "limitations": []}, None, suggestions

    selected_target = str(target["column"])
    selected_task = task_type or target.get("task_type") or _task_for_target(df[selected_target])
    limitations: list[str] = []
    if selected_task not in {"regression", "classification"}:
        return {"status": "failed", "reason": "task_type must be regression or classification", "limitations": []}, None, suggestions
    try:
        return _fit_models(df, selected_target, selected_task, limitations), None, suggestions
    except _BundleResult as bundle_result:
        return bundle_result.prediction, bundle_result.bundle, suggestions
    except Exception as exc:
        limitations.append(f"Model training failed: {type(exc).__name__}")
        return {"status": "failed", "reason": str(exc), "target_column": selected_target, "task_type": selected_task, "limitations": limitations}, None, suggestions


class _BundleResult(Exception):
    def __init__(self, prediction: dict[str, Any], bundle: TrainedModelBundle):
        super().__init__("bundle result")
        self.prediction = prediction
        self.bundle = bundle


def _fit_models(df: pd.DataFrame, target_column: str, task_type: str, limitations: list[str]) -> dict[str, Any]:
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    model_df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[target_column]).copy()
    features = _safe_features(model_df, target_column, limitations)
    if not features:
        return {"status": "skipped", "reason": "No safe feature columns available.", "target_column": target_column, "task_type": task_type, "limitations": limitations}

    X = model_df[features]
    y = model_df[target_column]
    numeric_features = [col for col in features if pd.api.types.is_numeric_dtype(X[col]) or pd.api.types.is_bool_dtype(X[col])]
    categorical_features = [col for col in features if col not in numeric_features]
    one_hot_estimate = sum(max(1, int(X[col].nunique(dropna=True))) for col in categorical_features)
    if one_hot_estimate > 200:
        limitations.append("Too many one-hot features would be created.")
        return {"status": "skipped", "reason": "Too many one-hot features.", "target_column": target_column, "task_type": task_type, "limitations": limitations}

    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # pragma: no cover
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)

    transformers = []
    if numeric_features:
        transformers.append(("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric_features))
    if categorical_features:
        transformers.append(("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encoder", encoder)]), categorical_features))
    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")

    stratify = None
    if task_type == "classification":
        counts = y.astype(str).value_counts()
        if counts.min() >= 2 and len(counts) > 1:
            stratify = y.astype(str)
        if counts.max() / max(1, counts.sum()) >= 0.9:
            limitations.append("Class imbalance is high.")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=stratify)

    if task_type == "regression":
        y_train = pd.to_numeric(y_train, errors="coerce")
        y_test = pd.to_numeric(y_test, errors="coerce")
        valid_train = y_train.dropna().index
        valid_test = y_test.dropna().index
        X_train, y_train = X_train.loc[valid_train], y_train.loc[valid_train]
        X_test, y_test = X_test.loc[valid_test], y_test.loc[valid_test]
        candidates = [
            ("DummyRegressor", DummyRegressor(strategy="mean")),
            ("Ridge", Ridge(random_state=42)),
            ("RandomForestRegressor", RandomForestRegressor(n_estimators=80, max_depth=8, random_state=42)),
        ]
    else:
        y_train = y_train.astype(str)
        y_test = y_test.astype(str)
        candidates = [
            ("DummyClassifier", DummyClassifier(strategy="most_frequent")),
            ("LogisticRegression", LogisticRegression(max_iter=1000, class_weight="balanced")),
            ("RandomForestClassifier", RandomForestClassifier(n_estimators=80, max_depth=8, random_state=42, class_weight="balanced")),
        ]

    results = []
    trained_models = []
    for name, estimator in candidates:
        pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])
        pipeline.fit(X_train, y_train)
        pred = pipeline.predict(X_test)
        if task_type == "regression":
            mse = mean_squared_error(y_test, pred)
            metrics = {"rmse": round(float(np.sqrt(mse)), 6), "mae": round(float(mean_absolute_error(y_test, pred)), 6), "r2": round(float(r2_score(y_test, pred)), 6)}
            score = metrics["r2"]
        else:
            metrics = {"accuracy": round(float(accuracy_score(y_test, pred)), 6), "f1_weighted": round(float(f1_score(y_test, pred, average="weighted", zero_division=0)), 6)}
            score = metrics["f1_weighted"]
        results.append({"model": name, "metrics": metrics})
        trained_models.append((name, pipeline, pred, metrics, score))

    selected = max(trained_models[1:] or trained_models, key=lambda item: item[4])
    selected_name, selected_pipeline, predictions, selected_metrics, _score = selected
    baseline_metrics = results[0]["metrics"]
    feature_importance = _feature_importance(selected_pipeline, features)
    sample = [
        {"row_index": int(y_test.index[idx]), "actual": _safe_scalar(actual), "predicted": _safe_scalar(predictions[idx])}
        for idx, actual in enumerate(list(y_test)[:10])
    ]
    matrix_data = []
    if task_type == "classification":
        labels = sorted(set(map(str, y_test)) | set(map(str, predictions)))
        matrix = confusion_matrix(y_test.astype(str), predictions.astype(str), labels=labels)
        matrix_data = [
            {"actual": labels[i], "predicted": labels[j], "count": int(matrix[i, j])}
            for i in range(len(labels))
            for j in range(len(labels))
        ]
    prediction = {
        "status": "complete",
        "task_type": task_type,
        "target_column": target_column,
        "selected_model": selected_name,
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": results,
        "test_metrics": selected_metrics,
        "model_metrics": selected_metrics,
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "feature_columns": features,
        "feature_importance": feature_importance,
        "predictions_sample": sample,
        "confusion_matrix": matrix_data,
        "limitations": limitations,
    }
    if task_type == "classification" and selected_metrics.get("accuracy") == 1.0:
        prediction["limitations"] = list(dict.fromkeys([
            *prediction["limitations"],
            "Perfect accuracy may indicate data leakage or overly deterministic category relationships. Validate on unseen external data.",
        ]))
    transformed_names = _feature_names(selected_pipeline, features)
    bundle = TrainedModelBundle(
        model=selected_pipeline.named_steps["model"],
        preprocessor=selected_pipeline.named_steps["preprocess"],
        X_test=X_test,
        y_test=y_test,
        predictions=predictions,
        feature_names=transformed_names,
        task_type=task_type,
        target_column=target_column,
    )
    raise _BundleResult(prediction, bundle)


def _feature_names(pipeline: Any, fallback: list[str]) -> list[str]:
    try:
        return [str(name).replace("num__", "").replace("cat__", "") for name in pipeline.named_steps["preprocess"].get_feature_names_out()]
    except Exception:
        return fallback


def _feature_importance(pipeline: Any, features: list[str]) -> list[dict[str, Any]]:
    model = pipeline.named_steps["model"]
    names = _feature_names(pipeline, features)
    values = None
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        coef = np.asarray(model.coef_, dtype=float)
        values = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
    if values is None:
        return []
    values = np.asarray([value if np.isfinite(value) else 0.0 for value in values], dtype=float)
    total = float(values.sum())
    if total <= 0:
        return []
    pairs = sorted(zip(names, values), key=lambda item: float(item[1]), reverse=True)[:20]
    return [{"feature": str(name), "importance": round(float(value) / total, 6)} for name, value in pairs]


def _append_leakage_warnings(df: pd.DataFrame, target_column: str, features: list[str], limitations: list[str]) -> None:
    target_norm = target_column.lower()
    if target_norm != "category":
        return
    suspicious_names = {"food_name", "food_description", "main_ingredient", "cuisine"}
    present = [feature for feature in features if feature.lower() in suspicious_names]
    if not present:
        return
    limitations.append(
        "Possible target leakage: food_name, food_description, main_ingredient, or cuisine can be highly predictive of category."
    )
    target = df[target_column].astype(str)
    for feature in present:
        grouped = df[[feature, target_column]].dropna().astype(str).groupby(feature)[target_column].nunique()
        if not grouped.empty and int((grouped <= 1).sum()) / max(1, len(grouped)) >= 0.9:
            limitations.append(f"Feature '{feature}' is nearly deterministic for category and may inflate classification accuracy.")


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 6)
    return value.item() if hasattr(value, "item") else value
