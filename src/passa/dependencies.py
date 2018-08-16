import functools
import os
import sys

import distlib.wheel
import packaging.utils
import packaging.version
import requests
import requirementslib
import requirementslib.models.cache
import requirementslib.models.utils
import six

from ._pip import build_wheel
from .markers import contains_extra, get_contained_extras, get_without_extra


DEPENDENCY_CACHE = requirementslib.models.cache.DependencyCache()


def _cached(f, **kwargs):

    @functools.wraps(f)
    def wrapped(ireq):
        result = f(ireq, **kwargs)
        if (result is not None and
                requirementslib.models.utils.is_pinned_requirement(ireq)):
            DEPENDENCY_CACHE[ireq] = result
        return result

    return wrapped


def _get_dependencies_from_cache(ireq):
    """Retrieves dependencies for the requirement from the dependency cache.
    """
    if ireq.editable:
        return

    try:
        cached = DEPENDENCY_CACHE[ireq]
    except KeyError:
        return

    # Preserving sanity: Run through the cache and make sure every entry if
    # valid. If this fails, something is wrong with the cache. Drop it.
    ireq_name = packaging.utils.canonicalize_name(ireq.name)
    try:
        broken = False
        for line in cached:
            dep_req = requirementslib.Requirement.from_line(line)
            if contains_extra(dep_req.markers):
                broken = True   # The "extra =" marker breaks everything.
            elif dep_req.normalized_name == ireq_name:
                broken = True   # A package cannot depend on itself.
            if broken:
                break
    except Exception:
        broken = True

    if broken:
        del DEPENDENCY_CACHE[ireq]
        return

    return cached


def _get_dependencies_from_json(ireq, sources):
    """Retrieves dependencies for the given install requirement from the json api.

    :param ireq: A single InstallRequirement
    :type ireq: :class:`~pip._internal.req.req_install.InstallRequirement`
    :return: A set of dependency lines for generating new InstallRequirements.
    :rtype: set(str) or None
    """

    if ireq.editable:
        return

    # It is technically possible to parse extras out of the JSON API's
    # requirement format, but it is such a chore let's just use the simple API.
    if ireq.extras:
        return

    url_prefixes = [
        proc_url[:-7]   # Strip "/simple".
        for proc_url in (
            raw_url.rstrip("/")
            for raw_url in (source.get("url", "") for source in sources)
        )
        if proc_url.endswith("/simple")
    ]

    session = requests.session()
    version = str(ireq.specifier).lstrip("=")

    dependencies = None
    for prefix in url_prefixes:
        url = "{prefix}/pypi/{name}/{version}/json".format(
            prefix=prefix,
            name=packaging.utils.canonicalize_name(ireq.name),
            version=version,
        )
        try:
            response = session.get(url)
            response.raise_for_status()
            info = response.json()["info"]
            dependencies = [
                dep_req.as_line(include_hashes=False) for dep_req in (
                    requirementslib.Requirement.from_line(line)
                    for line in info.get("requires_dist", info["requires"])
                )
                if not contains_extra(dep_req.markers)
            ]
        except Exception:
            continue
        break
    return dependencies


def _read_requirements(wheel, extras):
    """Read wheel metadata to know what it depends on.

    The `run_requires` attribute contains a list of dict or str specifying
    requirements. For dicts, it may contain an "extra" key to specify these
    requirements are for a specific extra. Unfortunately, not all fields are
    specificed like this (I don't know why); some are specified with markers.
    So we jump though these terrible hoops to know exactly what we need.

    The extra extraction is not comprehensive. Tt assumes the marker is NEVER
    something like `extra == "foo" and extra == "bar"`. I guess this never
    makes sense anyway? Markers are just terrible.
    """
    extras = extras or ()
    requirements = []
    for entry in wheel.metadata.run_requires:
        if isinstance(entry, six.text_type):
            entry = {"requires": [entry]}
            extra = None
        else:
            extra = entry.get("extra")
        if extra is not None and extra not in extras:
            continue
        for line in entry.get("requires", []):
            r = requirementslib.Requirement.from_line(line)
            if r.markers:
                contained = get_contained_extras(r.markers)
                if (contained and not any(e in contained for e in extras)):
                    continue
                marker = get_without_extra(r.markers)
                r.markers = str(marker) if marker else None
                line = r.as_line(include_hashes=False)
            requirements.append(line)
    return requirements


def _get_dependencies_from_pip(ireq, sources):
    """Retrieves dependencies for the requirement from pip internals.

    The current strategy is to build a wheel out of the ireq, and read metadata
    out of it.
    """
    wheel_path = build_wheel(ireq, sources)
    if not wheel_path or not os.path.exists(wheel_path):
        raise RuntimeError("failed to build wheel from {}".format(ireq))
    wheel = distlib.wheel.Wheel(wheel_path)
    extras = ireq.extras or ()
    requirements = _read_requirements(wheel, extras)
    return requirements


def get_dependencies(requirement, sources):
    """Get all dependencies for a given install requirement.

    :param requirement: A requirement
    :param sources: Pipfile-formatted sources
    :type sources: list[dict]
    """
    getters = [
        _get_dependencies_from_cache,
        _cached(_get_dependencies_from_json, sources=sources),
        _cached(_get_dependencies_from_pip, sources=sources),
    ]
    ireq = requirement.as_ireq()
    last_exc = None
    for getter in getters:
        try:
            deps = getter(ireq)
        except Exception as e:
            last_exc = sys.exc_info()
            continue
        if deps is not None:
            return [requirementslib.Requirement.from_line(d) for d in deps]
    if last_exc:
        six.reraise(*last_exc)
    raise RuntimeError("failed to get dependencies for {}".format(
        requirement.as_line(),
    ))
