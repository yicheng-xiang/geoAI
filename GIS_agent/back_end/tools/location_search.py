"""Resolve Hong Kong place names with the Lands Department Location Search API."""

from copy import deepcopy
from difflib import SequenceMatcher
import json
import re
import threading
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pyproj import Transformer


LOCATION_SEARCH_ENDPOINT = "https://www.map.gov.hk/gs/api/v1.0.0/locationSearch"
LOCATION_SEARCH_DOCS = "https://portal.csdi.gov.hk/csdi-webpage/apidoc/LocationSearchAPI"
PROVIDER_NAME = "Lands Department Location Search API"
HK80_CRS = "EPSG:2326"
WGS84_CRS = "EPSG:4326"
MAX_QUERY_LENGTH = 200
MAX_RESPONSE_BYTES = 1_000_000
CACHE_TTL_SECONDS = 24 * 60 * 60
MIN_REQUEST_INTERVAL_SECONDS = 1.0

_CACHE = {}
_CACHE_LOCK = threading.RLock()
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_HK80_TO_WGS84 = Transformer.from_crs(HK80_CRS, WGS84_CRS, always_xy=True)


class LocationSearchError(RuntimeError):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _clean_query(value):
    query = unicodedata.normalize("NFKC", str(value or "")).strip()
    query = re.sub(r"\s+", " ", query)
    if not query:
        raise LocationSearchError(
            "MISSING_LOCATION_QUERY",
            "Provide a Hong Kong place, building, facility, or address to search.",
        )
    if len(query) > MAX_QUERY_LENGTH:
        raise LocationSearchError(
            "LOCATION_QUERY_TOO_LONG",
            f"The location query must not exceed {MAX_QUERY_LENGTH} characters.",
        )
    return query


def _canonical_query(query):
    """Normalize the common PolyU 'Core Z' wording to the official 'Block Z' name."""
    polyu_reference = re.search(
        r"(?:hong\s*kong\s*polytechnic|poly\s*u|polyu|香港理工|理工大学|理工大學)",
        query,
        re.IGNORECASE,
    )
    if not polyu_reference:
        return query

    block_match = re.search(
        r"(?:core|block|座)\s*([a-z])\b|(?<![a-z])([a-z])\s*(?:core|block|座)",
        query,
        re.IGNORECASE,
    )
    if not block_match:
        block_match = re.search(r'(?<![a-z])([a-z])\s*(?:栋|棟|楼|樓)?$', query, re.IGNORECASE)
    if not block_match:
        return query
    block = next(group for group in block_match.groups() if group).upper()
    return f"Hong Kong Polytechnic University Block {block}"


def _fetch_location_results(query, timeout_seconds):
    global _LAST_REQUEST_AT
    url = f"{LOCATION_SEARCH_ENDPOINT}?{urlencode({'q': query})}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GeoAI-HK-Facility-Analysis/1.0",
        },
    )
    with _REQUEST_LOCK:
        remaining_wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _LAST_REQUEST_AT)
        if remaining_wait > 0:
            time.sleep(remaining_wait)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise LocationSearchError(
                "GEOCODING_SERVICE_ERROR",
                f"The Lands Department location service returned HTTP {exc.code}.",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LocationSearchError(
                "GEOCODING_SERVICE_UNAVAILABLE",
                "The Lands Department location service is temporarily unavailable. Try again later or provide WGS84 coordinates.",
            ) from exc
        finally:
            _LAST_REQUEST_AT = time.monotonic()

    if len(content) > MAX_RESPONSE_BYTES:
        raise LocationSearchError(
            "GEOCODING_RESPONSE_TOO_LARGE",
            "The location service returned an unexpectedly large response.",
        )
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocationSearchError(
            "INVALID_GEOCODING_RESPONSE",
            "The location service returned an invalid response.",
        ) from exc
    if not isinstance(payload, list):
        raise LocationSearchError(
            "INVALID_GEOCODING_RESPONSE",
            "The location service response did not contain a candidate list.",
        )
    return payload


def _valid_candidate(candidate):
    if not isinstance(candidate, dict):
        return None
    try:
        x = float(candidate["x"])
        y = float(candidate["y"])
        longitude, latitude = _HK80_TO_WGS84.transform(x, y)
    except (KeyError, TypeError, ValueError):
        return None
    if not (113.7 <= longitude <= 114.6 and 22.0 <= latitude <= 22.7):
        return None
    name_en = str(candidate.get("nameEN") or "").strip()
    name_zh = str(candidate.get("nameZH") or "").strip()
    return {
        "name": name_en or name_zh or "Matched location",
        "name_en": name_en,
        "name_zh": name_zh,
        "address_en": str(candidate.get("addressEN") or "").strip(),
        "address_zh": str(candidate.get("addressZH") or "").strip(),
        "district_en": str(candidate.get("districtEN") or "").strip(),
        "district_zh": str(candidate.get("districtZH") or "").strip(),
        "hk80_x": x,
        "hk80_y": y,
        "longitude": float(longitude),
        "latitude": float(latitude),
    }


def search_hong_kong_location(location_query, timeout_seconds=10):
    """Return the highest-ranked valid official location result with provenance."""
    original_query = _clean_query(location_query)
    submitted_query = _canonical_query(original_query)
    cache_key = submitted_query.casefold()
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached["cached_at"] <= CACHE_TTL_SECONDS:
            result = deepcopy(cached["result"])
            result["cache_hit"] = True
            result["original_query"] = original_query
            return result

    candidates = _fetch_location_results(submitted_query, float(timeout_seconds))
    valid_candidates = [candidate for item in candidates if (candidate := _valid_candidate(item))]
    if not valid_candidates:
        raise LocationSearchError(
            "LOCATION_NOT_FOUND",
            f"No Hong Kong location matched '{original_query}'. Try a more specific building name or address.",
        )

    # Official search returns fuzzy suggestions even for nonexistent places.
    # A valid coordinate alone is not evidence that it matches the request.
    def normalize(text):
        return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', text).casefold())

    query = normalize(submitted_query)
    requested_block = re.search(r'\bblock\s+([a-z])\b', submitted_query, re.I)
    def relevance(candidate):
        candidate_block = re.search(r'\bblock\s+([a-z])\b', candidate['name_en'], re.I)
        if requested_block and (not candidate_block or requested_block[1].lower() != candidate_block[1].lower()):
            return 0
        names = [normalize(candidate[k]) for k in ('name_en', 'name_zh', 'address_en', 'address_zh') if candidate[k]]
        return max((1.0 if query == name or (len(query) >= 4 and query in name)
                    else min(.89, SequenceMatcher(None, query, name).ratio()) for name in names), default=0)

    ranked = sorted(enumerate(valid_candidates, 1), key=lambda pair: relevance(pair[1]), reverse=True)
    rank, chosen = ranked[0]
    score = relevance(chosen)
    ambiguous = len(ranked) > 1 and score >= .72 and relevance(ranked[1][1]) >= score - .02 and (
        abs(chosen['longitude'] - ranked[1][1]['longitude']) + abs(chosen['latitude'] - ranked[1][1]['latitude']) > .0001)
    if score < .72 or ambiguous:
        raise LocationSearchError('LOCATION_CONFIRMATION_REQUIRED',
            f"Uncertain location match for '{original_query}'. Specify an exact candidate name or WGS84 coordinates; the previous map is unchanged. Candidates: " +
            '; '.join(c['name'] for _, c in ranked[:5]),
            data={'query': original_query, 'candidates': [c['name'] for _, c in ranked[:5]]})
    result = {
        **chosen,
        "original_query": original_query,
        "submitted_query": submitted_query,
        "candidate_count": len(valid_candidates),
        "selection_rank": rank,
        "match_score": score,
        "provider": PROVIDER_NAME,
        "provider_url": LOCATION_SEARCH_DOCS,
        "source_crs": HK80_CRS,
        "output_crs": WGS84_CRS,
        "cache_hit": False,
    }
    with _CACHE_LOCK:
        _CACHE[cache_key] = {"cached_at": now, "result": deepcopy(result)}
    return result
