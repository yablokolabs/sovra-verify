"""Sovra Verify backend package.

Default application inference: ``swiss-ai/Apertus-v1.5-70B`` on CSCS, with the
Hugging Face router available as an explicitly activated backup. The 8B models
are optional and are never selected automatically.
"""

from .config import DEFAULT_MODEL, OPTIONAL_8B_MODEL, Settings, load_settings, mask_secret
from .pipeline import PROTOTYPE_NOTICE, SovraService, summarise_runs
from .storage import Storage

__all__ = [
    "DEFAULT_MODEL",
    "OPTIONAL_8B_MODEL",
    "PROTOTYPE_NOTICE",
    "Settings",
    "SovraService",
    "Storage",
    "load_settings",
    "mask_secret",
    "summarise_runs",
]

__version__ = "0.1.0"
