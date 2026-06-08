"""Script to train machine learning models on the retail_mart_processed_v1 dataset.

Trains regression models to predict 'total_sales' and 'profit', and a classification model to predict 'stockout_flag'.
Saves the trained model pipelines and their metadata.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, accuracy_score, classification_report, confusion_matrix

# Path setup
ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "retail_mart_processed_v1.csv"
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_dataset() -> pd.DataFrame:
    """Load the retail mart dataset."""
    print(f"Loading dataset from {DATA_PATH}...")
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded dataset successfully. Shape: {df.shape}")
    return df


def get_features_and_target(df: pd.DataFrame, target_col: str) -> tuple[pd.DataFrame, pd.Series]:
    """Select features and targets safely, handling constant/identifier columns."""
    target_norm = target_col.lower().replace("_", "")
    features: list[str] = []
    
    for col in df.columns:
        name = str(col)
        if name == target_col:
            continue
        
        # Exclude constant columns
        if df[name].nunique(dropna=True) <= 1:
            continue
            
        # Exclude identifier-like columns
        if name.endswith("_id") or name == "id":
            continue
            
        # Exclude high-cardinality categorical columns
        if not pd.api.types.is_numeric_dtype(df[name]) and df[name].nunique(dropna=True) > 50:
            continue
            
        # Exclude leakage candidates
        normalized = name.lower().replace("_", "")
        if len(target_norm) > 3 and (target_norm in normalized or normalized in target_norm):
            continue
            
        features.append(name)
        
    return df[features], df[target_col]


def get_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """Build preprocessor for numerical and categorical features."""
    numeric_features = [col for col in X.columns if pd.api.types.is_numeric_dtype(X[col]) or pd.api.types.is_bool_dtype(X[col])]
    categorical_features = [col for col in X.columns if col not in numeric_features]
    
    transformers = []
    if numeric_features:
        transformers.append((
            "num", 
            Pipeline([
                ("imputer", SimpleImputer(strategy="median")), 
                ("scaler", StandardScaler())
            ]), 
            numeric_features
        ))
    if categorical_features:
        transformers.append((
            "cat", 
            Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")), 
                ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
            ]), 
            categorical_features
        ))
        
    return ColumnTransformer(transformers=transformers, remainder="drop")


def get_feature_importances(pipeline: Pipeline, feature_cols: list[str]) -> list[dict[str, Any]]:
    """Extract and sort feature importances from a trained pipeline."""
    model = pipeline.named_steps["model"]
    preprocessor = pipeline.named_steps["preprocess"]
    
    try:
        names = [str(name).replace("num__", "").replace("cat__", "") for name in preprocessor.get_feature_names_out()]
    except Exception:
        names = feature_cols
        
    values = None
    if hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        values = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
        
    if values is None:
        return []
        
    total = float(values.sum())
    if total <= 0:
        return []
        
    pairs = sorted(zip(names, values), key=lambda item: float(item[1]), reverse=True)
    return [{"feature": str(name), "importance": round(float(value) / total, 6)} for name, value in pairs]


def train_regression(df: pd.DataFrame, target_col: str) -> dict[str, Any]:
    """Train regression models for the given target."""
    print(f"\n--- Training Regression Model for '{target_col}' ---")
    X, y = get_features_and_target(df, target_col)
    
    # Drop rows with missing target
    valid_idx = y.dropna().index
    X, y = X.loc[valid_idx], y.loc[valid_idx]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
    preprocessor = get_preprocessor(X)
    
    candidates = [
        ("Ridge", Ridge(random_state=42)),
        ("RandomForestRegressor", RandomForestRegressor(n_estimators=80, max_depth=8, random_state=42, n_jobs=-1))
    ]
    
    best_r2 = -float("inf")
    best_model_name = None
    best_pipeline = None
    best_metrics = {}
    
    for name, estimator in candidates:
        pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])
        pipeline.fit(X_train, y_train)
        pred = pipeline.predict(X_test)
        
        mse = mean_squared_error(y_test, pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test, pred)
        r2 = r2_score(y_test, pred)
        
        print(f"{name} Results -> R2: {r2:.4f}, RMSE: {rmse:.4f}, MAE: {mae:.4f}")
        
        if r2 > best_r2:
            best_r2 = r2
            best_model_name = name
            best_pipeline = pipeline
            best_metrics = {
                "r2": round(float(r2), 6),
                "rmse": round(float(rmse), 6),
                "mae": round(float(mae), 6)
            }
            
    print(f"Selected Best Model: {best_model_name}")
    
    # Save model
    model_path = MODELS_DIR / f"{target_col}_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(best_pipeline, f)
    print(f"Saved best pipeline to {model_path}")
    
    feature_importance = get_feature_importances(best_pipeline, list(X.columns))
    
    return {
        "target": target_col,
        "task_type": "regression",
        "selected_model": best_model_name,
        "metrics": best_metrics,
        "features": list(X.columns),
        "feature_importance": feature_importance[:10],
        "model_file": model_path.name
    }


def train_classification(df: pd.DataFrame, target_col: str) -> dict[str, Any]:
    """Train classification models for the given target."""
    print(f"\n--- Training Classification Model for '{target_col}' ---")
    X, y = get_features_and_target(df, target_col)
    
    # Drop rows with missing target
    valid_idx = y.dropna().index
    X, y = X.loc[valid_idx], y.loc[valid_idx]
    
    # Stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    preprocessor = get_preprocessor(X)
    
    candidates = [
        ("LogisticRegression", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
        ("RandomForestClassifier", RandomForestClassifier(n_estimators=80, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1))
    ]
    
    best_f1 = -float("inf")
    best_model_name = None
    best_pipeline = None
    best_metrics = {}
    
    # Convert labels to string to be safe
    y_train = y_train.astype(str)
    y_test = y_test.astype(str)
    
    for name, estimator in candidates:
        pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])
        pipeline.fit(X_train, y_train)
        pred = pipeline.predict(X_test)
        
        acc = accuracy_score(y_test, pred)
        report = classification_report(y_test, pred, output_dict=True, zero_division=0)
        f1_weighted = report["weighted avg"]["f1-score"]
        
        print(f"{name} Results -> Accuracy: {acc:.4f}, Weighted F1: {f1_weighted:.4f}")
        
        if f1_weighted > best_f1:
            best_f1 = f1_weighted
            best_model_name = name
            best_pipeline = pipeline
            best_metrics = {
                "accuracy": round(float(acc), 6),
                "f1_weighted": round(float(f1_weighted), 6),
                "precision_weighted": round(float(report["weighted avg"]["precision"]), 6),
                "recall_weighted": round(float(report["weighted avg"]["recall"]), 6)
            }
            
    print(f"Selected Best Model: {best_model_name}")
    
    # Save model
    model_path = MODELS_DIR / f"{target_col}_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(best_pipeline, f)
    print(f"Saved best pipeline to {model_path}")
    
    feature_importance = get_feature_importances(best_pipeline, list(X.columns))
    
    # Confusion matrix
    pred_test = best_pipeline.predict(X_test)
    labels = sorted(list(set(y_test) | set(pred_test)))
    cm = confusion_matrix(y_test, pred_test, labels=labels)
    cm_list = [
        {"actual": labels[i], "predicted": labels[j], "count": int(cm[i, j])}
        for i in range(len(labels))
        for j in range(len(labels))
    ]
    
    return {
        "target": target_col,
        "task_type": "classification",
        "selected_model": best_model_name,
        "metrics": best_metrics,
        "features": list(X.columns),
        "feature_importance": feature_importance[:10],
        "confusion_matrix": cm_list,
        "model_file": model_path.name
    }


def main():
    df = load_dataset()
    
    results = {}
    
    # Train total_sales (regression)
    if "total_sales" in df.columns:
        results["total_sales"] = train_regression(df, "total_sales")
        
    # Train profit (regression)
    if "profit" in df.columns:
        results["profit"] = train_regression(df, "profit")
        
    # Train stockout_flag (classification)
    if "stockout_flag" in df.columns:
        results["stockout_flag"] = train_classification(df, "stockout_flag")
        
    # Save metadata summary
    metadata_path = MODELS_DIR / "model_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll models trained and evaluated. Metadata saved to {metadata_path}")


if __name__ == "__main__":
    main()
