import logging
import time
from datetime import timedelta

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import GeocodeCache

logger = logging.getLogger('apps.assistant')

RATE_KEY = 'geocode-rate-last'


class GeocodeServiceError(Exception):
    pass


def _unique_queries(address, address_remark, pincode, ai_queries=None):
    queries = []
    seen = set()
    for item in ai_queries or []:
        if not isinstance(item, dict):
            continue
        query = str(item.get('query') or '').strip()
        kind = item.get('kind')
        if query and kind in ('address', 'landmark', 'pincode'):
            key = query.lower()
            if key not in seen:
                seen.add(key)
                queries.append({'query': query, 'kind': kind})

    deterministic = []
    address = (address or '').strip()
    address_remark = (address_remark or '').strip()
    pincode = (pincode or '').strip()
    if address:
        deterministic.append(
            {
                'query': ', '.join(part for part in (address, pincode, 'India') if part),
                'kind': 'address',
            }
        )
    if address_remark:
        deterministic.append(
            {
                'query': ', '.join(
                    part for part in (address_remark, pincode, 'India') if part
                ),
                'kind': 'landmark',
            }
        )
    if pincode:
        deterministic.append(
            {'query': f'{pincode}, India', 'kind': 'pincode'}
        )

    for item in deterministic:
        key = item['query'].lower()
        if key not in seen:
            seen.add(key)
            queries.append(item)
    return queries[:3]


def _respect_rate_limit():
    last = cache.get(RATE_KEY)
    now = time.time()
    if last:
        wait = 1.1 - (now - float(last))
        if wait > 0:
            time.sleep(wait)
    cache.set(RATE_KEY, time.time(), timeout=5)


def _search_nominatim(query):
    cutoff = timezone.now() - timedelta(days=settings.GEOCODE_CACHE_DAYS)
    cached = GeocodeCache.objects.filter(
        query=query,
        fetched_at__gte=cutoff,
    ).first()
    if cached is not None:
        return cached.response

    _respect_rate_limit()
    try:
        with httpx.Client(timeout=settings.GEOCODE_TIMEOUT) as client:
            response = client.get(
                f'{settings.GEOCODE_BASE_URL.rstrip("/")}/search',
                params={
                    'q': query,
                    'format': 'jsonv2',
                    'addressdetails': 1,
                    'limit': 1,
                    'countrycodes': 'in',
                },
                headers={
                    'User-Agent': settings.GEOCODE_USER_AGENT,
                    'Accept': 'application/json',
                },
            )
    except httpx.HTTPError as exc:
        raise GeocodeServiceError(
            'The OpenStreetMap geocoding service is unavailable.'
        ) from exc

    if response.status_code in (429, 403):
        raise GeocodeServiceError(
            'The OpenStreetMap geocoding service is rate-limiting requests.'
        )
    if not response.is_success:
        raise GeocodeServiceError(
            'The OpenStreetMap geocoding service rejected the request.'
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise GeocodeServiceError(
            'The OpenStreetMap geocoding service returned invalid data.'
        ) from exc

    results = payload if isinstance(payload, list) else []
    GeocodeCache.objects.update_or_create(
        query=query,
        defaults={'response': results, 'provider': 'nominatim'},
    )
    return results


def geocode_location(address, address_remark, pincode, ai_queries=None):
    queries = _unique_queries(
        address,
        address_remark,
        pincode,
        ai_queries=ai_queries,
    )
    if not queries:
        return {
            'status': 'not_found',
            'label': '',
            'provider': 'nominatim',
            'latitude': None,
            'longitude': None,
            'map_radius_m': None,
            'queries': [],
        }

    for item in queries:
        try:
            results = _search_nominatim(item['query'])
        except GeocodeServiceError:
            raise
        if not results:
            continue
        result = results[0]
        try:
            latitude = float(result['lat'])
            longitude = float(result['lon'])
        except (KeyError, TypeError, ValueError):
            continue
        kind = item['kind']
        radius = {'address': 150, 'landmark': 600, 'pincode': 2500}[kind]
        return {
            'status': kind,
            'label': str(result.get('display_name') or item['query'])[:500],
            'provider': 'nominatim',
            'latitude': latitude,
            'longitude': longitude,
            'map_radius_m': radius,
            'queries': queries,
        }

    return {
        'status': 'not_found',
        'label': '',
        'provider': 'nominatim',
        'latitude': None,
        'longitude': None,
        'map_radius_m': None,
        'queries': queries,
    }
