import time
import weakref
from threading import Lock
from functools import wraps
from collections import namedtuple
from typing import Callable, TypeVar


__all__ = ("lru_cachemethod",)

_RT = TypeVar("_RT")

_CACHE_SEED_ATTR = "__cache_seed__"

_CacheInfo = namedtuple("CacheInfo", ("misses", "hits", "maxsize", "full"))
_PREV, _NEXT, _KEY, _RESULT = 0, 1, 2, 3
_LRU_DEFAULT_MAXSIZE = 128


def _hash_args_kwargs(args, kwargs) -> int:
    return hash(args) + sum(map(hash, kwargs.items()))


def _make_cache_key_seed(seed, args, kwargs) -> int:
    """generates a cache key based on given seed, args and kwargs"""
    return seed + _hash_args_kwargs(args, kwargs)


def _make_cache_key_weakref(__weak_self__, args, kwargs):
    """
    stored `self` weakref in the tuple key, making the weakref instance never die
    but the pointed instance is free to die
    """
    return (__weak_self__, _hash_args_kwargs(args, kwargs))


def _make_seed(used_seeds: set[int]) -> int:
    """generate seed that cannot be found in the given `used_seeds` set"""
    while (seed := round(time.time() * 1000)) in used_seeds:
        continue
    return seed


def _marshall_seed(__self__, cache_lock: Lock, used_seeds_set: set):
    with cache_lock:
        # get the seed from the instance, if no
        # seed found, generate and set it
        if not hasattr(__self__, _CACHE_SEED_ATTR):
            seed = _make_seed(used_seeds_set)
            used_seeds_set.add(seed)
            setattr(__self__, _CACHE_SEED_ATTR, seed)
            return seed
        else:
            return getattr(__self__, _CACHE_SEED_ATTR)


def _marshall_weakref(__self__, cache_lock: Lock):
    return weakref.ref(__self__)


def _base_seed():
    used_seeds_set = set()
    return (
        lambda *args, **kwargs: _marshall_seed(
            *args, **kwargs, used_seeds_set=used_seeds_set
        ),
        _make_cache_key_seed,
    )


def _base_weakref():
    return (_marshall_weakref, _make_cache_key_weakref)


def _lru_cachemthod_wrapper(
    func: Callable[..., _RT],
    maxsize: int,
    base: Callable[[], tuple[Callable, Callable]],
) -> Callable[..., _RT]:
    misses = hits = 0
    lock = Lock()
    full = False
    cache = {}

    # base function should return 2 functions, first is "marshall" function (i don't have a better name)
    # which takes `self` and the lock, and should return a marshalled self that we can
    # pass to `make_key` which is the 2 function returned by `base` that should
    # return to us a valid hash key
    marshall_self, make_key = base()

    # root is the root of the circular queue, values
    # matching the _PREV, _NEXT, _KEY, _RESULT consts
    root = []
    root[:] = [root, root, None, None]

    @wraps(func)
    def cache_wrapper(__self__, *args, **kwargs) -> _RT:
        nonlocal misses, hits, full, root

        marshalled_self = marshall_self(__self__, lock)
        key = make_key(marshalled_self, args, kwargs)

        with lock:
            node = cache.get(key)
            if node is not None:
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


def lru_cachemethod(maxsize: int = _LRU_DEFAULT_MAXSIZE):
    def _lru_cachemethod_deco(func: Callable[..., _RT]) -> Callable[..., _RT]:
        return _lru_cachemthod_wrapper(func, maxsize=maxsize, base=_base_seed)

    return _lru_cachemethod_deco


def weakref_lru_cachemethod(maxsize: int = _LRU_DEFAULT_MAXSIZE):
    def _lru_cachemethod_deco(func: Callable[..., _RT]) -> Callable[..., _RT]:
        return _lru_cachemthod_wrapper(func, maxsize=maxsize, base=_base_weakref)

    return _lru_cachemethod_deco
