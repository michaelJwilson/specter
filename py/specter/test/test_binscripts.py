#!/usr/bin/env python

"""
Unit tests for executable scripts in specter/bin
"""
from __future__ import print_function
import os
import sys
import numpy as np
import unittest
from astropy.io import fits
from uuid import uuid4
from pkg_resources import resource_filename
from specter.test import test_data_dir
from ..io import read_image, write_spectra
from astropy.io import fits

_base = uuid4().hex
imgfile1 = 'testimg1-'+_base+'.fits'
imgfile2 = 'testimg2-'+_base+'.fits'
specfile1 = 'testspec1-'+_base+'.fits'
specfile2 = 'testspec2-'+_base+'.fits'


class TestBinScripts(unittest.TestCase):

    def setUp(self):
        self.specter_dir = os.path.dirname( # top-level
            os.path.dirname( # py/
                os.path.dirname( # specter/
                    os.path.dirname(os.path.abspath(__file__)) # test/
                    )
                )
            )
        self.executable = sys.executable
        self.sky_file = resource_filename('specter', 'data/sky-uves.fits')
        self.monospot_file = resource_filename('specter.test', 't/psf-monospot.fits')
        self.throughput_file = resource_filename('specter.test', 't/throughput.fits')
        self.exspec_cmd = """{executable} {specter_dir}/bin/exspec \
          -i {imgfile} \
          -p {monospot_file} \
          -o {specfile} \
          -w 7500,7620,{dwave} \
          --specmin {specmin} --nspec {nspec}"""

        #- Add this package to PYTHONPATH so that binscripts can find it
        try:
            self.origPath = os.environ['PYTHONPATH']
            os.environ['PYTHONPATH'] = os.path.join(self.specter_dir,'py') + ':' + self.origPath
        except KeyError:
            self.origPath = None
            os.environ['PYTHONPATH'] = os.path.join(self.specter_dir,'py')

    def tearDown(self):
        if self.origPath is None:
            del os.environ['PYTHONPATH']
        else:
            os.environ['PYTHONPATH'] = self.origPath

    def test_aa(self):
        cmd = """{executable} {specter_dir}/bin/specter \
          -i {sky} \
          -p {monospot_file} \
          -t {throughput_file} \
          -o {imgfile} \
          -w 7500,7620 \
          -n --specmin 0 --nspec 2 --exptime 1500""".format(
            executable=self.executable,
            specter_dir=self.specter_dir,
            sky=self.sky_file,
            monospot_file=self.monospot_file,
            throughput_file=self.throughput_file,
            imgfile = imgfile1)
        print(cmd)
        err = os.system(cmd)
        self.assertEqual(err, 0, 'Error code {} != 0'.format(err))
        self.assertTrue(os.path.exists(imgfile1))

        with fits.open(imgfile1) as fx:
            self.assertIn('CCDIMAGE', fx)
            self.assertIn('IVAR', fx)

        #- Test the I/O routines while we have the file handy
        image, ivar, hdr = read_image(imgfile1)
        self.assertEqual(image.shape, ivar.shape)

        os.remove(imgfile1)
        cmd = cmd + ' --extra'
        err = os.system(cmd)
        self.assertEqual(err, 0, 'Error code {} != 0'.format(err))
        self.assertTrue(os.path.exists(imgfile1))
        with fits.open(imgfile1) as fx:
            self.assertIn('PHOTONS', fx)
            self.assertIn('XYWAVE', fx)

    def test_bb(self):
        for dwave in [1.0, 2.0]:
            cmd = self.exspec_cmd.format(
                executable=self.executable,
                specter_dir=self.specter_dir,
                imgfile = imgfile1,
                monospot_file=self.monospot_file,
                specfile = specfile1,
                dwave = dwave,
                specmin=0, nspec=2,
                )
            err = os.system(cmd)
            self.assertEqual(err, 0, 'Error code {} != 0 with dwave={}'.format(err, dwave))
            self.assertTrue(os.path.exists(specfile1))

        with fits.open(specfile1) as fx:
            print(fx.info())
            self.assertIn('FLUX', fx)
            self.assertIn('IVAR', fx)
            self.assertIn('WAVELENGTH', fx)
            self.assertIn('RESOLUTION', fx)

            #- this is covered in the exspec binscript, but not yet visible to
            #- coverage tools; try it here just for good measure
            write_spectra(specfile2,
                fx['WAVELENGTH'].data, fx['FLUX'].data,
                fx['IVAR'].data, fx['RESOLUTION'].data, fx[0].header)

    def test_cc(self):
        #- Also check it works for the last fibers and not just the first ones
        cmd = self.exspec_cmd.format(
            executable=sys.executable,
            specter_dir=self.specter_dir,
            imgfile = imgfile1,
            monospot_file=self.monospot_file,
            specfile = specfile1,
            dwave = 1.0,
            specmin=498, nspec=2,
            )
        err = os.system(cmd)
        self.assertEqual(err, 0, 'Error code {} != 0 for --specrange=498,500'.format(err))
        self.assertTrue(os.path.exists(specfile1))

    def test_dd(self):
        """Test both single core and dual core running"""
        cmd = """{executable} {specter_dir}/bin/specter \
          -i {sky} \
          -p {monospot_file} \
          -t {throughput_file} \
          -w 7500,7620 \
          --specmin 0 --nspec 2 --exptime 1500 --trimxy""".format(
              executable=self.executable,
              specter_dir=self.specter_dir,
              sky=self.sky_file,
              monospot_file=self.monospot_file,
              throughput_file=self.throughput_file)

        if os.path.exists(imgfile1):
            os.remove(imgfile1)
        if os.path.exists(imgfile2):
            os.remove(imgfile2)

        err = os.system(cmd + " --numcores 1 -o " + imgfile1)
        self.assertEqual(err, 0, 'Error code {} != 0'.format(err))
        self.assertTrue(os.path.exists(imgfile1))

        err = os.system(cmd + " --numcores 2 -o " + imgfile2)
        self.assertEqual(err, 0, 'Error code {} != 0'.format(err))
        self.assertTrue(os.path.exists(imgfile2))

        img1 = fits.getdata(imgfile1)
        img2 = fits.getdata(imgfile2)

        self.assertTrue(np.allclose(img1, img2))

    @classmethod
    def tearDownClass(cls):
        for filename in [imgfile1, imgfile2, specfile1, specfile2]:
            if os.path.exists(filename):
                print("Removing", filename)
                os.remove(filename)


if __name__ == '__main__':
    unittest.main()
