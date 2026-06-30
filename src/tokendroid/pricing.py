"""Pricing module using models.dev API for cost estimation."""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from pathlib import Path

from .models import ModelPrice

logger = logging.getLogger(__name__)

PRICING_DIR = Path.home() / ".local" / "share" / "tokendroid"
PRICING_CACHE = PRICING_DIR / "pricing.json"
TTL_SECONDS = 86_400

_MODELS_DEV_URL = "https://models.dev/api.json"

_OVERRIDE_MAP: dict[str, str] = {}


def _is_zero_price(price: ModelPrice) -> bool:
    """Return True if every per-1M rate on the price is zero."""
    return (
        price.input_per_1m == 0
        and price.output_per_1m == 0
        and price.cache_read_per_1m == 0
        and price.reasoning_per_1m == 0
    )

_CUSTOM_PREFIX_RE = re.compile(r"^custom:", re.IGNORECASE)
_BRACKET_RE = re.compile(r"[\[\(].*?[\]\)]", re.IGNORECASE)
_CUSTOM_SUFFIX_NUM_RE = re.compile(r"[-_]\d+$")
_SEP_RE = re.compile(r"[\s\-_.]+")


def _strip_factory_noise(name: str) -> str:
    """Remove Factory-specific artifacts from a model name.

    Handles patterns like:
      - 'custom:' prefix from BYOK models
      - '[Neuralwatt]', '[Z.AI]', '(Fast)' brackets
      - trailing numeric suffixes on custom: model IDs only
    """
    is_custom = name.lower().startswith("custom:")
    s = _CUSTOM_PREFIX_RE.sub("", name)
    s = _BRACKET_RE.sub("", s)
    if is_custom:
        s = _CUSTOM_SUFFIX_NUM_RE.sub("", s)
    return s.strip()


def _normalize(name: str) -> str:
    """Normalize a model name for fuzzy matching."""
    s = name.lower().strip()
    s = _BRACKET_RE.sub("", s)
    s = _SEP_RE.sub("-", s)
    s = s.strip("-")
    return s


def _extract_keywords(name: str) -> list[str]:
    """Extract meaningful keywords from a model display name.

    Strips Factory-specific noise (custom: prefix, bracket labels, numeric
    suffixes) and returns the individual tokens that identify the model.
    """
    cleaned = _strip_factory_noise(name)
    parts = _SEP_RE.split(cleaned.lower())
    return [p for p in parts if p]


def _fuzzy_score(keywords: list[str], candidate: str) -> float:
    """Score how well keywords match a candidate model name or ID.

    Returns a value between 0 and 1. Each matched keyword contributes
    proportionally. Full normalized match gets a bonus.
    """
    if not keywords:
        return 0.0
    norm_cand = _normalize(candidate)
    score = 0.0
    for kw in keywords:
        if kw in norm_cand:
            score += 1.0
    bonus = 0.0
    joined = "-".join(keywords)
    if joined == norm_cand:
        bonus = 0.5
    elif joined in norm_cand:
        bonus = 0.3
    return (score / len(keywords)) + bonus


def _fetch_api() -> dict:
    """Fetch pricing data from models.dev API."""
    import urllib.request

    import orjson

    req = urllib.request.Request(_MODELS_DEV_URL, headers={"User-Agent": "tokendroid/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return orjson.loads(resp.read())


def _load_cache() -> dict | None:
    """Load cached pricing data if fresh enough."""
    import orjson

    if not PRICING_CACHE.exists():
        return None
    try:
        with open(PRICING_CACHE, "rb") as f:
            cached = orjson.loads(f.read())
        if time.time() - cached.get("_fetched_at", 0) < TTL_SECONDS:
            return cached
    except Exception:
        logger.exception("Failed to load pricing cache")
    return None


def _save_cache(data: dict) -> None:
    """Persist pricing data to disk."""
    import orjson

    PRICING_DIR.mkdir(parents=True, exist_ok=True)
    data["_fetched_at"] = time.time()
    with open(PRICING_CACHE, "wb") as f:
        f.write(orjson.dumps(data))


def _get_pricing_data() -> dict:
    """Get pricing data, using cache when available."""
    cached = _load_cache()
    if cached is not None:
        return cached
    try:
        data = _fetch_api()
    except Exception:
        logger.exception("Failed to fetch pricing from models.dev")
        if PRICING_CACHE.exists():
            import orjson

            with open(PRICING_CACHE, "rb") as f:
                return orjson.loads(f.read())
        return {}
    try:
        _save_cache(data)
    except Exception:
        logger.exception("Failed to save pricing cache")
    return data


def _median_field(values: list[float]) -> float:
    """Compute the median of a list, ignoring zeros."""
    from statistics import median

    nonzero = [v for v in values if v > 0]
    return median(nonzero) if nonzero else 0.0


def _merge_prices(prices: list[ModelPrice]) -> ModelPrice:
    """Merge multiple ModelPrice entries by taking the median per field."""
    if len(prices) == 1:
        return prices[0]
    return ModelPrice(
        model_id=prices[0].model_id,
        input_per_1m=_median_field([p.input_per_1m for p in prices]),
        output_per_1m=_median_field([p.output_per_1m for p in prices]),
        cache_read_per_1m=_median_field([p.cache_read_per_1m for p in prices]),
        cache_write_per_1m=_median_field([p.cache_write_per_1m for p in prices]),
        reasoning_per_1m=_median_field([p.reasoning_per_1m for p in prices]),
    )


def _build_price_index(data: dict) -> dict[str, ModelPrice]:
    """Build a model_id -> ModelPrice index from models.dev data.

    When multiple providers offer the same model, the median price per
    field is used so that outliers don't skew the estimate.
    """
    buckets: dict[str, list[ModelPrice]] = {}
    for _provider_id, provider in data.items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models", {})
        if not isinstance(models, dict):
            continue
        for model_id, model in models.items():
            if not isinstance(model, dict):
                continue
            cost = model.get("cost", {})
            if not isinstance(cost, dict):
                continue
            name = model.get("name", model_id)
            price = ModelPrice(
                model_id=model_id,
                input_per_1m=cost.get("input", 0),
                output_per_1m=cost.get("output", 0),
                cache_read_per_1m=cost.get("cache_read", 0),
                cache_write_per_1m=cost.get("cache_write", 0),
                reasoning_per_1m=cost.get("reasoning", 0),
            )
            buckets.setdefault(model_id, []).append(price)
            norm_name = _normalize(name)
            if norm_name:
                buckets.setdefault(norm_name, []).append(price)
    index: dict[str, ModelPrice] = {}
    for key, prices in buckets.items():
        index[key] = _merge_prices(prices)
    return index


@lru_cache(maxsize=1)
def get_price_index() -> dict[str, ModelPrice]:
    """Get the full model_id -> ModelPrice index."""
    return _build_price_index(_get_pricing_data())


def refresh_pricing() -> bool:
    """Force refresh pricing data from models.dev. Returns True on success."""
    try:
        data = _fetch_api()
        _save_cache(data)
        get_price_index.cache_clear()
        return True
    except Exception:
        logger.exception("Failed to refresh pricing")
        return False


def _containment_match(
    index: dict[str, ModelPrice], norm_disp: str, norm_id: str
) -> ModelPrice | None:
    """Find the most specific substring-containment match.

    Two directions are considered, and the candidate explaining the largest
    portion of the display name/id wins:
      * Direction A: an index key contains the normalized display/id.
        Prefer the shortest such key (least extra noise).
      * Direction B: the normalized display/id contains an index key.
        Prefer the longest such key (most specific version, e.g.
        "kimi-k2-6" beats "kimi-k2"). Requires keys of length >= 6 to
        avoid spurious short matches.
    """
    best_price: ModelPrice | None = None
    best_score = 0.0

    for norm_target in (norm_disp, norm_id):
        if not norm_target:
            continue
        target_len = len(norm_target)
        for key, price in index.items():
            if _is_zero_price(price):
                continue
            # Direction A: key wraps the full target. Score = coverage of
            # the target; break ties by shorter (less noisy) key.
            if norm_target in key:
                score = target_len - (len(key) - target_len) / 100.0
            # Direction B: target wraps the key. Only keys long enough to be
            # meaningful count. Score = how much of the target is explained;
            # longer keys win.
            elif len(key) >= 6 and key in norm_target:
                score = len(key)
            else:
                continue
            if score > best_score:
                best_score = score
                best_price = price

    return best_price


def match_model_price(model_display: str, model_id: str = "") -> ModelPrice | None:
    """Find the pricing for a model given its display name and raw ID.

    Matching strategy in order:
      1. Exact match on model_id (non-zero price)
      2. Override map lookup (non-zero price)
      3. Exact match on model_display (non-zero price)
      4. Exact normalized match on display or id (non-zero price)
      5. Substring containment match on normalized index keys (non-zero
         price), picking the most specific candidate instead of the first
         one found.
      6. Fuzzy keyword scoring across all index entries (non-zero price)

    Zero-price entries (e.g. provider routers with no cost data) are skipped
    so that a meaningful price from another provider can be used instead.

    Returns None if no confident non-zero match is found, meaning the model
    is not in the models.dev database and its cost is unknown.
    """
    index = get_price_index()

    if model_id and model_id in index and not _is_zero_price(index[model_id]):
        return index[model_id]

    override = _OVERRIDE_MAP.get(model_display) or _OVERRIDE_MAP.get(model_id)
    if override and override in index and not _is_zero_price(index[override]):
        return index[override]

    if model_display in index and not _is_zero_price(index[model_display]):
        return index[model_display]

    norm_disp = _normalize(model_display)
    if norm_disp in index and not _is_zero_price(index[norm_disp]):
        return index[norm_disp]

    norm_id = _normalize(model_id) if model_id else ""
    if norm_id and norm_id in index and not _is_zero_price(index[norm_id]):
        return index[norm_id]

    containment = _containment_match(index, norm_disp, norm_id)
    if containment is not None:
        return containment

    keywords = _extract_keywords(model_display)
    if not keywords:
        keywords = _extract_keywords(model_id)
    if not keywords:
        return None

    best_score = 0.0
    best_price: ModelPrice | None = None
    for key, price in index.items():
        if _is_zero_price(price):
            continue
        score = _fuzzy_score(keywords, key)
        if score > best_score:
            best_score = score
            best_price = price

    if best_score >= 0.6:
        return best_price

    return None


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int = 0,
    thinking_tokens: int = 0,
    price: ModelPrice | None = None,
) -> dict[str, float]:
    """Compute cost in USD for given token counts and price.

    Cache tokens use cache_read price. Thinking tokens use reasoning price
    falling back to output price.
    """
    if price is None:
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_cost": 0.0,
            "reasoning_cost": 0.0,
            "total_cost": 0.0,
            "cache_savings": 0.0,
        }

    m = 1_000_000
    ic = input_tokens / m * price.input_per_1m
    oc = output_tokens / m * price.output_per_1m
    cc = cache_tokens / m * price.cache_read_per_1m
    rc = thinking_tokens / m * (price.reasoning_per_1m or price.output_per_1m)
    input_rate = price.input_per_1m / m
    cache_rate = price.cache_read_per_1m / m if price.cache_read_per_1m else 0.0
    savings = max(cache_tokens * (input_rate - cache_rate), 0.0) if cache_tokens > 0 else 0.0
    return {
        "input_cost": ic,
        "output_cost": oc,
        "cache_cost": cc,
        "reasoning_cost": rc,
        "total_cost": ic + oc + cc + rc,
        "cache_savings": savings,
    }


def fmt_cost(value: float) -> str:
    """Format a cost value for display."""
    if value == 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.4f}"
    if value < 1:
        return f"${value:.3f}"
    return f"${value:.2f}"
