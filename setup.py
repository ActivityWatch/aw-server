#!/usr/bin/env python

from setuptools import setup

setup(name='aw-server',
      version='0.1',
      description='ActivityWatch server',
      author='Erik Bjäreholt',
      author_email='erik@bjareho.lt',
      url='https://github.com/ActivityWatch/aw-server',
      packages=['aw_server'],
      install_requires=['aw-core', 'flask>=0.10', 'Flask-RESTful>=0.3', 'Flask-Cors>=2.1', 'pymongo>=3.2', 'appdirs==1.4.0'],
      entry_points={
            'console_scripts': ['aw-server = aw_server:main']
        }
     )
