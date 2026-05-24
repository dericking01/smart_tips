import json
import random
from app.config.logger import logger
from app.generator.generator import generate_tips_batch
from app.queue.redis_client import redis_conn
from app.validation.length import validate_length
from app.validation.safety import validate_safety

POOL_KEY_PREFIX = "smart_tips:generic_pool"
POOL_SIZE = 20
# TTL slightly longer than the gap between the two daily runs so the pool
# is always available when needed but never stale from a previous day.
POOL_TTL_SECONDS = 14 * 60 * 60  # 14 hours


def _validate_tips(tips: list) -> list:
    """Return only tips that pass length and safety checks."""
    valid = []
    for tip in tips:
        length_ok, _ = validate_length(tip)
        safe_ok, _ = validate_safety(tip)
        if length_ok and safe_ok:
            valid.append(tip)
    return valid


def prefetch_generic_tips():
    """Generate and cache a pool of generic health tips in Redis.
    Called once per schedule run — before the main processing job.
    One API call per language covers all no-history subscribers for that run.
    """
    for language in ('sw', 'en'):
        try:
            raw_tips = generate_tips_batch(count=POOL_SIZE, language=language)
            tips = _validate_tips(raw_tips)

            if not tips:
                logger.error(
                    'prefetch_no_valid_tips',
                    extra={
                        'event': 'prefetch_no_valid_tips',
                        'language': language,
                        'raw_count': len(raw_tips)
                    }
                )
                continue

            if len(tips) < POOL_SIZE:
                logger.warning(
                    'prefetch_partial_tips',
                    extra={
                        'event': 'prefetch_partial_tips',
                        'language': language,
                        'valid': len(tips),
                        'requested': POOL_SIZE
                    }
                )

            key = f"{POOL_KEY_PREFIX}:{language}"
            redis_conn.setex(key, POOL_TTL_SECONDS, json.dumps(tips))

            logger.info(
                'generic_tips_prefetched',
                extra={
                    'event': 'generic_tips_prefetched',
                    'language': language,
                    'count': len(tips)
                }
            )

        except Exception as exc:
            logger.exception(
                'prefetch_failed',
                extra={
                    'event': 'prefetch_failed',
                    'language': language,
                    'error': str(exc)
                }
            )


def get_tip_from_pool(language: str = 'sw') -> str | None:
    """Return a random tip from the pre-generated Redis pool.
    Falls back to the other language pool if the requested one is missing.
    Returns None only when both pools are empty (e.g. prefetch has not run yet).
    """
    for lang in (language, 'sw' if language != 'sw' else 'en'):
        key = f"{POOL_KEY_PREFIX}:{lang}"
        raw = redis_conn.get(key)
        if raw:
            try:
                tips = json.loads(raw)
                if tips:
                    return random.choice(tips)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    'pool_decode_error',
                    extra={'event': 'pool_decode_error', 'language': lang}
                )
    return None
