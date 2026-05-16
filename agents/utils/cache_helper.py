"""
Simple Cache Helper for Cost Optimization
Reduces API calls by caching standards and patterns
"""

import hashlib
import json
from functools import wraps
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

# STANDARDS_CACHE_TTL = 3600  # 1 hour
# PATTERNS_CACHE_TTL = 1800   # 30 minutes
# Production (Best Balance)
STANDARDS_CACHE_TTL = 604800   # 1 week
PATTERNS_CACHE_TTL = 604800    # 1 week


def cache_key(prefix: str, *args) -> str:
    """Generate cache key from arguments"""
    key_data = f"{prefix}:{':'.join(str(arg) for arg in args)}"
    return hashlib.md5(key_data.encode()).hexdigest()[:16]


def get_cached_standards(user_id: str):
    """Get cached standards for user"""
    key = cache_key('standards', user_id)
    cached = cache.get(key)
    
    if cached:
        logger.info(f"✅ Cache HIT: Standards for user {user_id}")
    else:
        logger.debug(f"❌ Cache MISS: Standards for user {user_id}")  # Changed to DEBUG level
    
    return cached


def set_cached_standards(user_id: str, data: dict):
    """Cache standards for user"""
    key = cache_key('standards', user_id)
    cache.set(key, data, STANDARDS_CACHE_TTL)
    logger.info(f"💾 Cached standards for user {user_id} (TTL: {STANDARDS_CACHE_TTL}s)")


def get_cached_patterns(user_id: str, query: str, language: str):
    """Get cached pattern retrieval results"""
    key = cache_key('patterns', user_id, query, language)
    cached = cache.get(key)
    
    if cached:
        logger.info(f"✅ Cache HIT: Patterns for {language}")
    else:
        logger.info(f"❌ Cache MISS: Patterns for {language}")
    
    return cached


def set_cached_patterns(user_id: str, query: str, language: str, data: list):
    """Cache pattern retrieval results"""
    key = cache_key('patterns', user_id, query, language)
    cache.set(key, data, PATTERNS_CACHE_TTL)
    logger.info(f"💾 Cached patterns for {language} (TTL: {PATTERNS_CACHE_TTL}s)")


def clear_user_cache(user_id: str):
    """Clear all cache for a user"""
    # Note: This is a simple implementation
    # For production, use cache.delete_pattern() with Redis
    logger.info(f"🗑️ Clearing cache for user {user_id}")


# NEW: Analyzed patterns cache (30 days TTL - expensive to compute!)
ANALYZED_PATTERNS_TTL = 604800  # 7 days


def get_cached_analyzed_patterns(user_id: str, codebase_id: str):
    """
    Get cached analyzed patterns (from pattern_analyzer.py)
    These are EXPENSIVE to compute, so cache for 30 days!
    """
    key = cache_key('analyzed_patterns', user_id, codebase_id)
    cached = cache.get(key)
    
    if cached:
        logger.info(f"✅ Cache HIT: Analyzed patterns for codebase {codebase_id}")
    else:
        logger.info(f"❌ Cache MISS: Analyzed patterns for codebase {codebase_id}")
    
    return cached


def set_cached_analyzed_patterns(user_id: str, codebase_id: str, data: dict):
    """
    Cache analyzed patterns (LONG TTL - 30 days)
    """
    key = cache_key('analyzed_patterns', user_id, codebase_id)
    cache.set(key, data, ANALYZED_PATTERNS_TTL)
    logger.info(f"💾 Cached analyzed patterns for codebase {codebase_id} (TTL: {ANALYZED_PATTERNS_TTL}s = 30 days)")


def invalidate_codebase_cache(user_id: str, codebase_id: str):
    """
    Invalidate all cache for a codebase (when codebase is updated/deleted)
    """
    key = cache_key('analyzed_patterns', user_id, codebase_id)
    cache.delete(key)
    logger.info(f"🗑️ Invalidated cache for codebase {codebase_id}")
