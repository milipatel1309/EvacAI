"""ML risk prediction for Evac-AI.

Uses a small scikit-learn RandomForestClassifier when sklearn is available,
trained on synthetic tabular data at module import time. If sklearn is not
installed (or training fails), the module silently falls back to a
deterministic, feature-based heuristic scorer that produces the **same
response shape**, so callers don't need to branch.

Response shape (always):
  {
    "risk_level":  "Low" | "Medium" | "High",
    "risk_score":  0..100 (int),
    "confidence":  0..1   (float),
    "reasons":     [str, ...],
    "features":    {<feature_name>: <value>, ...},
    "model":       "Random Forest (demo)" | "Heuristic (demo)",
    "model_kind":  "random_forest" | "heuristic",
  }
"""

from __future__ import annotations

import math
import random
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Feature schema
# ---------------------------------------------------------------------------
# The model takes 8 numeric features. They are easy to derive from the data
# the rest of the app already has on the client (alerts, weather, resources).
FEATURE_NAMES: tuple[str, ...] = (
    "alert_count",          # how many active alerts at this point
    "alert_severity_max",   # 0=none, 1=minor, 2=moderate, 3=severe, 4=extreme
    "wind_speed",           # mph (or whatever unit the client passes)
    "precip_mm",            # mm in latest interval
    "temp_extremity",       # 0..1 -- |temp - 70F| / 50  (clamped)
    "resource_count",       # nearby shelters/clinics/hospitals/etc.
    "resource_density",     # resource_count / max(radius_km, 1)
    "is_coastal_or_remote", # 0/1 hint (currently always 0 from client; placeholder)
)

# Risk classes used by the classifier
RISK_CLASSES: tuple[str, ...] = ("Low", "Medium", "High")


# ---------------------------------------------------------------------------
# Heuristic scorer (also used to label synthetic training data, so it must be
# defined BEFORE the sklearn training block below).
# ---------------------------------------------------------------------------
def _heuristic_raw_score(
    *,
    alert_count: float,
    alert_severity_max: float,
    wind_speed: float,
    precip_mm: float,
    temp_extremity: float,
    resource_count: float,
    resource_density: float,
    is_coastal_or_remote: float,
) -> float:
    """Return raw 0..100 risk score using transparent weighted features."""
    s = 0.0
    s += min(20.0, 4.0 * alert_count)
    s += 6.0 * alert_severity_max
    if wind_speed > 20:
        s += min(20.0, (wind_speed - 20) * 0.6)
    if precip_mm > 1:
        s += min(15.0, (precip_mm - 1) * 0.6)
    s += 18.0 * max(0.0, min(1.0, temp_extremity))
    if resource_count <= 1:
        s += 8.0
    elif resource_count <= 4:
        s += 4.0
    if resource_density < 0.3:
        s += 4.0
    if is_coastal_or_remote >= 0.5:
        s += 4.0
    return float(max(0.0, min(100.0, s)))


# ---------------------------------------------------------------------------
# Synthetic training data generator
# ---------------------------------------------------------------------------
def _label_for_features(feat: list[float]) -> int:
    """Deterministic-ish label from features for synthetic training set.

    Returns 0=Low, 1=Medium, 2=High. Mirrors the heuristic scorer below so
    training data is internally consistent.
    """
    score = _heuristic_raw_score(
        alert_count=feat[0],
        alert_severity_max=feat[1],
        wind_speed=feat[2],
        precip_mm=feat[3],
        temp_extremity=feat[4],
        resource_count=feat[5],
        resource_density=feat[6],
        is_coastal_or_remote=feat[7],
    )
    if score >= 65:
        return 2
    if score >= 35:
        return 1
    return 0


def _generate_synthetic_dataset(
    n_samples: int = 1200, seed: int = 7
) -> tuple[list[list[float]], list[int]]:
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[int] = []
    for _ in range(n_samples):
        alert_count = float(rng.randint(0, 8))
        alert_severity_max = float(rng.choice([0, 0, 1, 1, 2, 2, 3, 3, 4]))
        wind_speed = float(rng.uniform(0, 75))
        precip_mm = float(rng.uniform(0, 60))
        temp_extremity = float(rng.uniform(0, 1))
        resource_count = float(rng.randint(0, 30))
        radius_km = max(1.0, rng.uniform(2, 25))
        resource_density = resource_count / radius_km
        is_coastal_or_remote = float(rng.choice([0, 0, 0, 0, 1]))
        feat = [
            alert_count,
            alert_severity_max,
            wind_speed,
            precip_mm,
            temp_extremity,
            resource_count,
            resource_density,
            is_coastal_or_remote,
        ]
        X.append(feat)
        y.append(_label_for_features(feat))
    return X, y


# ---------------------------------------------------------------------------
# Optional sklearn model
# ---------------------------------------------------------------------------
_SKLEARN_OK = False
_RF_MODEL: Any = None

try:  # noqa: SIM105 -- explicit fallback chain
    from sklearn.ensemble import RandomForestClassifier  # type: ignore

    def _train_model() -> Any:
        X, y = _generate_synthetic_dataset()
        clf = RandomForestClassifier(
            n_estimators=120,
            max_depth=8,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=1,
        )
        clf.fit(X, y)
        return clf

    try:
        _RF_MODEL = _train_model()
        _SKLEARN_OK = True
    except Exception:
        _RF_MODEL = None
        _SKLEARN_OK = False
except (ImportError, ModuleNotFoundError, OSError):
    # Missing sklearn, bad binary / shared libs, or unloadable native deps on small Linux images.
    _RF_MODEL = None
    _SKLEARN_OK = False
except Exception:
    _RF_MODEL = None
    _SKLEARN_OK = False


# ---------------------------------------------------------------------------
# Heuristic predictor (uses the raw scorer defined above)
# ---------------------------------------------------------------------------
def _heuristic_predict(features: dict[str, float]) -> dict[str, Any]:
    raw = _heuristic_raw_score(**features)
    if raw >= 65:
        level = "High"
    elif raw >= 35:
        level = "Medium"
    else:
        level = "Low"
    # Confidence: closer to a band edge = lower confidence.
    if level == "High":
        confidence = min(0.95, 0.6 + (raw - 65) / 100.0)
    elif level == "Medium":
        # Highest confidence in middle of band (50)
        confidence = 0.65 + (1.0 - abs(raw - 50) / 30.0) * 0.2
    else:
        confidence = min(0.95, 0.6 + (35 - raw) / 100.0)
    return {
        "risk_level": level,
        "risk_score": int(round(raw)),
        "confidence": round(float(max(0.4, min(0.99, confidence))), 3),
        "model": "Heuristic (demo)",
        "model_kind": "heuristic",
    }


# ---------------------------------------------------------------------------
# Feature engineering from incoming summaries
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {
    "extreme": 4,
    "severe": 3,
    "moderate": 2,
    "minor": 1,
    "unknown": 0,
    "": 0,
    None: 0,
}


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return float(x)
        return float(x)
    except (TypeError, ValueError):
        return default


def build_features(payload: dict[str, Any]) -> dict[str, float]:
    """Translate a flexible client payload into the 8 model features.

    Accepted (all optional):
      alerts:    {"count": int, "max_severity": "minor|moderate|severe|extreme"}
                 OR a list of {"severity": "..."} dicts.
      weather:   {"wind_speed": float, "precip_mm": float, "temp_f": float, "temp_c": float}
      resources: {"count": int, "radius_km": float}
                 OR a list of items.
      hints:     {"is_coastal_or_remote": 0|1}
    """
    alerts_in = payload.get("alerts") or {}
    weather_in = payload.get("weather") or {}
    resources_in = payload.get("resources") or {}
    hints = payload.get("hints") or {}

    if isinstance(alerts_in, list):
        alert_count = float(len(alerts_in))
        max_sev = 0.0
        for a in alerts_in:
            sev = (a or {}).get("severity") if isinstance(a, dict) else None
            sev_key = str(sev or "").strip().lower()
            max_sev = max(max_sev, float(_SEVERITY_ORDER.get(sev_key, 0)))
        alert_severity_max = max_sev
    else:
        alert_count = _to_float(alerts_in.get("count"), 0.0)
        sev_key = str(alerts_in.get("max_severity") or "").strip().lower()
        alert_severity_max = float(_SEVERITY_ORDER.get(sev_key, 0))

    wind_speed = _to_float(weather_in.get("wind_speed"), 0.0)
    precip_mm = _to_float(weather_in.get("precip_mm"), 0.0)

    temp_f = weather_in.get("temp_f")
    temp_c = weather_in.get("temp_c")
    if temp_f is None and temp_c is not None:
        try:
            temp_f = float(temp_c) * 9.0 / 5.0 + 32.0
        except (TypeError, ValueError):
            temp_f = None
    if temp_f is None:
        temp_extremity = 0.0
    else:
        temp_extremity = max(0.0, min(1.0, abs(float(temp_f) - 70.0) / 50.0))

    if isinstance(resources_in, list):
        resource_count = float(len(resources_in))
        radius_km = _to_float(payload.get("radius_km"), 10.0)
    else:
        resource_count = _to_float(resources_in.get("count"), 0.0)
        radius_km = _to_float(resources_in.get("radius_km"), 10.0)
    radius_km = max(1.0, radius_km)
    resource_density = resource_count / radius_km

    is_coastal_or_remote = 1.0 if _to_float(hints.get("is_coastal_or_remote"), 0.0) >= 0.5 else 0.0

    return {
        "alert_count": float(alert_count),
        "alert_severity_max": float(alert_severity_max),
        "wind_speed": float(wind_speed),
        "precip_mm": float(precip_mm),
        "temp_extremity": float(temp_extremity),
        "resource_count": float(resource_count),
        "resource_density": float(resource_density),
        "is_coastal_or_remote": float(is_coastal_or_remote),
    }


def _features_vector(features: dict[str, float]) -> list[float]:
    return [features[name] for name in FEATURE_NAMES]


# ---------------------------------------------------------------------------
# Reason generation (so the UI can show "why")
# ---------------------------------------------------------------------------
def _reasons(features: dict[str, float]) -> list[str]:
    out: list[str] = []
    if features["alert_count"] >= 1:
        out.append(
            f"{int(features['alert_count'])} active alert(s) reported for this area"
        )
    sev = int(features["alert_severity_max"])
    if sev >= 3:
        names = {3: "severe", 4: "extreme"}
        out.append(f"At least one alert is rated {names.get(sev, 'severe')}")
    elif sev == 2:
        out.append("At least one moderate-severity alert is active")

    w = features["wind_speed"]
    if w >= 35:
        out.append(f"Sustained winds near {int(w)} mph (damaging-wind range)")
    elif w >= 20:
        out.append(f"Elevated winds around {int(w)} mph")

    p = features["precip_mm"]
    if p >= 20:
        out.append(f"Heavy precipitation: {p:.1f} mm in the latest interval")
    elif p >= 5:
        out.append(f"Notable precipitation: {p:.1f} mm")

    if features["temp_extremity"] >= 0.6:
        out.append("Temperature is far from the comfortable 70°F band (heat or cold stress risk)")
    elif features["temp_extremity"] >= 0.35:
        out.append("Temperature is meaningfully outside the comfort band")

    rc = features["resource_count"]
    if rc <= 1:
        out.append("Very few nearby shelters / clinics / hospitals were found")
    elif rc <= 4:
        out.append("Limited density of nearby emergency resources")

    if features["is_coastal_or_remote"] >= 0.5:
        out.append("Location flagged as coastal / remote (longer response times possible)")

    if not out:
        out.append("No strong risk signals detected in current alerts, weather, or resources")
    return out


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def predict_risk(payload: dict[str, Any]) -> dict[str, Any]:
    """Predict risk for a location given a flexible client payload.

    Always returns the documented response shape, even if sklearn is missing.
    """
    features = build_features(payload or {})
    reasons = _reasons(features)

    if _SKLEARN_OK and _RF_MODEL is not None:
        try:
            vec = [_features_vector(features)]
            probs = _RF_MODEL.predict_proba(vec)[0]
            class_index = int(max(range(len(probs)), key=lambda i: probs[i]))
            level = RISK_CLASSES[class_index]

            # Probability-weighted score for a 0..100 number
            # Low=15, Medium=50, High=85 anchors -> weighted average
            anchors = (15.0, 50.0, 85.0)
            score = sum(p * a for p, a in zip(probs, anchors))
            confidence = float(probs[class_index])
            return {
                "risk_level": level,
                "risk_score": int(round(max(0.0, min(100.0, score)))),
                "confidence": round(float(confidence), 3),
                "reasons": reasons,
                "features": features,
                "feature_names": list(FEATURE_NAMES),
                "model": "Random Forest (demo)",
                "model_kind": "random_forest",
                "class_probabilities": {
                    cls: round(float(p), 3) for cls, p in zip(RISK_CLASSES, probs)
                },
            }
        except Exception:
            # Defensive: fall back to heuristic if anything goes wrong at predict-time.
            pass

    base = _heuristic_predict(features)
    return {
        **base,
        "reasons": reasons,
        "features": features,
        "feature_names": list(FEATURE_NAMES),
    }


def model_info() -> dict[str, Any]:
    """Lightweight introspection for diagnostics / status pages."""
    return {
        "sklearn_available": _SKLEARN_OK,
        "model": "Random Forest (demo)" if _SKLEARN_OK else "Heuristic (demo)",
        "feature_names": list(FEATURE_NAMES),
        "risk_classes": list(RISK_CLASSES),
    }
