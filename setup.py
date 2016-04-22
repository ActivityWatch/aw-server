#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='actwa-server',
      version='0.1',
      description='ActivityWatch server',
      author='Erik Bjäreholt',
      author_email='erik@bjareho.lt',
      url='https://github.com/ActivityWatch/actwa-server',
      namespace_packages=['actwa'],
      packages=['actwa.server'],
      install_requires=['actwa-client']
     )
