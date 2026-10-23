"""Assiut Hospitals - map + hospital-routed ambulances on the Assiut SUMO network.

Public API (stable, used for integration into other simulations):

    from assiut_hospitals import load_dataset, snap_point, open_network

`load_dataset()` returns the generated dataset (see `assiut_hospitals.emit`).
`snap_point(lat, lon)` snaps a geo coordinate onto the SUMO network.
`open_network()` returns the parsed network model.
"""

from .config import Config, load_config
from .dataset import Dataset, Hospital, load_dataset
from .dispatch import Dispatcher, DispatchResult
from .dispatch_config import DispatchConfig, Zone, load_dispatch_config
from .netmodel import Network, open_network
from .projection import NetProjection, Projection
from .snapping import SnapResult, snap_point
from .traveltime import TimeModel

__version__ = "1.0.0"

__all__ = [
    "Config",
    "Dataset",
    "DispatchConfig",
    "DispatchResult",
    "Dispatcher",
    "Hospital",
    "NetProjection",
    "Network",
    "Projection",
    "SnapResult",
    "TimeModel",
    "Zone",
    "load_config",
    "load_dataset",
    "load_dispatch_config",
    "open_network",
    "snap_point",
    "__version__",
]
