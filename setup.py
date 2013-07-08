#!/usr/bin/env python
 
from distutils.core import setup
 
setup(name='brubeck-uploader',
    version='0.1.5',
    description='Brubeck module for uploading files',
    author='Seth Murphy',
    author_email='seth@brooklyncode.com',
    url='http://github.com/sethmurphy/BrubeckUploader',
    packages=['brubeckuploader'],
    install_requires=[
        "brubeck-service >= 0.1.0",
    ],
)
