#!/usr/bin/env python
# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function
#
# Standard imports
#
import glob
import os
import sys
#
# setuptools' sdist command ignores MANIFEST.in
#
from distutils.command.sdist import sdist as DistutilsSdist
from setuptools import setup, find_packages
#
# Begin setup
#
setup_keywords = dict()
#
# THESE SETTINGS NEED TO BE CHANGED FOR EVERY PRODUCT.
#
setup_keywords['name'] = 'specter'
setup_keywords['description'] = 'A toolkit for spectroperfectionism with multi-object spectrographs.'
setup_keywords['author'] = 'DESI Collaboration'
setup_keywords['author_email'] = 'desi-data@desi.lbl.gov'
setup_keywords['license'] = 'BSD'
setup_keywords['url'] = 'https://github.com/desihub/specter'
#
# END OF SETTINGS THAT NEED TO BE CHANGED.
#
sys.path.insert(int(sys.path[0] == ''), './py')
try:
    from importlib import import_module
    product = import_module(setup_keywords['name'])
    setup_keywords['long_description'] = product.__doc__
    setup_keywords['version'] = product.__version__
except ImportError:
    print('ERROR: unable to load specter; exiting.')
    sys.exit(1)
#
# Use README.rst as long_description.
#
# setup_keywords['long_description'] = ''
if os.path.exists('README.rst'):
    with open('README.rst') as readme:
        setup_keywords['long_description'] = readme.read()
#
# Set other keywords for the setup function.  These are automated, & should
# be left alone unless you are an expert.
#
# Treat everything in bin/ except *.rst as a script to be installed.
#
if os.path.isdir('bin'):
    setup_keywords['scripts'] = [fname for fname in glob.glob(os.path.join('bin', '*'))
        if not os.path.basename(fname).endswith('.rst')]
setup_keywords['provides'] = [setup_keywords['name']]
setup_keywords['requires'] = ['Python (>2.7.0)']
# setup_keywords['install_requires'] = ['Python (>2.7.0)']
setup_keywords['zip_safe'] = False
setup_keywords['use_2to3'] = True
setup_keywords['packages'] = find_packages('py')
setup_keywords['package_dir'] = {'':'py'}
setup_keywords['cmdclass'] = {'sdist': DistutilsSdist}
setup_keywords['test_suite'] = '{name}.test.{name}_test_suite.{name}_test_suite'.format(**setup_keywords)
#
# Autogenerate command-line scripts.
#
# setup_keywords['entry_points'] = {'console_scripts':['desiInstall = desiutil.install.main:main']}
#
# Add internal data directories.
#
setup_keywords['package_data'] = {'specter': ['data/*'],
                                  'specter.test': ['t/*']}
#
# Run setup command.
#
setup(**setup_keywords)
