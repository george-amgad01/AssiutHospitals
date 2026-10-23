"""Pure-python UTM (WGS84) <-> geographic conversions.

`pyproj` is not available in this environment, so the standard USGS / Krueger
series is implemented here.  Over a single UTM zone the series is accurate to
well below a millimetre, which is far more than enough for a city-scale
simulation.

The SUMO network stores coordinates in a *local* frame.  The `<location>`
element of `net.xml` carries the `netOffset` that relates the local frame to
the geographic projection used when the network was imported:

    local_x = utm_easting  + netOffset_x
    local_y = utm_northing + netOffset_y

`NetProjection` encapsulates that relation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

# --- WGS84 ellipsoid -------------------------------------------------------
SEMI_MAJOR_A = 6378137.0
INVERSE_FLATTENING_F = 1.0 / 298.257223563
K0 = 0.9996
E2 = INVERSE_FLATTENING_F * (2.0 - INVERSE_FLATTENING_F)
EP2 = E2 / (1.0 - E2)


def lonlat_to_utm(lon: float, lat: float, zone: int = 36, northern: bool = True) -> Tuple[float, float]:
    """Convert geographic coordinates to UTM easting/northing (metres)."""
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    phi = math.radians(lat)
    lam = math.radians(lon)

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    n = SEMI_MAJOR_A / math.sqrt(1.0 - E2 * sin_phi * sin_phi)
    t = tan_phi * tan_phi
    c = EP2 * cos_phi * cos_phi
    a_ = cos_phi * (lam - lon0)
    m = SEMI_MAJOR_A * (
        (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * phi
        - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024) * math.sin(2 * phi)
        + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * math.sin(4 * phi)
        - (35 * E2 ** 3 / 3072) * math.sin(6 * phi)
    )

    easting = 500000.0 + K0 * n * (
        a_ + (1 - t + c) * a_ ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a_ ** 5 / 120
    )
    northing = K0 * (
        m
        + n * tan_phi * a_ ** 2 / 2
        + n * tan_phi ** 3 * (5 - t + 9 * c + 4 * c * c) * a_ ** 4 / 24
        + n * tan_phi ** 5 * (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a_ ** 6 / 720
    )
    if not northern:
        northing += 10000000.0
    return easting, northing


def utm_to_lonlat(
    easting: float,
    northing: float,
    zone: int = 36,
    northern: bool = True,
) -> Tuple[float, float]:
    """Convert UTM easting/northing (metres) back to (lon, lat)."""
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    x = easting - 500000.0
    y = northing if northern else northing - 10000000.0

    m = y / K0
    mu = m / (SEMI_MAJOR_A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
        + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    )

    sin_p, cos_p, tan_p = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = EP2 * cos_p * cos_p
    t1 = tan_p * tan_p
    n1 = SEMI_MAJOR_A / math.sqrt(1 - E2 * sin_p * sin_p)
    r1 = SEMI_MAJOR_A * (1 - E2) / (1 - E2 * sin_p * sin_p) ** 1.5
    d = x / (n1 * K0)

    lat = phi1 - (n1 * tan_p / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720
    )
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120
    ) / cos_p
    return math.degrees(lon), math.degrees(lat)


@dataclass(frozen=True)
class Projection:
    """A plain UTM projection (no local network offset)."""

    zone: int = 36
    northern: bool = True

    def to_local(self, lon: float, lat: float) -> Tuple[float, float]:
        easting, northing = lonlat_to_utm(lon, lat, self.zone, self.northern)
        return easting, northing

    def to_geo(self, x: float, y: float) -> Tuple[float, float]:
        return utm_to_lonlat(x, y, self.zone, self.northern)


@dataclass(frozen=True)
class NetProjection(Projection):
    """Projection between geographic coordinates and the SUMO local frame.

    Parameters
    ----------
    net_offset:
        The `(x, y)` offset taken from the `<location>` element of `net.xml`.
    """

    net_offset: Tuple[float, float] = (0.0, 0.0)

    def to_local(self, lon: float, lat: float) -> Tuple[float, float]:
        easting, northing = lonlat_to_utm(lon, lat, self.zone, self.northern)
        return easting + self.net_offset[0], northing + self.net_offset[1]

    def to_geo(self, x: float, y: float) -> Tuple[float, float]:
        return utm_to_lonlat(
            x - self.net_offset[0],
            y - self.net_offset[1],
            self.zone,
            self.northern,
        )


def parse_proj_parameter(proj_parameter: str, fallback_zone: int = 36) -> int:
    """Extract the UTM zone from a SUMO ``+proj=utm +zone=36`` style string."""
    if not proj_parameter:
        return fallback_zone
    for token in proj_parameter.replace("+", " +").split():
        if token.startswith("zone="):
            try:
                return int(float(token.split("=", 1)[1]))
            except ValueError:
                continue
    return fallback_zone
