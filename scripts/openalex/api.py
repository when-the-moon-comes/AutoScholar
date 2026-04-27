from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if SRC_ROOT.exists() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autoscholar.integrations.openalex import OpenAlexClient as _V2OpenAlexClient


class OpenAlexClient(_V2OpenAlexClient):
    """Compatibility import path for standalone OpenAlex scripts.

    New code should import ``autoscholar.integrations.OpenAlexClient``.
    This wrapper keeps scripts under ``scripts/openalex`` aligned with the
    package client used by the AutoScholar CLI.
    """


__all__ = ["OpenAlexClient"]
