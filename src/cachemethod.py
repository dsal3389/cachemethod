import time
from threading import Lock
from functools import wraps
from collections import namedtuple
from typing import Callable, TypeVar, Optional


__all__ = ("lru_cachemethod",)

_RT = TypeVar("_RT")

_CACHE_SEED_ATTR = "__cache_seed__"

_CacheInfo = namedtuple("CacheInfo", ("misses", "hits", "maxsize", "full"))
_PREV, _NEXT, _KEY, _RESULT = 0, 1, 2, 3


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
    misses = hits = 0
    used_seeds = set()
    lock = Lock()
    full = False
    cache = {}

    # root is the root of the circular queue, values
    # matching the _PREV, _NEXT, _KEY, _RESULT consts
    root = []
    root[:] = [root, root, None, None]

    @wraps(func)
    def cache_wrapper(__self__, *args, **kwargs) -> _RT:
        nonlocal misses, hits, full, root

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
            node = cache.get(key, _CacheMiss)
            if node is not _CacheMiss:
                prev, next_, key, result = node

                # pop the current node from its position
                prev[_NEXT] = next_
                next_[_PREV] = prev

                # push the node after the
                # last node in the list, making the current node last
                last = root[_PREV]
                last[_NEXT] = root[_PREV] = node
                node[_PREV] = last
                node[_NEXT] = root
                hits += 1
                return result
            misses += 1

        result = func(__self__, *args, **kwargs)

        with lock:
            if key in cache:
                # based on python stdlib code this can happen
                # if the same key was added when the lock was released
                pass
            elif full:
                # use the oldest node which is the root
                # to store the new key and result
                node = root
                node[_KEY] = key
                node[_RESULT] = result

                # mark the next node as current root
                # marking it also the oldest one
                root = node[_NEXT]
                oldkey = root[_KEY]

                # deleting the root, key and result because
                # the root shouldn't containt data except being
                # the head of the queue marking the oldest and the newest items
                root[_KEY] = root[_RESULT] = None
                del cache[oldkey]
            else:
                last = root[_PREV]
                node = [last, root, key, result]
                last[_NEXT] = root[_PREV] = cache[key] = node
                full = len(cache) >= maxsize
        cache[key] = node
        return result

    def cache_info() -> _CacheInfo:
        """returns the cache info"""
        with lock:
            return _CacheInfo(misses=misses, hits=hits, maxsize=maxsize, full=full)

    def cache_clear() -> None:
        """clears the cache"""
        nonlocal misses, hits
        with lock:
            cache.clear()
            misses = 0
            hits = 0

    cache_wrapper.cache_info = cache_info
    cache_wrapper.cache_clear = cache_clear
    return cache_wrapper


def lru_cachemethod(maxsize: Optional[int] = 128) -> Callable[..., Callable[..., _RT]]:
    def _lru_cachemethod_deco(func: Callable[..., _RT]) -> Callable[..., _RT]:
        return _lru_cachemthod_wrapper(func, maxsize=maxsize)

    return _lru_cachemethod_deco
