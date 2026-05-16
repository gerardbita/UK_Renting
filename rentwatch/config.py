from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rightmove_url import RightmoveUrlOptions, build_rightmove_url


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass(slots=True)
class PollingConfig:
    delay_min_seconds: int = 1800
    delay_max_seconds: int = 3600
    page_delay_seconds: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PollingConfig":
        data = data or {}
        return cls(
            delay_min_seconds=int(data.get("delay_min_seconds", 1800)),
            delay_max_seconds=int(data.get("delay_max_seconds", 3600)),
            page_delay_seconds=float(data.get("page_delay_seconds", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "delay_min_seconds": self.delay_min_seconds,
            "delay_max_seconds": self.delay_max_seconds,
            "page_delay_seconds": self.page_delay_seconds,
        }


@dataclass(slots=True)
class HttpConfig:
    timeout_seconds: int = 20
    user_agent: str = (
        "RentWatch/0.1 personal property monitor "
        "(low-frequency; contact: local-user)"
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "HttpConfig":
        data = data or {}
        return cls(
            timeout_seconds=int(data.get("timeout_seconds", 20)),
            user_agent=str(data.get("user_agent", cls.user_agent)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "user_agent": self.user_agent,
        }


@dataclass(slots=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TelegramConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            bot_token=str(data.get("bot_token", "")),
            chat_id=str(data.get("chat_id", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bot_token": self.bot_token,
            "chat_id": self.chat_id,
        }


@dataclass(slots=True)
class NotificationConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NotificationConfig":
        data = data or {}
        return cls(telegram=TelegramConfig.from_dict(data.get("telegram")))

    def to_dict(self) -> dict[str, Any]:
        return {"telegram": self.telegram.to_dict()}


@dataclass(slots=True)
class RouteTargetConfig:
    name: str
    latitude: float
    longitude: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteTargetConfig":
        return cls(
            name=str(data.get("name") or "Target"),
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass(slots=True)
class RoutingConfig:
    enabled: bool = False
    target_name: str = ""
    target_latitude: float | None = None
    target_longitude: float | None = None
    public_transport: bool = True
    cycling: bool = True
    tfl_modes: str = "tube,bus,overground,elizabeth-line,dlr,national-rail"
    request_delay_seconds: float = 0.2
    cache_hours: float | None = None
    departure_day: str = "wednesday"
    departure_time: str = "13:00"
    targets: list[RouteTargetConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RoutingConfig":
        data = data or {}
        targets = [
            RouteTargetConfig.from_dict(item)
            for item in data.get("targets", [])
        ]
        target_latitude = _optional_float(data.get("target_latitude"))
        target_longitude = _optional_float(data.get("target_longitude"))
        if not targets and target_latitude is not None and target_longitude is not None:
            targets = [
                RouteTargetConfig(
                    name=str(data.get("target_name", "")) or "Target",
                    latitude=target_latitude,
                    longitude=target_longitude,
                )
            ]
        return cls(
            enabled=bool(data.get("enabled", False)),
            target_name=str(data.get("target_name", "")),
            target_latitude=target_latitude,
            target_longitude=target_longitude,
            public_transport=bool(data.get("public_transport", True)),
            cycling=bool(data.get("cycling", True)),
            tfl_modes=str(
                data.get("tfl_modes", "tube,bus,overground,elizabeth-line,dlr,national-rail")
            ),
            request_delay_seconds=float(data.get("request_delay_seconds", 0.2)),
            cache_hours=_optional_float(data.get("cache_hours")),
            departure_day=str(data.get("departure_day", "wednesday")),
            departure_time=str(data.get("departure_time", "13:00")),
            targets=targets,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "target_name": self.target_name,
            "target_latitude": self.target_latitude,
            "target_longitude": self.target_longitude,
            "public_transport": self.public_transport,
            "cycling": self.cycling,
            "tfl_modes": self.tfl_modes,
            "request_delay_seconds": self.request_delay_seconds,
            "cache_hours": self.cache_hours,
            "departure_day": self.departure_day,
            "departure_time": self.departure_time,
            "targets": [target.to_dict() for target in self.targets],
        }


@dataclass(slots=True)
class SearchConfig:
    name: str
    url: str = ""
    rightmove: RightmoveUrlOptions | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_price_pcm: int | None = None
    max_price_pcm: int | None = None
    notify_new: bool = True
    notify_price_changes: bool = True
    notify_removed: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchConfig":
        rightmove_data = data.get("rightmove")
        return cls(
            name=str(data["name"]),
            url=str(data.get("url", "")),
            rightmove=(
                RightmoveUrlOptions.from_dict(rightmove_data)
                if rightmove_data is not None
                else None
            ),
            include_keywords=[str(item).lower() for item in data.get("include_keywords", [])],
            exclude_keywords=[str(item).lower() for item in data.get("exclude_keywords", [])],
            min_price_pcm=_optional_int(data.get("min_price_pcm")),
            max_price_pcm=_optional_int(data.get("max_price_pcm")),
            notify_new=bool(data.get("notify_new", True)),
            notify_price_changes=bool(data.get("notify_price_changes", True)),
            notify_removed=bool(data.get("notify_removed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "include_keywords": self.include_keywords,
            "exclude_keywords": self.exclude_keywords,
            "min_price_pcm": self.min_price_pcm,
            "max_price_pcm": self.max_price_pcm,
            "notify_new": self.notify_new,
            "notify_price_changes": self.notify_price_changes,
            "notify_removed": self.notify_removed,
        }
        if self.url:
            data["url"] = self.url
        if self.rightmove is not None:
            data["rightmove"] = self.rightmove.to_dict()
        return data

    def resolved_url(self) -> str:
        if self.url:
            return self.url
        if self.rightmove is not None:
            return build_rightmove_url(self.rightmove)
        raise ValueError(f"Search {self.name!r} has neither url nor rightmove config.")


@dataclass(slots=True)
class AppConfig:
    database: str = "rentwatch.sqlite3"
    polling: PollingConfig = field(default_factory=PollingConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    searches: list[SearchConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            database=str(data.get("database", "rentwatch.sqlite3")),
            polling=PollingConfig.from_dict(data.get("polling")),
            http=HttpConfig.from_dict(data.get("http")),
            notifications=NotificationConfig.from_dict(data.get("notifications")),
            routing=RoutingConfig.from_dict(data.get("routing")),
            searches=[SearchConfig.from_dict(item) for item in data.get("searches", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "polling": self.polling.to_dict(),
            "http": self.http.to_dict(),
            "notifications": self.notifications.to_dict(),
            "routing": self.routing.to_dict(),
            "searches": [search.to_dict() for search in self.searches],
        }

    def resolve_database_path(self, config_path: Path) -> Path:
        db_path = Path(self.database).expanduser()
        if db_path.is_absolute():
            return db_path
        return config_path.resolve().parent / db_path


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()
    with path.open("r", encoding="utf-8") as handle:
        return AppConfig.from_dict(json.load(handle))


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, indent=2)
        handle.write("\n")


def sample_config() -> AppConfig:
    return AppConfig(
        routing=RoutingConfig(
            enabled=True,
            target_name="London target",
            target_latitude=51.5209823,
            target_longitude=-0.1770073,
            targets=[
                RouteTargetConfig(
                    name="Paddington target",
                    latitude=51.5209823,
                    longitude=-0.1770073,
                ),
                RouteTargetConfig(
                    name="Second target",
                    latitude=51.4928449,
                    longitude=-0.2198001,
                ),
            ],
            public_transport=True,
            cycling=True,
        ),
        searches=[
            SearchConfig(
                name="Example W2 garden unfurnished",
                url=(
                    "https://www.rightmove.co.uk/property-to-rent/find.html?"
                    "searchLocation=W2+1SJ&useLocationIdentifier=true&"
                    "locationIdentifier=POSTCODE%5E918640&rent=To+rent&radius=5.0&"
                    "maxPrice=2250&index=0&sortType=6&channel=RENT&"
                    "transactionType=LETTING&displayLocationIdentifier=undefined&"
                    "propertyTypes=detached%2Csemi-detached%2Cterraced%2Cflat%2Cbungalow&"
                    "minBedrooms=1&minPrice=1000&"
                    "dontShow=houseShare%2Cretirement%2Cstudent&mustHave=garden&"
                    "furnishTypes=unfurnished%2CpartFurnished"
                ),
                include_keywords=[],
                exclude_keywords=["student", "short let"],
                min_price_pcm=1000,
                max_price_pcm=2250,
            )
        ]
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
