r"""Birth-death-mutation-sampling (BDMS) process simulation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

from __future__ import annotations
import ete3
from ete3.coretype.tree import TreeError
from bdms import mutators, poisson
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from typing import Any, Optional, Union, Literal, Iterator, Self
import itertools
import copy


class TreeNode(ete3.Tree):
    r"""A tree generated by a BDMS process. Subclasses :py:class:`ete3.TreeNode`.

    Args:
        t: Time of this node.
        kwargs: Keyword arguments passed to :py:class:`ete3.TreeNode` initializer.
    """

    _BIRTH_EVENT = "birth"
    _DEATH_EVENT = "death"
    _MUTATION_EVENT = "mutation"
    _SURVIVAL_EVENT = "survival"
    _SAMPLING_EVENT = "sampling"

    _OFFSPRING_NUMBER = 2

    _name_generator = itertools.count()

    _time_face = ete3.AttrFace(
        "dist", fsize=6, ftype="Arial", fgcolor="black", formatter="%0.3g"
    )
    _mutation_face = ete3.AttrFace(
        "n_mutations", fsize=6, ftype="Arial", fgcolor="green"
    )

    def __init__(
        self,
        t: float = 0,
        **kwargs: Any,
    ) -> None:
        if "dist" not in kwargs:
            kwargs["dist"] = 0
        if "name" not in kwargs:
            TreeNode._name_generator = itertools.count()
            kwargs["name"] = next(self._name_generator)
        super().__init__(**kwargs)
        self.t = t
        """Time of the node."""
        self.event = None
        """Event at this node."""
        self.n_mutations = 0
        """Number of mutations on the branch above this node (zero unless the tree has
        been pruned above this node, removing mutation event nodes)."""
        self._sampled = False
        """Whether sampling has been run on this tree.

        (Not whether the node has been sampled as part of this sampling process).
        """
        self._pruned = False

    def _birth_outcome(
        self, birth_mutations: bool, mutator: mutators.Mutator, rng: np.random.Generator
    ) -> Iterator[Self]:
        r"""Generate the outcome of a birth event at this node.

        Args:
            birth_mutations: Flag to indicate whether mutations should occur at birth.
            mutator: Generator of mutation effects if ``birth_mutations=True``.
            rng: Random number generator.

        Yields:
            The child nodes, or mutated grandchild nodes if ``birth_mutations=True``.
        """
        assert self.event == self._BIRTH_EVENT
        for _ in range(self._OFFSPRING_NUMBER):
            child = TreeNode(
                t=self.t,
                dist=0,
                name=next(self._name_generator),
            )
            for attr in mutator.mutated_attrs:
                setattr(child, attr, copy.copy(getattr(self, attr)))
            if birth_mutations:
                child.event = self._MUTATION_EVENT
                mutator.mutate(child, seed=rng)
                grandchild = TreeNode(
                    t=child.t,
                    dist=0,
                    name=next(self._name_generator),
                )
                for attr in mutator.mutated_attrs:
                    setattr(grandchild, attr, copy.copy(getattr(child, attr)))
                child.add_child(grandchild)
                yield grandchild
            else:
                yield child
            self.add_child(child)

    def _mutation_outcome(
        self, mutator: mutators.Mutator, rng: np.random.Generator
    ) -> Iterator[Self]:
        r"""Generate the outcome of a mutation event at this node.

        Args:
            mutator: Generator of mutation effects.
            rng: Random number generator.

        Yields:
            The mutated child node.
        """
        assert self.event == self._MUTATION_EVENT
        mutator.mutate(self, seed=rng)
        child = TreeNode(
            t=self.t,
            dist=0,
            name=next(self._name_generator),
        )
        for attr in mutator.mutated_attrs:
            setattr(child, attr, copy.copy(getattr(self, attr)))
        self.add_child(child)
        yield child

    def evolve(
        self,
        t: float,
        birth_response: poisson.Response = poisson.ConstantResponse(1),
        death_response: poisson.Response = poisson.ConstantResponse(0),
        mutation_response: poisson.Response = poisson.ConstantResponse(1),
        mutator: mutators.Mutator = mutators.GaussianMutator(shift=0, scale=1),
        birth_mutations: bool = False,
        min_survivors: int = 1,
        capacity: int = 1000,
        capacity_method: Optional[Literal["birth", "death", "hard"]] = None,
        init_population: int = 1,
        seed: Optional[Union[int, np.random.Generator]] = None,
        verbose: bool = False,
    ) -> None:
        r"""Evolve for time :math:`\Delta t`.

        Args:
            t: Evolve for a duration of :math:`t` time units.
            birth_response: Birth rate response function.
            death_response: Death rate response function.
            mutation_response: Mutation rate response function.
            mutator: Generator of mutation effects at mutation events
                     (and on offspring of birth events if ``birth_mutations=True``).
            birth_mutations: Flag to indicate whether mutations should occur at birth.
            min_survivors: Minimum number of survivors. If the simulation finishes with
                           fewer than this number of survivors, then a
                           :py:class:`TreeError` is raised.
            capacity: Population carrying capacity.
            capacity_method: Method to enforce population carrying capacity. If
                             ``None``, then a :py:class:`TreeError` is raised if
                             the population exceeds the carrying capacity.
                             If ``"birth"``, then the birth rate is logistically
                             modulated such that the process is critical when the
                             population is at carrying capacity.
                             If ``"death"``, then the death rate is logistically
                             modulated such that the process is critical when the
                             population is at carrying capacity.
                             If ``"hard"``, then a random individual is chosen to
                             die whenever a birth event results in carrying capacity
                             being exceeded.
            init_population: Initial population size.
            seed: A seed to initialize the random number generation.
                  If ``None``, then fresh, unpredictable entropy will be pulled from
                  the OS.
                  If an ``int``, then it will be used to derive the initial state.
                  If a :py:class:`numpy.random.Generator`, then it will be used
                  directly.
            verbose: Flag to indicate whether to print progress information.
        """
        if not self.is_root():
            raise TreeError("Cannot evolve a non-root node")
        if self.children:
            raise TreeError(
                "tree has already evolved at node "
                f"{self.name} with {len(self.children)} descendant lineages"
            )
        if init_population > capacity:
            raise ValueError(f"{init_population=} must be less than {capacity=}")
        for attr in mutator.mutated_attrs:
            if not hasattr(self, attr):
                raise ValueError(
                    f"node {self.name} does not have attribute {attr} "
                    "specified in mutator"
                )

        rng = np.random.default_rng(seed)

        if verbose:

            def print_progress(current_time, n_active_nodes):
                print(f"t={current_time:.3f}, n={n_active_nodes}", end="   \r")

        else:

            def print_progress(current_time, n_active_nodes):
                pass

        current_time = self.t
        end_time = self.t + t
        event_rates = {
            self._BIRTH_EVENT: birth_response,
            self._DEATH_EVENT: death_response,
            self._MUTATION_EVENT: mutation_response,
        }

        # initialize population
        active_nodes = {}
        n_active_nodes = 0
        total_birth_rate = 0.0
        total_death_rate = 0.0
        for _ in range(init_population):
            start_node = TreeNode(
                t=self.t,
                dist=0,
                name=next(self._name_generator),
            )
            for attr in mutator.mutated_attrs:
                setattr(start_node, attr, copy.copy(getattr(self, attr)))
            self.add_child(start_node)
            active_nodes[start_node.name] = start_node
            n_active_nodes += 1
            total_birth_rate += birth_response(start_node)
            total_death_rate += death_response(start_node)

        # initialize rate multipliers, which are used to modulate
        # rates in accordance with the carrying capacity
        rate_multipliers = {
            self._BIRTH_EVENT: 1.0,
            self._DEATH_EVENT: 1.0,
            self._MUTATION_EVENT: 1.0,
        }
        while n_active_nodes:
            if capacity_method == "birth":
                rate_multipliers[self._BIRTH_EVENT] = (
                    total_death_rate / total_birth_rate
                ) ** (n_active_nodes / capacity)
            elif capacity_method == "death":
                rate_multipliers[self._DEATH_EVENT] = (
                    total_birth_rate / total_death_rate
                ) ** (n_active_nodes / capacity)
            elif capacity_method == "hard":
                if n_active_nodes > capacity:
                    node_to_die = rng.choice(list(active_nodes.values()))
                    node_to_die.event = self._DEATH_EVENT
                    del active_nodes[node_to_die.name]
                    n_active_nodes -= 1
                    total_birth_rate -= birth_response(node_to_die)
                    total_death_rate -= death_response(node_to_die)
            elif capacity_method is None:
                if n_active_nodes > capacity:
                    self._aborted_evolve_cleanup()
                    if verbose:
                        print()
                    raise TreeError(f"{capacity=} exceeded at time={current_time}")
            else:
                raise ValueError(f"{capacity_method=} not recognized")
            waiting_time, event = min(
                (
                    event_rates[event].waiting_time_rv(
                        active_nodes.values(),
                        rate_multiplier=rate_multipliers[event],
                        seed=rng,
                    ),
                    event,
                )
                for event in event_rates
            )
            p = np.asarray(event_rates[event].λ(active_nodes.values(), waiting_time))
            p /= sum(p)
            event_node_name = rng.choice(list(active_nodes.keys()), p=p)
            Δt = min(waiting_time, end_time - current_time)
            current_time += Δt
            assert current_time <= end_time
            for node in active_nodes.values():
                node.dist += Δt
                node.t = current_time
                # https://numpy.org/doc/stable/reference/generated/numpy.isclose.html
                assert np.abs(node.dist - (node.t - node.up.t)) <= (
                    1e-8 + 1e-5 * np.abs(node.t - node.up.t)
                )
            if current_time < end_time:
                event_node = active_nodes[event_node_name]
                event_node.event = event
                del active_nodes[event_node.name]
                n_active_nodes -= 1
                total_birth_rate -= birth_response(event_node)
                total_death_rate -= death_response(event_node)
                if event_node.event == self._DEATH_EVENT:
                    new_nodes = ()
                elif event_node.event == self._BIRTH_EVENT:
                    new_nodes = event_node._birth_outcome(birth_mutations, mutator, rng)
                elif event_node.event == self._MUTATION_EVENT:
                    new_nodes = event_node._mutation_outcome(mutator, rng)
                else:
                    raise ValueError(f"invalid event {event_node.event}")
                for new_node in new_nodes:
                    active_nodes[new_node.name] = new_node
                    n_active_nodes += 1
                    total_birth_rate += birth_response(new_node)
                    total_death_rate += death_response(new_node)
                print_progress(current_time, n_active_nodes)
            else:
                print_progress(current_time, n_active_nodes)
                for node in active_nodes.values():
                    node.event = self._SURVIVAL_EVENT
                    n_active_nodes -= 1
                    assert node.t == end_time
                assert n_active_nodes == 0
                active_nodes.clear()
        if verbose:
            print()
        n_survivors = sum(leaf.event == self._SURVIVAL_EVENT for leaf in self)
        if n_survivors < min_survivors:
            self._aborted_evolve_cleanup()
            raise TreeError(
                f"number of survivors {n_survivors} is less than {min_survivors=}"
            )

    def _aborted_evolve_cleanup(self) -> None:
        """Remove any children added to the root node during an aborted evolution
        attempt, and reset the node name generator."""
        for child in self.children.copy():
            child.detach()
            del child
        TreeNode._name_generator = itertools.count(start=self.name + 1)

    def sample_survivors(
        self,
        n: Optional[int] = None,
        p: Optional[float] = 1.0,
        seed: Optional[Union[int, np.random.Generator]] = None,
    ) -> None:
        """Choose :math:`n` survivor leaves from the tree, or each survivor leaf with
        probability :math:`p`, to mark as sampled (via the event attribute).

        Args:
            n: Number of leaves to sample.
            p: Probability of sampling a leaf.
            seed: A seed to initialize the random number generation. If ``None``, then
                  fresh, unpredictable entropy will be pulled from the OS. If an
                  ``int``, then it will be used to derive the initial state. If a
                  :py:class:`numpy.random.Generator`, then it will be used directly.
        """
        if self._sampled:
            raise ValueError(f"tree has already been sampled below node {self.name}")
        rng = np.random.default_rng(seed)
        surviving_leaves = [leaf for leaf in self if leaf.event == self._SURVIVAL_EVENT]
        if n is not None:
            for leaf in rng.choice(surviving_leaves, size=n, replace=False):
                leaf.event = self._SAMPLING_EVENT
        elif p is not None:
            for leaf in surviving_leaves:
                if rng.choice(range(2), p=(1 - p, p)):
                    leaf.event = self._SAMPLING_EVENT
        else:
            raise ValueError("must specify either n or p")
        for node in self.traverse():
            node._sampled = True

    # NOTE: this could be generalized to take an ordered array-valued t,
    #       and made efficient via ordered traversal
    def slice(self, t: float, attr: str = "x") -> list[Any]:
        r"""Return a list of attribute ``attr`` at time :math:`t` for all lineages alive
        at that time.

        Args:
            t: Slice the tree at time :math:`t`.
            attr: Attribute to extract from slice.
        """
        if self._pruned:
            raise ValueError("Cannot slice a pruned tree")
        if not self.children:
            raise ValueError("Cannot slice an unevolved tree")
        if t < self.t:
            raise ValueError(f"Cannot slice at time {t} before root time {self.t}")
        tree_end_time = max(node.t for node in self)
        if t > tree_end_time:
            raise ValueError(
                f"cannot slice at time {t} after tree end time {tree_end_time}"
            )

        if self.t == t:
            return [getattr(self, attr)]

        def is_leaf_fn(node):
            return node.t >= t and node.up.t < t

        return [
            (getattr(node, attr) if node.t == t else getattr(node.up, attr))
            for node in self.iter_leaves(is_leaf_fn=is_leaf_fn)
        ]

    def prune(self) -> None:
        r"""Prune the tree to the subtree subtending the sampled leaves, removing
        unobserved subtrees."""
        if self._pruned:
            raise ValueError(f"tree has already been pruned below node {self.name}")
        if not self._sampled:
            raise ValueError(f"tree has not been sampled below node {self.name}")

        event_cache = self.get_cached_content(store_attr="event")
        if self._SAMPLING_EVENT not in event_cache[self]:
            raise TreeError("cannot prune because no leaves were sampled")

        def is_leaf_fn(node):
            return self._SAMPLING_EVENT not in event_cache[node]

        for node in self.iter_leaves(is_leaf_fn=is_leaf_fn):
            parent = node.up
            parent.remove_child(node)
            assert parent.event == self._BIRTH_EVENT or parent.is_root()
            parent.delete(prevent_nondicotomic=False, preserve_branch_length=True)
        for node in self.traverse():
            node._pruned = True

    def remove_mutation_events(self) -> None:
        r"""Remove unifurcating mutation event nodes, preserving branch length, and
        annotate mutation counts in child node ``n_mutations`` attribute.

        The tree must have been pruned first with :py:meth:`prune`.
        """
        if not self._pruned:
            raise ValueError(f"tree has not been pruned below node {self.name}")
        for node in self.traverse(strategy="postorder"):
            if node.event == self._MUTATION_EVENT:
                assert len(node.children) == 1
                node.children[0].n_mutations += 1
                node.delete(prevent_nondicotomic=False, preserve_branch_length=True)

    def render(
        self, color_by=None, *args: Any, cbar_file: Optional[str] = None, **kwargs: Any
    ) -> Any:
        r"""A thin wrapper around :py:func:`ete3.TreeNode.render` that adds some custom
        decoration and a color bar. As with the base class method, pass ``"%%inline"``
        for the first argument to render inline in a notebook. See also ETE's tree
        rendering `tutorial`_ and linked API docs pages there.

        .. _tutorial: http://etetoolkit.org/docs/latest/tutorial/tutorial_drawing.html

        If tree is not pruned (or is pruned without removing mutation events), then
        branches are colored according to the attribute specified by ``color_by``,
        extinct lineages are indicated as dotted branches, unsampled non-extint
        lineages are indicated as solid branches, and sampled lineages are indicated
        as thick solid branches. Sampled leaves are indicated with a circle.

        If tree is pruned without retaining mutation events, then nodes are colored
        according to the attribute specified by ``color_by``, branches are annotated
        above with branch length (in black text) and below with number of mutations
        (in green text).

        Args:
            color_by: If not ``None``, color tree by this attribute (must be a scalar).
            args: Arguments to pass to :py:func:`ete3.TreeNode.render`.
            cbar_file: If not ``None``, save color bar to this file.
            kwargs: Keyword arguments to pass to :py:func:`ete3.TreeNode.render`.
        """
        if "tree_style" not in kwargs:
            kwargs["tree_style"] = ete3.TreeStyle()
            kwargs["tree_style"].show_leaf_name = False
            kwargs["tree_style"].show_scale = False
        cmap = "coolwarm_r"
        cmap = mpl.cm.get_cmap(cmap)
        halfrange = max(
            abs(getattr(node, color_by) - getattr(self, color_by))
            for node in self.traverse()
        )
        norm = mpl.colors.CenteredNorm(
            vcenter=getattr(self, color_by),
            halfrange=halfrange if halfrange > 0 else 1,
        )
        colormap = {
            node.name: mpl.colors.to_hex(cmap(norm(getattr(node, color_by))))
            for node in self.traverse()
        }
        event_cache = self.get_cached_content(store_attr="event", leaves_only=False)
        if (not self._pruned) or (self._MUTATION_EVENT in event_cache[self]):
            for node in self.traverse():
                nstyle = ete3.NodeStyle()
                if (
                    self._SURVIVAL_EVENT not in event_cache[node]
                    and self._SAMPLING_EVENT not in event_cache[node]
                ):
                    nstyle["hz_line_type"] = 1
                    nstyle["vt_line_type"] = 1
                    nstyle["hz_line_width"] = 0
                elif self._SAMPLING_EVENT not in event_cache[node]:
                    nstyle["hz_line_width"] = 0.5
                else:
                    nstyle["hz_line_width"] = 1
                nstyle["hz_line_color"] = colormap[node.name]
                nstyle["fgcolor"] = colormap[node.name]
                nstyle["size"] = 1 if node.event == self._SAMPLING_EVENT else 0
                node.set_style(nstyle)
        else:
            for node in self.traverse():
                nstyle = ete3.NodeStyle()
                nstyle["fgcolor"] = colormap[node.name]
                if not node.is_root() and not getattr(node.faces, "branch-bottom"):
                    node.add_face(self._time_face, 0, position="branch-top")
                    node.add_face(self._mutation_face, 0, position="branch-bottom")
                node.set_style(nstyle)

        fig = plt.figure(figsize=(2, 1))
        cax = fig.add_axes([0, 0, 1, 0.1])
        plt.colorbar(
            mpl.cm.ScalarMappable(cmap=cmap, norm=norm),
            orientation="horizontal",
            cax=cax,
            label=r"$x$",
        )
        if cbar_file is not None:
            plt.savefig(cbar_file)

        return super().render(*args, **kwargs)