"""
2D Spectroperfectionism extractions
"""
from __future__ import absolute_import, division, print_function

import sys
import numpy as np
import scipy.sparse
import scipy.linalg
from scipy.sparse import spdiags, issparse
from scipy.sparse.linalg import spsolve

def ex2d(image, imageivar, psf, specmin, nspec, wavelengths, xyrange=None,
         regularize=0.0, ndecorr=False, bundlesize=25, wavesize=50, verbose=False):
    '''
    TODO: DOCUMENT
    
    Returns: flux, ivar, Rdata
    '''
    #- TODO: check input dimensionality etc.

    dw = wavelengths[1] - wavelengths[0]
    if not np.allclose(dw, np.diff(wavelengths)):
        raise ValueError('ex2d currently only supports linear wavelength grids')

    #- Output arrays to fill
    nwave = len(wavelengths)
    flux = np.zeros( (nspec, nwave) )
    ivar = np.zeros( (nspec, nwave) )

    #- Diagonal elements of resolution matrix
    #- Keep resolution matrix terms equivalent to 9-sigma of largest spot
    #- ndiag is in units of number of wavelength steps of size dw
    ndiag = 0
    for ispec in [0, psf.nspec//2, psf.nspec-1]:
        for w in [psf.wmin, 0.5*(psf.wmin+psf.wmax), psf.wmax]:
            ndiag = max(ndiag, int(round(9.0*psf.wdisp(ispec, w) / dw )))

    #- Orig was ndiag = 10, which fails when dw gets too large compared to PSF size
    Rd = np.zeros( (nspec, 2*ndiag+1, nwave) )

    #- Let's do some extractions
    for speclo in range(specmin, specmin+nspec, bundlesize):
        #- index of last spectrum, non-inclusive, i.e. python-style indexing
        spechi = min(speclo+bundlesize, specmin+nspec)
        specrange = (speclo, spechi)

        for iwave in range(0, len(wavelengths), wavesize):
            #- Low and High wavelengths for the core region
            wlo = wavelengths[iwave]
            if iwave+wavesize < len(wavelengths):
                whi = wavelengths[iwave+wavesize]
            else:
                whi = wavelengths[-1]
        
            #- Identify subimage that covers the core wavelengths
            xyrange = xlo,xhi,ylo,yhi = psf.xyrange(specrange, (wlo, whi))
            subimg = image[ylo:yhi, xlo:xhi]
            subivar = imageivar[ylo:yhi, xlo:xhi]
    
            #- Determine extra border wavelength extent
            ny, nx = psf.pix(speclo, wlo).shape
            ymin = ylo-ny+2
            ymax = yhi+ny-2
        
            nlo = int((wlo - psf.wavelength(speclo, ymin))/dw)-1
            nhi = int((psf.wavelength(speclo, ymax) - whi)/dw)-1
            ww = np.arange(wlo-nlo*dw, whi+(nhi+0.5)*dw, dw)
            wmin, wmax = ww[0], ww[-1]
            nw = len(ww)
        
            #- include \r carriage return to prevent scrolling
            if verbose:
                sys.stdout.write("\rSpectra {specrange} wavelengths ({wmin:.2f}, {wmax:.2f}) -> ({wlo:.2f}, {whi:.2f})".format(\
                    specrange=specrange, wmin=wmin, wmax=wmax, wlo=wlo, whi=whi))
                sys.stdout.flush()

            #- Do the extraction
            specflux, specivar, R = \
                ex2d_patch(subimg, subivar, psf,
                    specmin=speclo, nspec=spechi-speclo, wavelengths=ww,
                    xyrange=xyrange, regularize=regularize, ndecorr=ndecorr)

            #- Fill in the final output arrays
            iispec = slice(speclo-specmin, spechi-specmin)
            flux[iispec, iwave:iwave+wavesize+1] = specflux[:, nlo:-nhi]
            ivar[iispec, iwave:iwave+wavesize+1] = specivar[:, nlo:-nhi]
    
            #- Fill diagonals of resolution matrix
            for ispec in range(speclo, spechi):
                #- subregion of R for this spectrum
                ii = slice(nw*(ispec-speclo), nw*(ispec-speclo+1))
                Rx = R[ii, ii]

                for j in range(nlo,nw-nhi):
                    # Rd dimensions [nspec, 2*ndiag+1, nwave]
                    Rd[ispec-specmin, :, iwave+j-nlo] = Rx[j-ndiag:j+ndiag+1, j]

    #- Add extra print because of carriage return \r progress trickery
    if verbose:
        print()

    #+ TODO: what should this do to R in the case of non-uniform bins?
    #+       maybe should do everything in photons/A from the start.            
    #- Convert flux to photons/A instead of photons/bin
    dwave = np.gradient(wavelengths)
    flux /= dwave
    ivar *= dwave**2
    
    return flux, ivar, Rd


def ex2d_patch(image, ivar, psf, specmin, nspec, wavelengths, xyrange=None,
         full_output=False, regularize=0.0, ndecorr=False):
    """
    2D PSF extraction of flux from image patch given pixel inverse variance.
    
    Inputs:
        image : 2D array of pixels
        ivar  : 2D array of inverse variance for the image
        psf   : PSF object
        specmin : index of first spectrum to extract
        nspec : number of spectra to extract
        wavelengths : 1D array of wavelengths to extract
        
    Optional Inputs:
        xyrange = (xmin, xmax, ymin, ymax): treat image as a subimage
            cutout of this region from the full image
        full_output : if True, return a dictionary of outputs including
            intermediate outputs such as the projection matrix.
        ndecorr : if True, decorrelate the noise between fibers, at the
            cost of residual signal correlations between fibers.
        
    Returns (flux, ivar, R):
        flux[nspec, nwave] = extracted resolution convolved flux
        ivar[nspec, nwave] = inverse variance of flux
        R : 2D resolution matrix to convert
    """

    #- Range of image to consider
    waverange = (wavelengths[0], wavelengths[-1])
    specrange = (specmin, specmin+nspec)
    
    if xyrange is None:
        xmin, xmax, ymin, ymax = xyrange = psf.xyrange(specrange, waverange)
        image = image[ymin:ymax, xmin:xmax]
        ivar = ivar[ymin:ymax, xmin:xmax]
    else:
        xmin, xmax, ymin, ymax = xyrange

    nx, ny = xmax-xmin, ymax-ymin
    npix = nx*ny
    
    nspec = specrange[1] - specrange[0]
    nwave = len(wavelengths)
    
    #- Solve AT W pix = (AT W A) flux
    
    #- Projection matrix and inverse covariance
    A = psf.projection_matrix(specrange, wavelengths, xyrange)

    #- Pixel weights matrix
    w = ivar.ravel()
    W = spdiags(ivar.ravel(), 0, npix, npix)

    #-----
    #- Extend A with an optional regularization term to limit ringing.
    #- If any flux bins don't contribute to these pixels,
    #- also use this term to constrain those flux bins to 0.
    
    #- Original: exclude flux bins with 0 pixels contributing
    # ibad = (A.sum(axis=0).A == 0)[0]
    
    #- Identify fluxes with very low weights of pixels contributing            
    fluxweight = W.dot(A).sum(axis=0).A[0]
    minweight = 0.01*np.max(fluxweight)
    ibad = fluxweight < minweight
    
    #- Original version; doesn't work on older versions of scipy
    # I = regularize*scipy.sparse.identity(nspec*nwave)
    # I.data[0,ibad] = minweight - fluxweight[ibad]
    
    #- Add regularization of low weight fluxes
    Idiag = regularize*np.ones(nspec*nwave)
    Idiag[ibad] = minweight - fluxweight[ibad]
    I = scipy.sparse.identity(nspec*nwave)
    I.setdiag(Idiag)

    #- Only need to extend A if regularization is non-zero
    if np.any(I.diagonal()):
        pix = np.concatenate( (image.ravel(), np.zeros(nspec*nwave)) )
        Ax = scipy.sparse.vstack( (A, I) )
        wx = np.concatenate( (w, np.ones(nspec*nwave)) )
    else:
        pix = image.ravel()
        Ax = A
        wx = w

    #- Inverse covariance
    Wx = spdiags(wx, 0, len(wx), len(wx))
    iCov = Ax.T.dot(Wx.dot(Ax))

    #- Solve (image = A flux) weighted by Wx:
    #-     A^T W image = (A^T W A) flux = iCov flux    
    y = Ax.T.dot(Wx.dot(pix))
    
    xflux = spsolve(iCov, y).reshape((nspec, nwave))

    #- Solve for Resolution matrix
    try:
        if ndecorr:
            R, fluxivar = resolution_from_icov(iCov)
        else:
            R, fluxivar = resolution_from_icov(iCov, decorr=[nwave for x in range(nspec)])
    except np.linalg.linalg.LinAlgError, err:
        outfile = 'LinAlgError_{}-{}_{}-{}.fits'.format(specrange[0], specrange[1], waverange[0], waverange[1])
        print("ERROR: Linear Algebra didn't converge")
        print("Dumping {} for debugging".format(outfile))
        from astropy.io import fits
        fits.writeto(outfile, image, clobber=True)
        fits.append(outfile, ivar, name='IVAR')
        fits.append(outfile, A.data, name='ADATA') 
        fits.append(outfile, A.indices, name='AINDICES')
        fits.append(outfile, A.indptr, name='AINDPTR')
        fits.append(outfile, iCov.toarray(), name='ICOV')
        raise err
        
    #- Convolve with Resolution matrix to decorrelate errors
    fluxivar = fluxivar.reshape((nspec, nwave))
    rflux = R.dot(xflux.ravel()).reshape(xflux.shape)

    if full_output:
        results = dict(flux=rflux, ivar=fluxivar, R=R, xflux=xflux, A=A)
        results['iCov'] = iCov
        return results
    else:
        return rflux, fluxivar, R


def eigen_compose(w, v, invert=False, sqr=False):
    """
    Create a matrix from its eigenvectors and eigenvalues.

    Given the eigendecomposition of a matrix, recompose this
    into a real symmetric matrix.  Optionally take the square
    root of the eigenvalues and / or invert the eigenvalues.
    The eigenvalues are regularized such that the condition 
    number remains within machine precision for 64bit floating 
    point values.

    Args:
        w (array): 1D array of eigenvalues
        v (array): 2D array of eigenvectors.
        invert (bool): Should the eigenvalues be inverted? (False)
        sqr (bool): Should the square root eigenvalues be used? (False)

    Returns:
        A 2D numpy array which is the recomposed matrix.
    """
    dim = w.shape[0]

    # Threshold is 10 times the machine precision (~1e-15)
    threshold = 10.0 * sys.float_info.epsilon

    maxval = np.max(w)
    wscaled = np.zeros_like(w)

    if invert:
        # Normally, one should avoid explicit loops in python.
        # in this case however, we need to conditionally invert
        # the eigenvalues only if they are above the threshold.
        # Otherwise we might divide by zero.  Since the number
        # of eigenvalues is never too large, this should be fine.
        # If it does impact performance, we can improve this in
        # the future.  NOTE: simple timing with an average over
        # 10 loops shows that all four permutations of invert and
        # sqr options take about the same time- so this is not
        # an issue.
        if sqr:
            minval = np.sqrt(maxval) * threshold
            replace = 1.0 / minval
            tempsqr = np.sqrt(w)
            for i in range(dim):
                if tempsqr[i] > minval:
                    wscaled[i] = 1.0 / tempsqr[i]
                else:
                    wscaled[i] = replace
        else:
            minval = maxval * threshold
            replace = 1.0 / minval
            for i in range(dim):
                if w[i] > minval:
                    wscaled[i] = 1.0 / w[i]
                else:
                    wscaled[i] = replace
    else:
        if sqr:
            minval = np.sqrt(maxval) * threshold
            replace = minval
            wscaled[:] = np.where((w > minval), np.sqrt(w), replace*np.ones_like(w))
        else:
            minval = maxval * threshold
            replace = minval
            wscaled[:] = np.where((w > minval), w, replace*np.ones_like(w))

    # multiply to get result
    wdiag = spdiags(wscaled, 0, dim, dim)
    return v.dot( wdiag.dot(v.T) )


def resolution_from_icov(icov, decorr=None):
    """
    Function to generate the 'resolution matrix' in the simplest
    (no unrelated crosstalk) Bolton & Schlegel 2010 sense.
    Works on dense matrices.  May not be suited for production-scale
    determination in a spectro extraction pipeline.

    Args:
        icov (array): real, symmetric, 2D array containing inverse
                      covariance.
        decorr (list): produce a resolution matrix which decorrelates
                      signal between fibers, at the cost of correlated
                      noise between fibers (default).  This list should
                      contain the number of elements in each spectrum,
                      which is used to define the size of the blocks.

    Returns (R, ivar):
        R : resolution matrix
        ivar : R C R.T  -- decorrelated resolution convolved inverse variance
    """
    #- force symmetry since due to rounding it might not be exactly symmetric
    icov = 0.5*(icov + icov.T)
    
    if issparse(icov):
        icov = icov.toarray()

    w, v = scipy.linalg.eigh(icov)

    sqrt_icov = np.zeros_like(icov)

    if decorr is not None:
        if np.sum(decorr) != icov.shape[0]:
            raise RuntimeError("The list of spectral block sizes must sum to the matrix size")
        inverse = eigen_compose(w, v, invert=True)
        # take each spectrum block and process
        offset = 0
        for b in decorr:
            bw, bv = scipy.linalg.eigh(inverse[offset:offset+b,offset:offset+b])
            sqrt_icov[offset:offset+b,offset:offset+b] = eigen_compose(bw, bv, invert=True, sqr=True)
            offset += b
    else:
        sqrt_icov = eigen_compose(w, v, sqr=True)

    norm_vector = np.sum(sqrt_icov, axis=1)
    R = np.outer(norm_vector**(-1), np.ones(norm_vector.size)) * sqrt_icov
    ivar = norm_vector**2  #- Bolton & Schlegel 2010 Eqn 13
    return R, ivar
