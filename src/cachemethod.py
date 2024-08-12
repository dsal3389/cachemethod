from sys import maxsize
import time
from threading import Lock
from functools import wraps
from collections import namedtuple
from typing import Callable, TypeVar, Optional


_RT = TypeVar("_RT")

_CACHE_SEED_ATTR = "__cache_seed__"

_CacheInfo = namedtuple("CacheInfo", ("misses", "hits"))


class _CacheMiss:
    pass


def _make_cache_key(seed, args, kwargs):
    """generates a cache key based on given seed, args and kwargs"""
    cache_key = seed
    cache_key += hash(args)

    for item in kwargs.items():
        cache_key += hash(item)
    return cache_key


def _make_seed(used_seeds: set[int]) -> int:
    """generate seed that cannot be found in the given `used_seeds` set"""
    while (seed := round(time.time() * 1000)) in used_seeds:
        continue
    return seed


def _lru_cachemthod_wrapper(
    func: Callable[..., _RT], maxsize: int
) -> Callable[..., _RT]:
    used_seeds = set()
    lock = Lock()
    cache = {}

    misses = hits = 0

    @wraps(func)
    def cache_wrapper(__self__, *args, **kwargs) -> _RT:
        nonlocal misses, hits

        # get the seed from the instance, if no
        # seed found, generate and set it
        if not hasattr(__self__, _CACHE_SEED_ATTR):
            with lock:
                seed = _make_seed(used_seeds)
                used_seeds.add(seed)
            setattr(__self__, _CACHE_SEED_ATTR, seed)
        else:
            seed = getattr(__self__, _CACHE_SEED_ATTR)

        key = _make_cache_key(seed, args, kwargs)

        with lock:
            results = cache.get(key, _CacheMiss)
            if results is not _CacheMiss:
                hits += 1
                return results
            misses += 1

        results = func(__self__, *args, **kwargs)
        cache[key] = results
        return results

    def cache_info() -> _CacheInfo:
        """returns the cache info"""
        with lock:
            return _CacheInfo(misses=misses, hits=hits)

    def cache_clear() -> None:
        """clears the cache"""
        nonlocal misses, hits
        with lock:
            cache.clear()
            misses = 0
            hits = 0

    def cache_clear_instance(__self__) -> None:
        seed = getattr(__self__, _CACHE_SEED_ATTR, None)
        if seed is None:
            return

    cache_wrapper.cache_clear = cache_clear
    cache_wrapper.cache_info = cache_info
    return cache_wrapper


def lru_cachemethod(maxsize: Optional[int] = 128) -> Callable[..., Callable[..., _RT]]:
    def _lru_cachemethod_deco(func: Callable[..., _RT]) -> Callable[..., _RT]:
        return _lru_cachemthod_wrapper(func, maxsize=maxsize)

    return _lru_cachemethod_deco


def cachemethod(func: Callable[..., _RT]) -> Callable[..., _RT]:
    """returns `lru_cachemethod` with no limit"""
    return lru_cachemethod(maxsize=None)(func)
