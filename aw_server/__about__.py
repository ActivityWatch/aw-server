import os
import subprocess
import pkg_resources


def detect_version():
    basever = "v0.8"

    for env_var in ["TRAVIS_TAG", "APPVEYOR_REPO_TAG_NAME"]:
        if env_var in os.environ:
            return os.environ[env_var]

    for env_var in ["TRAVIS_COMMIT", "APPVEYOR_REPO_COMMIT"]:
        if env_var in os.environ:
            return basever + "-" + os.environ[env_var]

    try:
        return pkg_resources.get_distribution("aw-server").version
    except pkg_resources.DistributionNotFound:
        pass

    try:
        return basever + "-dev-" + str(subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip(), "utf8")
    except Exception as e:
        print("Unable to get current commit with git")

    return basever + "-dev-unknown"


__version__ = detect_version()
