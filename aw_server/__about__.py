from typing import Optional
import os
import subprocess
import pkg_resources
import re


basever = "v0.9"


def detect_version_ci() -> Optional[str]:
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
        return basever + ".dev+" + str(subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip(), "utf8")
    except Exception as e:
        # Unable to get current commit with git
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


__version__ = 'v0.8.dev+c6433ea'


def assign_static_version():
    """Self-modifies the current script to lock in version"""
    version = detect_version()
    with open(__file__, "r") as f:
        versionline = "\n__version__ = '{}'".format(version)
        data = re.sub(r"\n__version__ = [^\n;]+", versionline, f.read())

    with open(__file__, "w") as f:
        f.write(data)

    print("Set versionline: {}".format(versionline.strip()))


if __name__ == "__main__":
    assign_static_version()
