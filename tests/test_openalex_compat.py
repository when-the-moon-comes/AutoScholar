from __future__ import annotations

from openalex import OpenAlexClient as CompatOpenAlexClient
from autoscholar.integrations import OpenAlexClient


def test_openalex_scripts_package_reexports_v2_client() -> None:
    assert issubclass(CompatOpenAlexClient, OpenAlexClient)
