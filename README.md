# cachemethod
python's missing cache functionality, you can cache a regular function
you can cache `staticmethod` and `classmethod` but you can't really cache a method that takes `self`.

```console
pip3 install cachemethod
```

## why can't I use cache on a method that takes self?
python `cache` doesn't actually stores the hash of the *args and *kwargs (including `self`), but it
puts it into a tuple (which is hashable) and that tuple is used as a key in the cache `dict`, thus
storing the reference to `self` in that tuple causes the instance to be a live until the cache is cleared
or it runs of our space (if you use `lru_cache`)

## why not just hash the items then?
the default `hash` implementation for classes uses the allocated memory for instances,
so if an instance memory gets freed, the `cache` is not really valid anymore but it is still
in the `cache` dict, so instance that was created on the same memory and passed the same arguments
can hit the cache and cause unexpected results

## how this package solves the issue
it creates a `seed` which is a random integer and attaches it to the instance, based on that `seed` caching is done
not relying on the class `hash` and not storing references

