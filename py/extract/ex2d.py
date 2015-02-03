"""
2D Spectroperfectionism extractions
"""

import numpy as N
import scipy.sparse
from scipy.sparse import spdiags, issparse
from scipy.sparse.linalg import spsolve

def ex2d(image, ivar, psf, specrange, wavelengths, xyrange=None,
         full_output=False, regularize=0.0):
    """
    2D PSF extraction of flux from image given pixel inverse variance.
    
    Inputs:
        image : 2D array of pixels
        ivar  : 2D array of inverse variance for the image
        psf   : PSF object
        specrange : (specmin, specmax) inclusive to extract
        wavelengths : 1D array of wavelengths to extract
        
    Optional Inputs:
        xyrange = (xmin, xmax, ymin, ymax): treat image as a subimage
            cutout of this region from the full image
        full_output : if True, return a dictionary of outputs including
            intermediate outputs such as the projection matrix.
        
    Returns (flux, ivar, R):
        flux[nspec, nwave] = extracted resolution convolved flux
        ivar[nspec, nwave] = inverse variance of flux
        R : 2D resolution matrix to convert
    """

    #- Range of image to consider
    waverange = (wavelengths[0], wavelengths[-1])
    
    if xyrange is None:
        xmin, xmax, ymin, ymax = xyrange = psf.xyrange(specrange, waverange)
        image = image[ymin:ymax, xmin:xmax]
        ivar = ivar[ymin:ymax, xmin:xmax]
    else:
        xmin, xmax, ymin, ymax = xyrange

    nx, ny = xmax-xmin, ymax-ymin
    npix = nx*ny
    
    nspec = specrange[1] - specrange[0]
    nflux = len(wavelengths)
    
    #- Solve AT W pix = (AT W A) flux
    
    #- Projection matrix and inverse covariance
    A = psf.projection_matrix(specrange, wavelengths, xyrange)

    #- Pixel weights matrix
    w = ivar.ravel()
    ### W = spdiags(ivar.ravel(), 0, npix, npix)

    #-----
    #- Extend A with an optional regularization term to limit ringing.
    #- If any flux bins don't contribute to these pixels,
    #- also use this term to constrain those flux bins to 0.
    
    #- HACK WARNING
    #- Regularize any flux bins that are below the 10th percentile
    #- in terms of how many pixels contribute to them
    ### ibad = (A.sum(axis=0).A == 0)[0]  #- Orig: exclude those with 0 pix
    npix = (A.A>0).sum(axis=0)
    p10 = N.percentile(npix[npix>0], 10)
    ibad = ( npix < p10 )
    nx = nspec*nflux
    I = regularize*scipy.sparse.identity(nx)
    if N.any(ibad):
        I.data[0, ibad] = 1.0
    
    #- Only need to extend A if regularization is non-zero
    if N.any(I.data):
        pix = N.concatenate( (image.ravel(), N.zeros(nx)) )
        Ax = scipy.sparse.vstack( (A, I) )
        wx = N.concatenate( (w, N.ones(nx)) )
    else:
        pix = image.ravel()
        Ax = A
        wx = w
        
    #- Inverse covariance
    W = spdiags(wx, 0, len(wx), len(wx))
    iCov = Ax.T.dot(W.dot(Ax))
    
    #- Solve (image = A flux) weighted by W:
    #-     A^T W image = (A^T W A) flux = iCov flux    
    y = Ax.T.dot(W.dot(pix))
    
    xflux = spsolve(iCov, y).reshape((nspec, nflux))

    #- Solve for Resolution matrix
    try:
        R, ivar = resolution_from_icov(iCov)
    except N.linalg.linalg.LinAlgError, err:
        outfile = 'LinAlgError_{}-{}_{}-{}.fits'.format(specrange[0], specrange[1], waverange[0], waverange[1])
        print "ERROR: Linear Algebra didn't converge"
        print "Dumping {} for debugging".format(outfile)
        import fitsio
        fitsio.write(outfile, image, clobber=True)
        fitsio.write(outfile, ivar)
        fitsio.write(outfile, A.toarray())
        raise err
        
    #- Convolve with Resolution matrix to decorrelate errors
    ivar = ivar.reshape((nspec, nflux))
    rflux = R.dot(xflux.ravel()).reshape(xflux.shape)

    if full_output:
        results = dict(flux=rflux, ivar=ivar, R=R, xflux=xflux, A=A)
        results['iCov'] = iCov
        return results
    else:
        return rflux, ivar, R
    

def sym_sqrt(a):
    """
    NAME: sym_sqrt

    PURPOSE: take 'square root' of a symmetric matrix via diagonalization

    USAGE: s = sym_sqrt(a)

    ARGUMENT: a: real symmetric square 2D ndarray

    RETURNS: s such that a = numpy.dot(s, s)

    WRITTEN: Adam S. Bolton, U. of Utah, 2009
    """
    
    w, v = N.linalg.eigh(a)        
    w[w<0]=0 # Is this necessary to enforce eigenvalues positive definite???
        
    # dm = n.diagflat(n.sqrt(w))
    # result = n.dot(v, n.dot(dm, n.transpose(v)))

    #- A bit faster with sparse matrix for multiplication:
    nw = len(w)
    dm = spdiags(N.sqrt(w), 0, nw, nw)
    result = v.dot( dm.dot(v.T) )
    
    return result

def resolution_from_icov(icov):
    """
    Function to generate the 'resolution matrix' in the simplest
    (no unrelated crosstalk) Bolton & Schlegel 2010 sense.
    Works on dense matrices.  May not be suited for production-scale
    determination in a spectro extraction pipeline.

    Input argument is inverse covariance matrix array.
    If input is not 2D and symmetric, results will be unpredictable.
    
    returns (R, ivar):
        R : resolution matrix
        ivar : R C R.T  -- decorrelated resolution convolved inverse variance

    WRITTEN: Adam S. Bolton, U. of Utah, 2009
    """
    if issparse(icov):
        icov = icov.toarray()
        
    sqrt_icov = sym_sqrt(icov)
    norm_vector = N.sum(sqrt_icov, axis=1)
    R = N.outer(norm_vector**(-1), N.ones(norm_vector.size)) * sqrt_icov
    ivar = norm_vector**2  #- Bolton & Schlegel 2010 Eqn 13
    return R, ivar
