#!/usr/bin/env python

from setuptools import setup

setup(name='aw-server',
      version='0.1',
      description='ActivityWatch server',
      author='Erik Bjäreholt',
      author_email='erik@bjareho.lt',
      url='https://github.com/ActivityWatch/aw-server',
      packages=['aw_server'],
      install_requires=['aw-core', 'flask>=0.10', 'flask-restplus>=0.9.2', 'flask-cors>=2.1', 'pymongo>=3.2', 'appdirs==1.4.0', 'python-json-logger>=0.1.5'],
      dependency_links=[
          'https://github.com/ActivityWatch/aw-core/tarball/master#egg=aw-core'
      ],
      entry_points={
          'console_scripts': ['aw-server = aw_server:main']
      })
