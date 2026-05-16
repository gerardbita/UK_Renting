from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

import requests


TFL_JOURNEY_URL = "https://api.tfl.gov.uk/Journey/JourneyResults"
PUBLIC_TRANSPORT_MODES = "tube,bus,overground,elizabeth-line,dlr,national-rail"


class RoutingError(RuntimeError):
    pass


@dataclass(slots=True)
class RouteMetrics:
    mode: str
    provider: str
    duration_minutes: int
    distance_km: float | None
    summary: str = ""


class TflRoutingClient:
    def __init__(self, *, timeout_seconds: int, user_agent: str):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )

    def public_transport(
        self,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        *,
        modes: str = PUBLIC_TRANSPORT_MODES,
        date: str | None = None,
        time: str | None = None,
    ) -> RouteMetrics:
        return self._journey(
            origin_latitude,
            origin_longitude,
            destination_latitude,
            destination_longitude,
            mode="public_transport",
            tfl_modes=modes,
            date=date,
            time=time,
        )

    def cycling(
        self,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        *,
        date: str | None = None,
        time: str | None = None,
    ) -> RouteMetrics:
        return self._journey(
            origin_latitude,
            origin_longitude,
            destination_latitude,
            destination_longitude,
            mode="cycling",
            tfl_modes="cycle",
            date=date,
            time=time,
        )

    def _journey(
        self,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        *,
        mode: str,
        tfl_modes: str,
        date: str | None = None,
        time: str | None = None,
    ) -> RouteMetrics:
        origin = f"{origin_latitude},{origin_longitude}"
        destination = f"{destination_latitude},{destination_longitude}"
        url = f"{TFL_JOURNEY_URL}/{origin}/to/{destination}"
        try:
            params = {
                "mode": tfl_modes,
                "timeIs": "Departing",
                "journeyPreference": "LeastTime",
            }
            if date:
                params["date"] = date
            if time:
                params["time"] = time

            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RoutingError(f"TfL routing failed for {mode}: {exc}") from exc
        except ValueError as exc:
            raise RoutingError(f"TfL routing returned invalid JSON for {mode}.") from exc

        journeys = payload.get("journeys") or []
        if not journeys:
            raise RoutingError(f"TfL returned no {mode} route.")

        journey = min(journeys, key=lambda item: item.get("duration") or 10**9)
        duration = int(journey.get("duration") or 0)
        distance_m = _journey_distance_m(journey)
        return RouteMetrics(
            mode=mode,
            provider="tfl",
            duration_minutes=duration,
            distance_km=round(distance_m / 1000, 2) if distance_m is not None else None,
            summary=_journey_summary(journey),
        )


def route_key(
    provider: str,
    mode: str,
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    profile: str = "default",
) -> str:
    return (
        f"{provider}:geometry-v1:{mode}:"
        f"{profile}:"
        f"{origin_latitude:.5f},{origin_longitude:.5f}:"
        f"{destination_latitude:.5f},{destination_longitude:.5f}"
    )


def _journey_distance_m(journey: dict[str, Any]) -> float | None:
    total = 0.0
    has_distance = False
    for leg in journey.get("legs") or []:
        path_distance = _path_distance_m(leg.get("path", {}).get("lineString"))
        if path_distance is not None:
            total += path_distance
            has_distance = True
            continue

        distance = leg.get("distance")
        if isinstance(distance, (int, float)):
            total += float(distance)
            has_distance = True
            continue
        steps = leg.get("instruction", {}).get("steps") or []
        for step in steps:
            step_distance = step.get("distance")
            if isinstance(step_distance, (int, float)):
                total += float(step_distance)
                has_distance = True
    return total if has_distance else None


def _path_distance_m(line_string: Any) -> float | None:
    if not line_string:
        return None
    if isinstance(line_string, str):
        try:
            points = json.loads(line_string)
        except json.JSONDecodeError:
            return None
    else:
        points = line_string

    if not isinstance(points, list) or len(points) < 2:
        return None

    distance = 0.0
    previous: tuple[float, float] | None = None
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        current = (float(point[0]), float(point[1]))
        if previous is not None:
            distance += _haversine_m(previous[0], previous[1], current[0], current[1])
        previous = current
    return distance


def _haversine_m(
    latitude1: float, longitude1: float, latitude2: float, longitude2: float
) -> float:
    radius_m = 6371000
    phi1 = math.radians(latitude1)
    phi2 = math.radians(latitude2)
    delta_phi = math.radians(latitude2 - latitude1)
    delta_lambda = math.radians(longitude2 - longitude1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _journey_summary(journey: dict[str, Any]) -> str:
    parts = []
    for leg in journey.get("legs") or []:
        mode = leg.get("mode", {}).get("name")
        duration = leg.get("duration")
        if mode and duration is not None:
            parts.append(f"{mode} {duration} min")
    return ", ".join(parts)
