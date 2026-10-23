"""Fetch healthcare POIs from an Overpass API.

The module talks to a list of public Overpass mirrors, retries with
exponential back-off and caches the raw result on disk so that the project
can be rebuilt without network access.

Only the standard library is used (``urllib``), there is no hard dependency on
``requests``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

USER_AGENT = "AssiutHospitals/1.0 (SUMO hospital scenario generator)"

#: Overpass queries, one per tag combination.  Splitting the request keeps
#: each response small which makes the public mirrors much more reliable.
TAG_QUERIES: Tuple[Tuple[str, str], ...] = (
    ("amenity", "hospital"),
    ("healthcare", "hospital"),
    ("amenity", "clinic"),
    ("healthcare", "clinic"),
    ("healthcare", "centre"),
)


class OverpassError(RuntimeError):
    """Raised when no mirror could serve the query."""


def build_query(area_id: int, key: str, value: str, timeout: int = 60) -> str:
    """Build the Overpass QL query for a single tag combination."""
    return (
        "[out:json][timeout:{timeout}];"
        "area({area})->.a;"
        'nwr["{key}"="{value}"](area.a);'
        "out center tags;"
    ).format(timeout=timeout, area=area_id, key=key, value=value)


def _post(url: str, query: str, timeout: int) -> bytes:
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_query(
    query: str,
    mirrors: Sequence[str],
    timeout: int = 90,
    attempts_per_mirror: int = 3,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run one Overpass query, trying every mirror with back-off."""
    last_error: Optional[Exception] = None
    for mirror in mirrors:
        for attempt in range(attempts_per_mirror):
            try:
                raw = _post(mirror, query, timeout)
                payload = json.loads(raw.decode("utf-8"))
                if verbose:
                    print(
                        "    [overpass] {0} -> {1} elements".format(
                            mirror.rsplit("/", 2)[-3] if "/" in mirror else mirror,
                            len(payload.get("elements", [])),
                        )
                    )
                return payload
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
                    json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if verbose:
                    print(
                        "    [overpass] {0} failed ({1}), retry {2}/{3}".format(
                            mirror, exc, attempt + 1, attempts_per_mirror
                        )
                    )
                time.sleep(min(2 ** attempt, 8))
    raise OverpassError("no Overpass mirror could answer the query: {0}".format(last_error))


def fetch_healthcare(
    area_id: int,
    mirrors: Sequence[str],
    timeout: int = 90,
    verbose: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Fetch every healthcare POI inside the given Overpass area.

    Returns ``(elements, mirrors_used)``.
    """
    merged: Dict[Tuple[str, int], Dict[str, Any]] = {}
    used: List[str] = []

    for key, value in TAG_QUERIES:
        query = build_query(area_id, key, value, timeout=min(timeout, 60))
        payload = fetch_query(query, mirrors, timeout=timeout, verbose=verbose)
        for element in payload.get("elements", []):
            element_type = element.get("type")
            element_id = element.get("id")
            if not element_type or element_id is None:
                continue
            merged[(element_type, int(element_id))] = element
        used.append(key + "=" + value)

    elements = list(merged.values())
    return elements, used


def load_cache(path: Path) -> Optional[Dict[str, Any]]:
    if not Path(path).exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(path: Path, elements: Iterable[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "elements": list(elements)}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def load_or_fetch(
    cache_path: Path,
    area_id: int,
    mirrors: Sequence[str],
    timeout: int = 90,
    refresh: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Return the cached OSM payload, fetching it first when necessary."""
    cache_path = Path(cache_path)
    if not refresh:
        cached = load_cache(cache_path)
        if cached and cached.get("elements"):
            if verbose:
                print(
                    "  using cached OSM data: {0} elements ({1})".format(
                        len(cached["elements"]), cache_path
                    )
                )
            return cached

    if verbose:
        print("  querying Overpass for area {0} ...".format(area_id))
    elements, used = fetch_healthcare(
        area_id, mirrors, timeout=timeout, verbose=verbose
    )
    meta = {
        "area_id": area_id,
        "queries": used,
        "count": len(elements),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_cache(cache_path, elements, meta)
    return {"meta": meta, "elements": elements}
