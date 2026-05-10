from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# Scenarios accepted by the action plan generator. The watsonx prompt
# adapts to whichever value is provided; "general" is a safe default.
SCENARIO_VALUES = (
    "general",
    "heatwave",
    "flood",
    "wildfire_smoke",
    "power_outage",
    "winter_storm",
    "hurricane",
)


class PlanRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    location_display: Optional[str] = None
    scenario: str = Field(
        "general",
        description=(
            "general | heatwave | flood | wildfire_smoke | power_outage | "
            "winter_storm | hurricane"
        ),
    )
    alerts_summary: Optional[str] = None
    weather_summary: Optional[str] = None
    resources_summary: Optional[str] = None
    risk_summary: Optional[str] = None
    archive_to_cos: bool = False


class RiskAlertsBlock(BaseModel):
    count: Optional[int] = None
    max_severity: Optional[str] = Field(
        None,
        description="One of: minor | moderate | severe | extreme",
    )


class RiskWeatherBlock(BaseModel):
    wind_speed: Optional[float] = Field(
        None, description="Wind speed in mph or km/h (any consistent unit)."
    )
    precip_mm: Optional[float] = None
    temp_f: Optional[float] = None
    temp_c: Optional[float] = None


class RiskResourcesBlock(BaseModel):
    count: Optional[int] = None
    radius_km: Optional[float] = None


class RiskRequest(BaseModel):
    """ML risk prediction input.

    Most fields are optional; the model gracefully handles missing data and
    returns lower-confidence predictions when context is sparse.
    """

    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    alerts: Optional[Any] = Field(
        None,
        description=(
            "Either a {count, max_severity} object or a list of {severity} dicts."
        ),
    )
    weather: Optional[RiskWeatherBlock] = None
    resources: Optional[Any] = Field(
        None,
        description="Either a {count, radius_km} object or a list of resource items.",
    )
    radius_km: Optional[float] = Field(
        None,
        description=(
            "Resource search radius in km. Used as a fallback when "
            "resources is a list and lacks its own radius_km."
        ),
    )
    hints: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional hints, e.g. {is_coastal_or_remote: 0|1}.",
    )
