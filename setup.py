#!/usr/bin/env python

from pip.req import parse_requirements
from setuptools import setup

requirements = parse_requirements("./requirements.txt", session=False)

setup(name='aw-server',
      version='0.1',
      description='ActivityWatch server',
      author='Erik Bjäreholt',
      author_email='erik@bjareho.lt',
      url='https://github.com/ActivityWatch/aw-server',
      packages=['aw_server'],
      include_package_data=True,
      install_requires=[str(requirement.req) for requirement in requirements],
      entry_points={
          'console_scripts': ['aw-server = aw_server:main']
      },
      classifiers=[
          'Programming Language :: Python :: 3'
      ])
