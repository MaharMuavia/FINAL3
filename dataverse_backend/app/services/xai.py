"""Explain trained models with SHAP when possible and safe fallbacks otherwise."""
from __future__ import annotations

from typing import Any

import numpy as np

from .modeling import TrainedModelBundle


def explain_model(bundle: TrainedModelBundle | None, prediction: dict[str, Any], run_xai: bool = True) -> dict[str, Any]:
    fallback_importance = prediction.get("feature_importance", []) if prediction else []
    if bundle is None or prediction.get("status") != "complete":
        reason = str(prediction.get("reason") or "No trained model was available for XAI.")
        if prediction.get("status") == "skipped":
            return _fallback(fallback_importance, [reason], reason=reason)
        return _fallback(fallback_importance, ["No trained model was available for XAI."])
    if not run_xai:
        return _fallback(fallback_importance, ["run_xai=false"])

    warnings: list[str] = []
    local_explanations: list[dict[str, Any]] = []
    method = "feature_importance_fallback"
    global_importance = fallback_importance

    try:
        import shap  # type: ignore

        if not hasattr(bundle.model, "feature_importances_"):
            raise TypeError("SHAP TreeExplainer is only attempted for tree-compatible models")
        transformed = bundle.preprocessor.transform(bundle.X_test.head(10))
        explainer = shap.TreeExplainer(bundle.model)
        values = explainer.shap_values(transformed)
        if isinstance(values, list):
            values = values[0]
        arr = np.asarray(values)
        if arr.ndim == 3:
            arr = arr.mean(axis=2)
        mean_abs = np.abs(arr).mean(axis=0)
        pairs = sorted(zip(bundle.feature_names, mean_abs), key=lambda item: float(item[1]), reverse=True)[:20]
        total = sum(float(value) for _, value in pairs) or 1.0
        global_importance = [{"feature": str(name), "importance": round(float(value) / total, 6)} for name, value in pairs]
        for row_index, row_values in enumerate(arr[:5]):
            top = sorted(zip(bundle.feature_names, row_values), key=lambda item: abs(float(item[1])), reverse=True)[:5]
            local_explanations.append(
                {
                    "sample_index": row_index,
                    "top_contributors": [{"feature": str(name), "shap_value": round(float(value), 6)} for name, value in top],
                }
            )
        method = "shap_tree_explainer"
    except Exception as exc:
        warnings.append(f"SHAP unavailable or failed; used feature importance fallback ({type(exc).__name__}).")

    top_features = [item["feature"] for item in global_importance[:5]]
    explanation = (
        "The model is primarily influenced by " + ", ".join(top_features) + "."
        if top_features
        else "The model did not expose usable feature importance."
    )
    return {
        "status": "success" if global_importance and method == "shap_tree_explainer" else "fallback" if global_importance else "limited",
        "method": method,
        "global_feature_importance": global_importance,
        "top_features": top_features,
        "local_explanations": local_explanations,
        "plain_english_explanation": explanation,
        "warnings": warnings,
    }


def _fallback(importance: list[dict[str, Any]], warnings: list[str], reason: str | None = None) -> dict[str, Any]:
    top_features = [item["feature"] for item in importance[:5]]
    skipped_message = "Explainability was skipped because no trained model was available."
    if reason:
        skipped_message = f"Prediction and XAI were skipped. {reason}"
    return {
        "status": "fallback" if importance else "skipped",
        "method": "feature_importance_fallback" if importance else None,
        "global_feature_importance": importance,
        "top_features": top_features,
        "local_explanations": [],
        "plain_english_explanation": (
            "Feature importance is used as the explanation fallback. Top drivers: "
            + ", ".join(top_features)
            if top_features
            else skipped_message
        ),
        "warnings": warnings,
    }
