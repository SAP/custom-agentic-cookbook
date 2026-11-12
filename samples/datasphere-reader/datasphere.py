"""Bounded, read-only OAuth/OData adapter. It never accepts a raw query from a model."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")
MAX_RESPONSE_BYTES = 1048576


class ReaderError(RuntimeError):
    """Safe adapter error without credentials, endpoint URLs, or response bodies."""


def identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("expected a technical identifier with at most 128 characters")
    return value


def endpoint(value: str, *, allow_http: bool) -> str:
    try:
        url = urlsplit(value)
        host = url.hostname
        _ = url.port
        httpx.URL(value)
    except (ValueError, httpx.InvalidURL):
        raise ValueError("endpoint is malformed") from None
    if url.username or url.password or url.query or url.fragment or not host:
        raise ValueError("endpoint must contain a host and no credentials, query, or fragment")
    if url.scheme != "https" and not (
        allow_http and url.scheme == "http" and host in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("HTTPS is required except for explicitly enabled loopback fixtures")
    return value.rstrip("/")


class DatasphereReader:
    def __init__(
        self,
        *,
        base_url: str,
        space: str,
        view: str,
        shape: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        transport=None,
        clock: Callable[[], float] = time.monotonic,
        allow_http: bool = False,
    ):
        if shape not in {"A", "B"}:
            raise ValueError("shape must be A (space service) or B (view service)")
        base = endpoint(base_url, allow_http=allow_http)
        self.token_url = endpoint(token_url, allow_http=allow_http)
        self.view = identifier(view)
        identifier(space)
        if not client_id or not client_secret:
            raise ValueError("OAuth client credentials are required")
        self.service = base + "/" if shape == "A" else f"{base}/{quote(space)}/{quote(view)}/"
        self.shape = shape
        self.auth = httpx.BasicAuth(client_id, client_secret)
        self.clock = clock
        self.token = ""
        self.expires = 0.0
        self.http = httpx.AsyncClient(
            timeout=20,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept-Encoding": "identity"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.http.aclose()

    async def _request(self, method, url, **kwargs):
        try:
            async with self.http.stream(method, url, **kwargs) as response:
                if (
                    response.headers.get("Content-Encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise ReaderError("Datasphere response encoding must be identity")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ReaderError("Datasphere response exceeds the one MiB bound")
                    body.extend(chunk)
                # Keep only the bounded body needed by OAuth and OData decoding.
                return httpx.Response(response.status_code, content=bytes(body))
        except httpx.HTTPError:
            raise ReaderError("Datasphere network request failed") from None

    async def _token(self):
        if self.token and self.clock() < self.expires:
            return self.token
        response = await self._request(
            "POST", self.token_url, auth=self.auth, data={"grant_type": "client_credentials"}
        )
        if response.status_code != 200:
            raise ReaderError(f"OAuth request failed with HTTP {response.status_code}")
        try:
            data = response.json()
            token, seconds = data["access_token"], float(data["expires_in"])
            if (
                not isinstance(token, str)
                or not token
                or not math.isfinite(seconds)
                or seconds <= 0
            ):
                raise ValueError("invalid token response")
        except (ValueError, TypeError, KeyError):
            raise ReaderError("OAuth returned a malformed token response") from None
        self.token = token
        self.expires = self.clock() + max(0, seconds - min(10, seconds / 10))
        return token

    async def _get(self, url, params=None):
        for attempt in range(2):
            response = await self._request(
                "GET",
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {await self._token()}",
                    "Accept": "application/json",
                },
            )
            if response.status_code == 401 and attempt == 0:
                self.token = ""
                continue
            if response.status_code != 200:
                raise ReaderError(f"Datasphere request failed with HTTP {response.status_code}")
            try:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("value"), list):
                    raise ValueError("expected an OData row envelope")
            except ValueError:
                raise ReaderError("Datasphere returned malformed OData") from None
            return data
        raise ReaderError("Datasphere authorization failed")

    def _scoped_url(self, request_url, link, collection):
        if not isinstance(link, str) or not link:
            raise ReaderError("invalid OData continuation")
        try:
            resolved = urljoin(request_url, link)
            candidate, expected = urlsplit(resolved), urlsplit(collection)
            httpx.URL(resolved)
        except (ValueError, httpx.InvalidURL):
            raise ReaderError("invalid OData continuation") from None
        if (candidate.scheme, candidate.netloc, candidate.path) != (
            expected.scheme,
            expected.netloc,
            expected.path,
        ) or candidate.fragment:
            raise ReaderError("OData continuation leaves the configured collection")
        return resolved

    async def read(
        self,
        *,
        select: list[str],
        equal: dict[str, str] | None = None,
        limit: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be 1-1000")
        if not isinstance(max_pages, int) or not 1 <= max_pages <= 100:
            raise ValueError("max_pages must be 1-100")
        if not select or len(select) > 32:
            raise ValueError("select must contain 1-32 fields")
        fields = [identifier(field) for field in select]
        clauses = []
        for field, value in (equal or {}).items():
            identifier(field)
            if not isinstance(value, str) or len(value) > 256:
                raise ValueError("filter values must be strings with at most 256 characters")
            clauses.append(field + " eq '" + value.replace("'", "''") + "'")
        collection = self.service + quote(self.view)
        if self.shape == "B":
            listing = (await self._get(self.service))["value"]
            if len(listing) != 1 or not isinstance(listing[0], dict):
                raise ReaderError("view must expose exactly one inner entity set")
            try:
                name = identifier(listing[0]["name"])
            except (KeyError, ValueError):
                raise ReaderError("view returned a malformed entity-set listing") from None
            collection = self.service + quote(name)
            if listing[0].get("url") != name:
                raise ReaderError("view listing URL does not match its entity-set name")
        params = {"$select": ",".join(fields), "$top": str(limit)}
        if clauses:
            params["$filter"] = " and ".join(clauses)
        url, rows, seen = collection, [], set()
        for _ in range(max_pages):
            key = str(httpx.URL(url, params=params)) if params else url
            if key in seen:
                raise ReaderError("repeated OData continuation")
            seen.add(key)
            payload = await self._get(url, params)
            for row in payload["value"]:
                if not isinstance(row, dict) or any(field not in row for field in fields):
                    raise ReaderError("OData row does not satisfy the selected field contract")
                rows.append({field: row[field] for field in fields})
                if len(rows) == limit:
                    return rows
            link = payload.get("@odata.nextLink")
            if link is None:
                return rows
            url = self._scoped_url(key, link, collection)
            params = None
        raise ReaderError("OData pagination exceeded max_pages")
