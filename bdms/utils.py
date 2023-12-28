r"""Utilities
^^^^^^^^^^^^^

Miscellaneous utilities needed by the rest of the package.

"""

from __future__ import annotations
from typing import Hashable, Iterable
import numpy as np


class RandomizedSet:
    r"""A set-like data structure that supports random sampling with constant time
    complexity.

    Example:

        >>> import bdms

        Initialize with any iterable of hashable items.

        >>> rs = bdms.utils.RandomizedSet("abc")
        >>> rs
        RandomizedSet('a', 'b', 'c')
        >>> len(rs)
        3

        Add an item.

        >>> rs.add('d')
        >>> rs
        RandomizedSet('a', 'b', 'c', 'd')
        >>> len(rs)
        4

        Choose a random item.

        >>> rs.choice(seed=0)
        'd'

        Remove an item.

        >>> rs.remove('a')
        >>> rs
        RandomizedSet('d', 'b', 'c')

        Iterate over the items.

        >>> for item in rs:
        ...     print(item)
        d
        b
        c

        Reverse iterate over the items.

        >>> for item in reversed(rs):
        ...     print(item)
        c
        b
        d

    Args:
        items: Items to initialize the set with.
    """

    def __init__(self, items: Iterable[Hashable] = ()):
        self._item_to_idx = {}
        self._idx_to_item = {}
        self._size = 0
        for item in items:
            self.add(item)

    def add(self, item: Hashable):
        r"""Add an item to the set.

        Args:
            item: The item to add.
        """
        if item in self._item_to_idx:
            return
        self._item_to_idx[item] = self._size
        self._idx_to_item[self._size] = item
        self._size += 1

    def remove(self, item: Hashable):
        r"""Remove an item from the set.

        Args:
            item: The item to remove.

        Raises:
            KeyError: If the item is not in the set.
        """
        if item not in self._item_to_idx:
            raise KeyError(item)
        # Swap the element with the last element
        last_item, del_idx = (
            self._idx_to_item[self._size - 1],
            self._item_to_idx[item],
        )
        self._item_to_idx[last_item], self._idx_to_item[del_idx] = del_idx, last_item
        # Remove the last element
        del self._item_to_idx[item]
        del self._idx_to_item[self._size - 1]
        self._size -= 1

    def choice(self, seed: int | np.random.Generator | None = None) -> Hashable:
        r"""Randomly sample an item from the set.

        Args:
            seed: A seed to initialize the random number generation.
                  If ``None``, then fresh, unpredictable entropy will be pulled from
                  the OS.
                  If an ``int``, then it will be used to derive the initial state.
                  If a :py:class:`numpy.random.Generator`, then it will be used
                  directly.

        Returns:
            A randomly sampled item from the set.
        """
        rng = np.random.default_rng(seed)
        random_idx = rng.choice(self._size)
        return self._idx_to_item[random_idx]

    def __len__(self) -> int:
        return self._size

    def __iter__(self):
        for idx in range(self._size):
            yield self._idx_to_item[idx]

    def __reversed__(self):
        for idx in reversed(range(self._size)):
            yield self._idx_to_item[idx]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({', '.join(map(repr, self))})"