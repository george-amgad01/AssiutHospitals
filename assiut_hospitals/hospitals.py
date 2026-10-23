"""Normalisation of raw OSM healthcare elements into hospital records."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

CATEGORY_HOSPITAL = "hospital"
CATEGORY_CLINIC = "clinic"
CATEGORY_HEALTH_CENTRE = "health_centre"
CATEGORY_OTHER = "other"

CATEGORY_LABELS = {
    CATEGORY_HOSPITAL: "Hospital",
    CATEGORY_CLINIC: "Clinic",
    CATEGORY_HEALTH_CENTRE: "Health centre",
    CATEGORY_OTHER: "Healthcare",
}


def contains_arabic(text: str) -> bool:
    return bool(text) and bool(ARABIC_RE.search(text))


def slugify(text: str, fallback: str = "facility") -> str:
    """ASCII slug; Arabic names are transliterated by the OSM id instead."""
    if not text:
        return fallback
    normalised = unicodedata.normalize("NFKD", text)
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_RE.sub("-", ascii_text).strip("-")
    return slug or fallback


@dataclass
class Hospital:
    """A single healthcare POI."""

    osm_type: str
    osm_id: int
    name: str = ""
    name_ar: str = ""
    name_en: str = ""
    category: str = CATEGORY_OTHER
    lat: float = 0.0
    lon: float = 0.0
    emergency: bool = False
    tags: Dict[str, str] = field(default_factory=dict)
    merged_from: List[str] = field(default_factory=list)

    @property
    def osm_key(self) -> str:
        return "{0}/{1}".format(self.osm_type, self.osm_id)

    @property
    def slug(self) -> str:
        if self.name_en:
            base = slugify(self.name_en)
        elif self.name and not contains_arabic(self.name):
            base = slugify(self.name)
        else:
            base = "osm-{0}-{1}".format(self.osm_type, self.osm_id)
        return base

    @property
    def display_name(self) -> str:
        if self.name_en:
            return self.name_en
        if self.name and not contains_arabic(self.name):
            return self.name
        if self.name_ar:
            return self.name_ar
        if self.name:
            return self.name
        return "Unnamed {0} ({1}/{2})".format(
            CATEGORY_LABELS.get(self.category, "facility").lower(),
            self.osm_type,
            self.osm_id,
        )

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, "Healthcare")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "name": self.name,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "display_name": self.display_name,
            "category": self.category,
            "category_label": self.category_label,
            "emergency": self.emergency,
            "lat": self.lat,
            "lon": self.lon,
        }


def _element_position(element: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is None or lon is None:
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _categorise(tags: Dict[str, str]) -> str:
    amenity = (tags.get("amenity") or "").lower()
    healthcare = (tags.get("healthcare") or "").lower()
    if amenity == "hospital" or healthcare == "hospital":
        return CATEGORY_HOSPITAL
    if amenity in ("clinic", "doctors", "pharmacy") or healthcare in ("clinic", "doctor"):
        return CATEGORY_CLINIC
    if healthcare in ("centre", "center"):
        return CATEGORY_HEALTH_CENTRE
    if amenity or healthcare:
        return CATEGORY_OTHER
    return CATEGORY_OTHER


def _pick_names(tags: Dict[str, str]) -> Tuple[str, str, str]:
    """Return ``(name, name_ar, name_en)``."""
    raw_name = (tags.get("name") or "").strip()
    name_ar = (tags.get("name:ar") or "").strip()
    name_en = (tags.get("name:en") or "").strip()

    if raw_name:
        if contains_arabic(raw_name):
            name_ar = name_ar or raw_name
        else:
            name_en = name_en or raw_name

    if not raw_name:
        raw_name = name_ar or name_en

    if not name_en:
        for key in ("official_name", "short_name", "int_name", "name:en", "operator"):
            value = (tags.get(key) or "").strip()
            if value and not contains_arabic(value):
                name_en = value
                break

    return raw_name, name_ar, name_en


def _is_emergency(tags: Dict[str, str]) -> bool:
    value = (tags.get("emergency") or "").strip().lower()
    return value in ("yes", "true", "1")


def element_to_hospital(element: Dict[str, Any]) -> Optional[Hospital]:
    """Convert one raw Overpass element into a :class:`Hospital`."""
    position = _element_position(element)
    if position is None:
        return None
    lat, lon = position
    tags = {k: v for k, v in (element.get("tags") or {}).items() if isinstance(v, str)}
    name, name_ar, name_en = _pick_names(tags)
    return Hospital(
        osm_type=str(element.get("type", "node")),
        osm_id=int(element.get("id", 0)),
        name=name,
        name_ar=name_ar,
        name_en=name_en,
        category=_categorise(tags),
        lat=lat,
        lon=lon,
        emergency=_is_emergency(tags),
        tags=tags,
    )


def _haversine(a: Hospital, b: Hospital) -> float:
    radius = 6371000.0
    p1 = math.radians(a.lat)
    p2 = math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def dedupe(hospitals: Iterable[Hospital], radius_m: float = 30.0) -> List[Hospital]:
    """Merge facilities that are the same place.

    OSM occasionally maps the same hospital twice (for example a building and
    its entrance, a few metres apart).  Facilities whose display names match
    and which are closer than ``radius_m`` are merged into a single record.
    """
    ordered = sorted(hospitals, key=lambda h: (-len(h.tags), h.osm_key))
    kept: List[Hospital] = []
    for hospital in ordered:
        merged = False
        for existing in kept:
            if existing.display_name != hospital.display_name:
                continue
            if _haversine(existing, hospital) <= radius_m:
                existing.merged_from.append(hospital.osm_key)
                merged = True
                break
        if not merged:
            kept.append(hospital)
    return kept


def hospitals_from_elements(elements: Iterable[Dict[str, Any]]) -> List[Hospital]:
    hospitals: List[Hospital] = []
    for element in elements:
        hospital = element_to_hospital(element)
        if hospital is not None:
            hospitals.append(hospital)
    hospitals = dedupe(hospitals)
    hospitals.sort(key=lambda h: (h.category != CATEGORY_HOSPITAL, h.display_name.lower()))
    return hospitals
