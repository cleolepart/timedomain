from abc import ABC
import numpy as np

import matplotlib as mpl
import matplotlib.pyplot as plt

from scipy.constants import c
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d

from astropy.table import Table

import os
from glob import glob

from astropy.table import Table, join, vstack, hstack, unique

from desispec.io import read_spectra
from desispec.spectra import Spectra
from desispec.coaddition import coadd_cameras

import redrock.templates

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import warnings

from scipy.signal import butter,filtfilt

from desispec.interpolation import resample_flux
from desispec.resolution import Resolution

####

def singlegaus(x,A,mu,sigma):
    y = A*np.exp(-(x-mu)**2/(2*sigma**2))
    return y
def doublegaus(x,A1,mu1,sigma1,A2,mu2,sigma2):
    y = A1*np.exp(-(x-mu1)**2/(2*sigma1**2)) + A2*np.exp(-(x-mu2)**2/(2*sigma2**2)) 
    return y


def triplegaus(x,A1,mu1,sigma1,A2,mu2,sigma2,A3,mu3,sigma3):
    y = A1*np.exp(-(x-mu1)**2/(2*sigma1**2)) + A2*np.exp(-(x-mu2)**2/(2*sigma2**2)) + \
        A3*np.exp(-(x-mu3)**2/(2*sigma3**2))
    return y

def quadgaus(x,A1,mu1,sigma1,A2,mu2,sigma2,A3,mu3,sigma3,A4,mu4,sigma4):
    y = A1*np.exp(-(x-mu1)**2/(2*sigma1**2)) + A2*np.exp(-(x-mu2)**2/(2*sigma2**2)) + \
        A3*np.exp(-(x-mu3)**2/(2*sigma3**2)) + A4*np.exp(-(x-mu4)**2/(2*sigma4**2))
    return y

def Combine_multifilt(wave,flux, mask,ivar):
        difwave_single = []
        difflux_single = []
        difmask_single = []
        difivar_single = []
        for band in wave:
            difwave_single += list(wave[band]) 
            difflux_single += list(flux[band])
            difivar_single += list(ivar[band])
            difmask_single += list(mask[band])
                
        diftable = Table([difwave_single, difflux_single,difmask_single,difivar_single], names = ('wave','flux', 'mask','ivar'))

        diftable.sort('wave')
        difwave_single = np.array(diftable['wave'])
        difflux_single = np.array(diftable['flux'])
        difivar_single = np.array(diftable['ivar'])
        difmask_single = np.array(diftable['mask'])
        return difwave_single,difflux_single,difmask_single,difivar_single
       

def line_finder(wave, flux,ivar,z):
    c = 2.99e5 #km/s

    lines = ['Halpha','Hbeta', 'Hgamma','HeII4686','OIII5007','NIII','SII','OIII4959']
    restwavelengths = [6562,4861,4340,4686,5007,4100, 6732,4959]
    
    
    
    HB_center = list(abs(wave-4861.4)).index(min(abs(wave - 4861.4)))
    HBroi = wave[HB_center - 500:HB_center + 500]
    HBflux = flux[HB_center - 500:HB_center + 500]
    HBsigma = np.sqrt(1/ivar[HB_center - 500:HB_center + 500])
    
    Ha_center = list(abs(wave-6562.79)).index(min(abs(wave - 6562.79)))
    Haroi = wave[Ha_center - 300:Ha_center + 300]
    Haflux = flux[Ha_center - 300:Ha_center + 300]
    Hasigma = np.sqrt(1/ivar[Ha_center - 300:Ha_center + 300])
    
    NIII_center = list(abs(wave-4200)).index(min(abs(wave - 4200)))
    NIIIroi = wave[NIII_center- 200:NIII_center+200]
    NIIIflux = flux[NIII_center- 200:NIII_center+200]
    NIIIsigma = np.sqrt(1/ivar[NIII_center - 200:NIII_center + 200])
    
    
    try:
        HBopt, HBcov = curve_fit(quadgaus, HBroi, HBflux, \
                                 p0 = [1,4686,3,1,4861,5,5,5007,0.125, 3, 4959,0.125],sigma = HBsigma, \
                                 maxfev = 3000, absolute_sigma = True)
    except RuntimeError:
        HBopt = [1,1,1,1,1,1,1,1,1,1,1,1]
        HBcov = np.ones((12,12))
    
    try:
        Haopt, Hacov = curve_fit(doublegaus, Haroi, Haflux, \
                             p0 = [3,6562,5,1,6732,1],sigma = Hasigma, \
                                 maxfev = 3000, absolute_sigma = True)
    except RuntimeError:
        Haopt = [1,1,1,1,1,1]
        Hacov = np.ones((6,6))
    try:
        NIIIopt, NIIIcov = curve_fit(doublegaus, NIIIroi, NIIIflux, \
                         p0 = [1,4100,2,1,4340,3],sigma = NIIIsigma, \
                                     maxfev = 3000,absolute_sigma = True)
    except RuntimeError:
        NIIIopt = [1,1,1,1,1,1]
        NIIIcov = np.ones((6,6))

    
    Haexp = doublegaus(Haroi, *Haopt)
    rHa = Haflux - Haexp
    Hachisq = np.sum(rHa**2/Hasigma**2)
    Hachisq = Hachisq/(len(Haroi)-len(Haopt))
    
    HBexp = quadgaus(HBroi, *HBopt)
    rHB = HBflux - HBexp
    HBchisq = np.sum(rHB**2/HBsigma**2)
    HBchisq = HBchisq/(len(HBroi)-len(HBopt))
    
    
    NIIIexp = doublegaus(NIIIroi, *NIIIopt)
    rNIII = NIIIflux - NIIIexp
    NIIIchisq = np.sum(rNIII**2/NIIIsigma**2)
    NIIIchisq = NIIIchisq/(len(NIIIroi)-len(NIIIopt))
    
    
    heights = []
    heights_err = []
    means = []
    means_err = []
    sigmas = []
    sigmas_err = []
    vs = []
    chi2s = []
    
    heights.append(Haopt[0]) #Ha data
    means.append(Haopt[1])
    sigmas.append(Haopt[2])
    vs.append((Haopt[2]*2.355/Haopt[1])*c)
    heights_err.append(np.sqrt(Hacov[0][0]))
    means_err.append(np.sqrt(Hacov[1][1]))
    sigmas_err.append(np.sqrt(Hacov[2][2]))
    chi2s.append(Hachisq)
    
    heights.append(HBopt[3]) #HB data
    means.append(HBopt[4])
    sigmas.append(HBopt[5])
    vs.append((HBopt[5]*2.355/HBopt[4])*c)
    heights_err.append(np.sqrt(HBcov[3][3]))
    means_err.append(np.sqrt(HBcov[4][4]))
    sigmas_err.append(np.sqrt(HBcov[5][5]))
    chi2s.append(HBchisq)
    
    heights.append(NIIIopt[3]) #Hgamma data
    means.append(NIIIopt[4])
    sigmas.append(NIIIopt[5])
    vs.append((NIIIopt[5]*2.355/NIIIopt[4])*c)
    heights_err.append(np.sqrt(NIIIcov[3][3]))
    means_err.append(np.sqrt(NIIIcov[4][4]))
    sigmas_err.append(np.sqrt(NIIIcov[5][5]))
    chi2s.append(NIIIchisq)
         
    heights.append(HBopt[0]) #HeII data
    means.append(HBopt[1])
    sigmas.append(HBopt[2])
    vs.append((HBopt[2]*2.355/HBopt[1])*c)
    heights_err.append(np.sqrt(HBcov[0][0]))
    means_err.append(np.sqrt(HBcov[1][1]))
    sigmas_err.append(np.sqrt(HBcov[2][2]))
    chi2s.append(HBchisq)
    
    heights.append(HBopt[6]) #OIII5007 data
    means.append(HBopt[7])
    sigmas.append(HBopt[8])
    vs.append((HBopt[8]*2.355/HBopt[7])*c)
    heights_err.append(np.sqrt(HBcov[6][6]))
    means_err.append(np.sqrt(HBcov[7][7]))
    sigmas_err.append(np.sqrt(HBcov[8][8]))   
    chi2s.append(HBchisq)

    heights.append(NIIIopt[0])#NIII data
    means.append(NIIIopt[1])
    sigmas.append(NIIIopt[2])
    vs.append((NIIIopt[2]*2.355/NIIIopt[1])*c)
    heights_err.append(np.sqrt(NIIIcov[0][0]))
    means_err.append(np.sqrt(NIIIcov[1][1]))
    sigmas_err.append(np.sqrt(NIIIcov[2][2]))
    chi2s.append(NIIIchisq)
    
    heights.append(Haopt[3]) #SII data
    means.append(Haopt[4])
    sigmas.append(Haopt[5])
    vs.append((Haopt[5]*2.355/Haopt[4])*c)
    heights_err.append(np.sqrt(Hacov[1][1]))
    means_err.append(np.sqrt(Hacov[2][2]))
    sigmas_err.append(np.sqrt(Hacov[3][3]))
    chi2s.append(Hachisq)
    
    heights.append(HBopt[9]) #OIII4959data
    means.append(HBopt[10])
    sigmas.append(HBopt[11])
    vs.append((HBopt[11]*2.355/HBopt[10])*c)
    heights_err.append(np.sqrt(HBcov[9][9]))
    means_err.append(np.sqrt(HBcov[10][10]))
    sigmas_err.append(np.sqrt(HBcov[11][11]))   
    chi2s.append(HBchisq)

    
    
    sigmas = [abs(i) for i in sigmas]
    vs = [abs(i) for i in vs]
    linetable = Table([lines,restwavelengths,heights,heights_err,means,means_err,sigmas,sigmas_err,\
                      vs,chi2s],names = ('Line','Wavelength','Height','e_Height','Mean','e_Mean','Sigma',\
                                   'e_Sigma','Velocity','Chi Square'))
    linetable = linetable.to_pandas()
    return linetable

    
    
    
def TDE_filter(linetable, tflux):
    filter_pass = []
    score = 0
    lines = list(linetable['Line'])
    #flux input should be prior to subtraction of continuum
    blue_end = np.nanmean(flux[1000:3000])
    red_end = np.nanmean(flux[5000:7000])
    
    #Halpha
    i = lines.index('Halpha')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 7 and linetable['Velocity'][i] > 750:
            score += 1
            filter_pass.append('Halpha')
               
    
    #HBeta
    i = lines.index('Hbeta')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 7 and linetable['Velocity'][i] > 500:
            score += 1
            filter_pass.append('Hbeta')
        
    #Hgamma
    i = lines.index('Hgamma')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 7 and linetable['Velocity'][i] > 500:
            score += 1
            filter_pass.append('Hgamma')
    #HeII4686
    i = lines.index('HeII4686')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 7 and linetable['Velocity'][i] > 650:
            score += 1
            filter_pass.append('HeII4686')
    #NIII
    i = lines.index('NIII')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 7 and linetable['Velocity'][i] > 400:
            score += 1
            filter_pass.append('NIII')

    
    #OIII5007
    i = lines.index('OIII5007')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 5 and linetable['Velocity'][i] > 20:
            score -= 1.1
    #OIII4959
    i = lines.index('OIII4959')
    if linetable['Chi Square'][i] < 2 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 5 and linetable['Velocity'][i] > 20:
            score -= 1.1

    #Blueness
    if blue_end/red_end >= 2 and blue_end > 1:
        score += 1
        filter_pass.append('Blue')
    
    return(score, filter_pass)
    
#####
def Hline_filter(linetable):
    filter_pass = []
    score = 0
    lines = list(linetable['Line'])
    #flux input should be prior to subtraction of continuum

    #Halpha
    i = lines.index('Halpha')
    if linetable['Chi Square'][i] < 3 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 15 and linetable['Velocity'][i] > 75:
            score += 1
            filter_pass.append('Halpha')
    
    #HBeta
    i = lines.index('Hbeta')
    if linetable['Chi Square'][i] < 3 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 15 and linetable['Velocity'][i] > 75:
            score += 1
            filter_pass.append('Hbeta')
        
    #Hgamma
    i = lines.index('Hgamma')
    if linetable['Chi Square'][i] < 3 and linetable['Chi Square'][i] > 0.5: # check for decent fit
        if abs(linetable['Wavelength'][i] - linetable['Mean'][i]) < 5 and linetable['e_Height'][i] > 0\
        and linetable['Height'][i]/linetable['e_Height'][i] > 15 and linetable['Velocity'][i] > 75:
            score += 1
            filter_pass.append('Hgamma')
  
    return(score)