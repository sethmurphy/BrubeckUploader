#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='brubeck-uploader',
    version='0.1.12',
    description='Brubeck module for uploading files',
    author='Seth Murphy',
    author_email='seth@brooklyncode.com',
    url='http://github.com/sethmurphy/BrubeckUploader',
    packages=find_packages(),
    install_requires=[
        "brubeck-service >= 0.1.4",
    ],
)
