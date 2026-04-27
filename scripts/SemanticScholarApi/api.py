from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import requests


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if SRC_ROOT.exists() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autoscholar.integrations.semantic_scholar import SemanticScholarClient as _V2SemanticScholarClient


class _CompatHTTPStatusError(httpx.HTTPStatusError, requests.exceptions.HTTPError):
    pass


class _CompatTimeoutError(httpx.TimeoutException, requests.exceptions.Timeout):
    pass


class _CompatTransportError(httpx.TransportError, requests.exceptions.ConnectionError):
    pass


class _CompatRequestError(httpx.HTTPError, requests.exceptions.RequestException):
    pass


class SemanticScholarClient(_V2SemanticScholarClient):
    """Compatibility import path for first-version scripts.

    New code should import ``autoscholar.integrations.SemanticScholarClient``.
    This wrapper keeps old ``SemanticScholarApi`` scripts working while routing
    all HTTP behavior through the v2 client.
    """

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return super()._request(method, url, **kwargs)
        except httpx.HTTPStatusError as exc:
            raise _CompatHTTPStatusError(
                str(exc),
                request=exc.request,
                response=exc.response,
            ) from exc
        except httpx.TimeoutException as exc:
            raise _CompatTimeoutError(str(exc), request=exc.request) from exc
        except httpx.TransportError as exc:
            raise _CompatTransportError(str(exc), request=exc.request) from exc
        except httpx.HTTPError as exc:
            raise _CompatRequestError(str(exc)) from exc


__all__ = ["SemanticScholarClient"]
