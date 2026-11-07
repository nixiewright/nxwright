"""Pairs fixture-bearing leader probes with their selected follower probes.

F and K follow T. E follows P. A pair uses the original probes, including
both change callables. Packaging probes borrow user code and are not paired.
"""
from importlib import import_module
import pkgutil

from tools.tft import probing
from tools.tft.probing.probe_runner import Probe


# F moves the xfloat away from the gauge and builds its own attribute code.
# These are separate projects, not selections of the same-named T probes.
_F_OWN_ATTRIBUTE_PROBES = {
    "f-other-attributes-read",
    "f-other-attributes-set",
    "f-other-attributes-in-commands",
}


def _by_name(probes, description: str) -> dict[str, Probe]:
    found = {}
    for probe in probes:
        if probe.name in found:
            raise ValueError("ambiguous %s probe name: %s" % (description, probe.name))
        found[probe.name] = probe
    return found


def _leader_probes(series: str) -> dict[str, Probe]:
    probes = []
    for module_info in pkgutil.iter_modules(probing.__path__, probing.__name__ + "."):
        if not module_info.name.endswith("_probes"):
            continue
        module = import_module(module_info.name)
        # A probe of an older Nextion Editor keeps that Editor's file, which
        # nxwright writes none of: its `ours` is None (kept_from_the_editor).
        probes.extend(probe for probe in getattr(module, "PROBES", ())
                      if probe.base == series and probe.fixtures is not None
                      and probe.borrows is None and probe.ours is not None)
    return _by_name(probes, series)


def paired_probes(follower: str) -> list[tuple[Probe, Probe]]:
    """Returns selected (leader, follower) probes whose leader keeps fixtures.

    Follower fixtures are not needed. The names and change callables must
    identify the same selection. Duplicate names and changed inputs raise
    ValueError. F's three separate attribute projects are not T selections.
    """
    if follower not in ("F", "K", "E"):
        raise ValueError("no leader is defined for follower %r" % follower)
    leader = "P" if follower == "E" else "T"
    module = import_module("tools.tft.probing.%s_probes" % follower.lower())
    selected = _by_name(module.PROBES, follower)
    available = _leader_probes(leader)
    prefix = follower.lower() + "-"
    pairs = []
    for name, probe in selected.items():
        if not name.startswith(prefix) or probe.base != follower:
            raise ValueError("unexpected %s probe inputs: %s" % (follower, name))
        if probe.borrows is not None:
            continue
        leader_name = ("p-" if follower == "E" else "") + name[len(prefix):]
        leader_probe = available.get(leader_name)
        if leader_probe is None:
            continue
        if probe.change is not leader_probe.change:
            if (follower == "F" and name in _F_OWN_ATTRIBUTE_PROBES
                    and probe.fixtures is None):
                continue
            raise ValueError("%s selects %s by name but changes its inputs" %
                             (name, leader_name))
        pairs.append((leader_probe, probe))
    return pairs
