#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# vim: fenc=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#
#

"""
File name: setup.py
Version: 0.1
Author: dhilipsiva <dhilipsiva@gmail.com>
Date created: 2015-11-24
"""

from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))
f = path.join(here, 'README.md')

setup(
    name='pymobiledevice',
    version='0.1.1',
    description="Interface with iOS devices",
    url='https://github.com/appknox/pymobiledevice',
    author='dhilipsiva',
    author_email='dhilipsiva@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='pymobiledevice ios iphone ipad ipod',
    packages=find_packages(),
    py_modules=['pymobiledevice'],
    entry_points='',
    install_requires=[
        'ak-vendor',
        'ak-construct',
        'ak-m2crypto',
    ],
    extras_require={
        'dev': [''],
        'test': [''],
    },
)
