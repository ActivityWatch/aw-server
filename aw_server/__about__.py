from typing import Optional
import os
import subprocess
import pkg_resources
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# TODO: Remove reliance on
basever = "v0.11"

srcpath = Path(__file__).absolute().parent
projectpath = srcpath.parent
bundlepath = projectpath.parent  # the ActivityWatch bundle repo, in some circumstances

# This line set by script when run (metaprogramming)
__version__ = "v0.11.0b1.dev+98fd120"


def get_rev():
    p = subprocess.run(
        "git rev-parse HEAD",
        shell=True,
        capture_output=True,
        encoding="utf8",
        cwd=workdir,
    )
    return p.stdout.strip()


def detect_version_ci() -> Optional[str]:
    # always set to true in GitHub actions
    if os.environ.get("CI", False) == "true":
        # GitHub Actions build
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

    for env_var in ["TRAVIS_TAG", "APPVEYOR_REPO_TAG_NAME"]:
        if env_var in os.environ:
            return os.environ[env_var]
    for env_var in ["TRAVIS_COMMIT", "APPVEYOR_REPO_COMMIT"]:
        # TODO: Add build number/id
        if env_var in os.environ:
            return basever + "+commit." + os.environ[env_var]
    return None


def detect_version_git() -> Optional[str]:
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--abbrev=0", "--tags"], encoding="utf8", cwd=workdir
        ).strip()
        if tag:
            basever = tag
        return (
            basever
            + ".dev+"
            + str(
                subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"], cwd=workdir
                ).strip(),
                "utf8",
            )
        )
    except Exception as e:
        # Unable to get current commit with git
        logger.exception(e)
        return None


def detect_version_pkg() -> Optional[str]:
    try:
        return pkg_resources.get_distribution("aw-server").version
    except pkg_resources.DistributionNotFound:
        return None


def detect_version():
    for detectfunc in (detect_version_ci, detect_version_git, detect_version_pkg):
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
    print(f"  ci:  {detect_version_ci()}")
    print(f"  pkg: {detect_version_pkg()}")
