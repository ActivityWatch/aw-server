import subprocess
import re
import logging
from typing import Optional
from pathlib import Path

import pkg_resources

from importlib.metadata import version as get_version

logger = logging.getLogger(__name__)

# TODO: Remove reliance on
basever = "v0.12"

srcpath = Path(__file__).absolute().parent
projectpath = srcpath.parent
bundlepath = projectpath.parent  # the ActivityWatch bundle repo, in some circumstances

# This line set by script when run (metaprogramming)
__version__ = "v0.12.0b2.dev+1c03eb2"


def get_rev():
    p = subprocess.run(
        "git rev-parse --short HEAD",
        shell=True,
        capture_output=True,
        encoding="utf8",
        cwd=workdir,
    )
    return p.stdout.strip()


def get_tag_exact():
    rev = get_rev()
    p = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--exact-match", rev],
        capture_output=True,
        encoding="utf8",
        cwd=workdir,
    )
    if p.stderr:
        if (
            "no tag exactly matches" in p.stderr
            or "No names found, cannot describe anything" in p.stderr
        ):
            pass
        else:
            raise Exception(p.stderr)
    else:
        return p.stdout.strip()


def get_tag_latest():
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--abbrev=0", "--tags"], encoding="utf8", cwd=workdir
        ).strip()
        if tag:
            basever = tag
    except subprocess.CalledProcessError as e:
        print(e)
        return

    try:
        return f"{basever}.dev+{get_rev()}"
    except Exception as e:
        # Unable to get current commit with git
        logger.exception(e)
        return None


def detect_version_git() -> Optional[str]:
    # Returns an exact tag if there is one, or an approximate one + commit identifier
    version = get_tag_exact()
    if version:
        return version

    version = get_tag_latest()
    if version:
        return version

    return None


def detect_version_pkg() -> Optional[str]:
    try:
        return f"v{get_version('aw-server')}.dev+{get_rev()}"
    except pkg_resources.DistributionNotFound:
        return None


def detect_version():
    for detectfunc in (detect_version_git, detect_version_pkg):
        version = detectfunc()
        if version:
            return version

    return basever + ".dev+unknown"


def assign_static_version():
    """Self-modifies the current script to lock in version"""
    version = detect_version()
    with open(__file__, "r") as f:
        versionline = '\n__version__ = "{}"'.format(version)
        data = re.sub(r"\n__version__ = [^\n;]+", versionline, f.read())

    with open(__file__, "w") as f:
        f.write(data)

    print("Set versionline: {}".format(versionline.strip()))


if __name__ == "__main__":
    # Use the bundle repo as working repo, if it exists
    if (bundlepath / ".git").exists():
        print("Found bundle repo in parent dir, using for calls to git")
        workdir = bundlepath
    else:
        workdir = projectpath

    assign_static_version()

    print("By method:")
    print(f"  git: {detect_version_git()}")
    print(f"  pkg: {detect_version_pkg()}")
