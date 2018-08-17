import atexit
import os
import shutil
import tempfile


def identify_requirment(r):
    """Produce an identifier for a requirement to use in the resolver.

    Note that we are treating the same package with different extras as
    distinct. This allows semantics like "I only want this extra in
    development, not production".

    This also makes the resolver's implementation much simpler, with the minor
    costs of possibly needing a few extra resolution steps if we happen to have
    the same package apprearing multiple times.
    """
    return "{0}{1}".format(r.normalized_name, r.extras_as_pip)


def mkdir_p(path, mode=0o777):
    try:
        os.makedirs(path, mode=mode)
    except OSError:
        # Backporting os.makedirs(exist_ok=True) from newer Pythons.
        if not os.path.isdir(path):
            raise


def cheesy_temporary_directory(*args, **kwargs):
    """A very naive tempeorary directory.

    This is intended as a last-resort when nothing viable is provided. Avoid
    using this if possible. The directory is created with `tempfile.mkdtemp`,
    and removed on program exit. The removal is done only with minimal effort.
    """
    temp_src = tempfile.mkdtemp(*args, **kwargs)

    def cleanup():
        try:
            shutil.rmtree(temp_src)
        except Exception as e:
            pass    # Whatever.

    atexit.register(cleanup)
    return temp_src


def get_pinned_version(ireq):
    """Get the pinned version of an InstallRequirement.

    An InstallRequirement is considered pinned if:

    - Is not editable
    - It has exactly one specifier
    - That specifier is "=="
    - The version does not contain a wildcard

    Examples:
        django==1.8   # pinned
        django>1.8    # NOT pinned
        django~=1.8   # NOT pinned
        django==1.*   # NOT pinned

    Raises `TypeError` if the input is not a valid InstallRequirement, or
    `ValueError` if the InstallRequirement is not pinned.
    """
    try:
        specifier = ireq.specifier
    except AttributeError:
        raise TypeError("Expected InstallRequirement, not {}".format(
            type(ireq).__name__,
        ))

    if ireq.editable:
        raise ValueError("InstallRequirement is editable")
    if not specifier:
        raise ValueError("InstallRequirement has no version specification")
    if len(specifier._specs) != 1:
        raise ValueError("InstallRequirement has multiple specifications")

    op, version = next(iter(specifier._specs))._spec
    if op not in ('==', '===') or version.endswith('.*'):
        raise ValueError("InstallRequirement not pinned (is {0!r})".format(
            op + version,
        ))

    return version


def is_pinned(ireq):
    """Returns whether an InstallRequirement is a "pinned" requirement.

    An InstallRequirement is considered pinned if:

    - Is not editable
    - It has exactly one specifier
    - That specifier is "=="
    - The version does not contain a wildcard

    Examples:
        django==1.8   # pinned
        django>1.8    # NOT pinned
        django~=1.8   # NOT pinned
        django==1.*   # NOT pinned
    """
    try:
        get_pinned_version(ireq)
    except (TypeError, ValueError):
        return False
    return True
