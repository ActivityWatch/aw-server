#!/usr/bin/env python

import os
from typing import Dict, Any

# Stupid shit happened in pip 10: https://stackoverflow.com/a/49867265/965332
try:  # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError:  # for pip <= 9.0.3
    from pip.req import parse_requirements

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

about = {}  # type: Dict[str, Any]
with open(os.path.join(here, 'aw_server', '__about__.py'), 'r', encoding='utf-8') as f:
    exec(f.read(), about)

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

requirements = parse_requirements("./requirements.txt", session=False)

packages = find_packages()
if packages != ["aw_server", "aw_server.resources"]:
    print(f"Found extra packages: {packages}")

setup(name='aw-server',
      version=about["__version__"],
      description='ActivityWatch server',
      long_description=readme,
      author='Erik Bjäreholt',
      author_email='erik@bjareho.lt',
      url='https://github.com/ActivityWatch/aw-server',
      packages=packages,
      include_package_data=True,
      install_requires=[str(requirement.req) for requirement in requirements],
      entry_points={
          'console_scripts': ['aw-server = aw_server:main']
      },
      classifiers=[
          'Programming Language :: Python :: 3'
      ])
