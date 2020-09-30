"""
JexoSim 
2.0
Detector module
v1.0

"""

from jexosim.classes.sed import Sed
from jexosim.lib import jexosim_lib 
from jexosim.lib.jexosim_lib import jexosim_msg, jexosim_plot, planck
import numpy           as np
from astropy import units as u
import matplotlib.pyplot as plt
import copy, os
from scipy import interpolate
import sys
import scipy
 


def run(opt):
    
      opt.observation_feasibility = 1  # this variable is currently not changed to zero under any circumstances

#==============================================================================
#     get PSFs  
#==============================================================================

      if os.path.exists('%s/../archive/PSF/%s_psf_stack.npy'%(opt.__path__,opt.channel.instrument.val)):
          psf_stack = np.load('%s/../archive/PSF/%s_psf_stack.npy'%(opt.__path__,opt.channel.instrument.val))
          psf_stack_wl =  1e6*np.load('%s/../archive/PSF/%s_psf_stack_wl.npy'%(opt.__path__,opt.channel.instrument.val))
          psf = interpolate.interp1d(psf_stack_wl, psf_stack, axis=2,bounds_error=False, fill_value=0.0, kind='linear')(opt.x_wav_osr.value)      
          psf = np.rot90(psf) 
          opt.psf_type = 'wfe'
      else: # uses airy if no psf database however this is to be avoided, as pipeline assumes the wfe database psfs.
          psf = jexosim_lib.Psf(opt.x_wav_osr.value, opt.channel.camera.wfno_x.val, opt.channel.camera.wfno_y.val, opt.fp_delta.value, shape='airy')  
          psf[np.isnan(psf)] =0
          opt.psf_type = 'airy'

      opt.psf = psf 

      jexosim_msg("PSF shape %s, %s"%(opt.psf.shape[0],opt.psf.shape[1] ), opt.diagnostics)     
      jexosim_plot('psf check', opt.diagnostics, image=True, image_data = psf[..., int(psf.shape[2]/2)])
    
      sum1=[]
      for i in range(psf.shape[2]):
          sum1.append(psf[...,i].sum())
          if psf[...,i].sum()!=0:
              # psf[...,i] =psf[...,i]/psf[...,i].sum() 
                if np.round(psf[...,i].sum(),3) !=1.0:    
                    jexosim_msg('error... check PSF normalisation %s %s'%(psf[...,i].sum(), opt.x_wav_osr[i]), 1)
                    sys.exit()
                  
      jexosim_plot('test7 - psf sum vs subpixel position (should be 1)', opt.diagnostics, 
                   xdata=opt.x_pix_osr, ydata = sum1, marker='bo')
    
#==============================================================================    
      # Populate focal plane with monochromatic PSFs
#============================================================================== 
      j0 = np.arange(opt.fp.shape[1]) - int(opt.psf.shape[1]/2)
      j1 = j0 + opt.psf.shape[1]
      idx = np.where((j0>=0) & (j1 < opt.fp.shape[1]))[0]
      i0 = np.array([opt.fp.shape[0]/2 - psf.shape[0]/2 + opt.offs]*len(j1)).astype(np.int)     
      i0+=1     
      
      # variable y position (applies only to NIRISS)
      if opt.y_pos_osr != []:
          opt.y_pos_osr = np.where(opt.y_pos_osr<0,0, opt.y_pos_osr).astype(np.int) +opt.fp.shape[0]/2 -opt.psf.shape[0]/2 + opt.offs 
          i0 = (opt.y_pos_osr).astype(np.int)
          
      i1 = i0 + psf.shape[0]
      
      # SPECIAL CASE: fix if airy psfs used     
      if opt.channel.name == 'NIRISS_SOSS_GR700XD':
          # fix if airy psfs used
          if opt.psf_type == 'airy':
              original_fp = copy.deepcopy(opt.fp)
              if i1.max() > opt.fp.shape[0]: #psfs will fall outside fp area due to curve
                  original_fp = copy.deepcopy(opt.fp)
                  opt.fp = np.zeros((i1.max(), opt.fp.shape[1] ))  # temp increase in fp size           
    
      FPCOPY = copy.deepcopy(opt.fp)
      opt.fp_signal = copy.deepcopy(opt.fp)  
      
     
      for k in idx:
          FPCOPY[i0[k]:i1[k], j0[k]:j1[k]] += opt.psf[...,k] * opt.star.sed.sed[k].value    
      if opt.background.EnableSource.val == 1 or opt.background.EnableAll.val == 1:
          for k in idx: 
              opt.fp[i0[k]:i1[k], j0[k]:j1[k]] += psf[...,k] * opt.star.sed.sed[k].value          
      for k in idx: 
              opt.fp_signal[i0[k]:i1[k], j0[k]:j1[k]] += psf[...,k] * opt.star.sed.sed[k].value                
       
      # SPECIAL CASE: fix if airy psfs used      
      if opt.channel.name == 'NIRISS_SOSS_GR700XD': 
          if opt.psf_type == 'airy':  # now return fp to original size
              if i1.max() > original_fp.shape[0]: 
                  diff = i1.max()- original_fp.shape[0]         
                  FPCOPY = FPCOPY[diff:]
                  opt.fp = opt.fp[diff:]
                  opt.fp_signal = opt.fp_signal[diff:]
         
      opt.pre_convolved_fp = copy.deepcopy(opt.fp)
      
#==============================================================================
#     Now deal with the planet
#==============================================================================
      if opt.channel.name == 'NIRISS_SOSS_GR700XD':  # Niriss curved spectrum means code below will not work
          opt.planet.sed =  Sed(opt.x_wav_osr, opt.planet_sed_original)
      else:              
          i0p = np.unravel_index(np.argmax(opt.psf.sum(axis=2)), opt.psf[...,0].shape)[0]
          planet_response = np.zeros((opt.fp.shape[1]))         
          for k in idx: 
              planet_response[j0[k]:j1[k]] += psf[i0p,:,k] * opt.planet.sed.sed[k].value          
          pl_sed = np.zeros((opt.fp.shape[1]))
          for i in range (len(planet_response)): 
               pl_sed[i] = planet_response[i]/(1e-30+ opt.fp[:,i][(i0[i]+i1[i])//2])                   
          opt.planet.sed =  Sed(opt.x_wav_osr, pl_sed*u.dimensionless_unscaled)
                
      jexosim_plot('planet sed 1', opt.diagnostics, 
                   xdata=opt.planet.sed.wl, ydata = opt.planet.sed.sed, 
                   ylim=[0,1])

# alternate code that does not rely on multiplying by the star.sed first- not sure if this works correctly yet.    
#          planet_fp = copy.deepcopy(opt.fp)*0
#          i0 = np.array([opt.fp.shape[0]/2 - psf.shape[0]/2 + opt.offs]*len(j1))
#          i1 = i0 + psf.shape[0]
#          
#          for k in idx: 
#              planet_fp[i0[k]:i1[k], j0[k]:j1[k]] += psf[...,k] * opt.planet_sed_original[k] 
#
#  
#          planet_response = planet_fp.sum(axis=0)
#          plt.figure('planet sed 111')
#          plt.plot(opt.planet.sed.wl, planet_response)
#          
#          plt.figure('test')
#          plt.imshow(planet_fp)
          
#==============================================================================
#     Allocate pixel response function and convolve with focal plane
#==============================================================================
      kernel, kernel_delta = jexosim_lib.PixelResponseFunction(opt, 
        opt.psf.shape[0:2],
        7*opt.channel.simulation_factors.osf(),   
        opt.channel.detector_pixel.pixel_size(),
        lx = opt.channel.detector_pixel.pixel_diffusion_length())

      jexosim_msg ("kernel sum %s"%(kernel.sum()), opt.diagnostics) 
      jexosim_msg ("check 3.9 - unconvolved FP max %s"%(opt.fp.max()) , opt.diagnostics)      
      jexosim_plot('test3', opt.diagnostics, 
                   xdata=opt.x_wav_osr, ydata = opt.fp.sum(axis=0), marker='bo')
      jexosim_plot('test4', opt.diagnostics, 
                   xdata=opt.x_pix_osr, ydata = opt.x_wav_osr, marker='bo')                  
      jexosim_plot('test5', opt.diagnostics, 
                   xdata=opt.x_pix_osr, ydata = opt.fp.sum(axis=0), marker='bo')
      jexosim_plot('test6', opt.diagnostics, 
                   xdata=opt.x_wav_osr, ydata = opt.star.sed.sed, marker='bo') 
      
      opt.fp = jexosim_lib.fast_convolution(opt.fp, opt.fp_delta, kernel, kernel_delta)
      FPCOPY = jexosim_lib.fast_convolution(FPCOPY, opt.fp_delta, kernel, kernel_delta)       
      opt.fp_signal = jexosim_lib.fast_convolution(opt.fp_signal, opt.fp_delta, kernel, kernel_delta)

      jexosim_msg ("check 4 - convolved FP max %s %s"%(opt.fp.max(), FPCOPY[1::3,1::3].max()) , opt.diagnostics)    #FPCOPY0 = exolib.fast_convolution(FPCOPY[1::3,1::3], 18e-6*pq.m, kernel, kernel_delta)    

      opt.kernel = kernel
      opt.kernel_delta = kernel_delta
      
      # Fix units
      opt.fp = opt.fp*opt.star.sed.sed.unit  
      opt.fp_signal = opt.fp_signal*opt.star.sed.sed.unit  

#==============================================================================
#     Find saturation time
#==============================================================================
    ## Find count rate with diffuse radiation 
      FPCOPY += opt.zodi.sed.value   + opt.emission.sed.value  
      FPCOUNT = FPCOPY[1::3,1::3] + opt.channel.detector_pixel.Idc.val.value    
      FPCOUNT = FPCOUNT*u.electron/u.s 
      opt.FPCOUNT = FPCOUNT
    
      jexosim_msg ("check 5 - %s"%(FPCOUNT.max()), opt.diagnostics)

      FW = opt.channel.detector_pixel.full_well.val*u.electron   
      A,B = np.unravel_index(FPCOUNT.argmax(), FPCOUNT.shape)
      jexosim_msg ("maximum index and count with all backgrounds %s %s %s"%(A,B, FPCOUNT.max()), opt.diagnostics)
      A,B = np.unravel_index(opt.fp_signal[1::3,1::3].argmax(), opt.fp_signal[1::3,1::3].shape)
      jexosim_msg ("maximum index and count with no backgrounds %s %s %s"%(A,B, opt.fp_signal[1::3,1::3].max()), opt.diagnostics)
      jexosim_msg ("full well %s"%(FW), opt.diagnostics)   
      jexosim_msg ("full cycle time based on 100 percent saturation %s"%((FW / FPCOUNT.max())), opt.diagnostics)     
      jexosim_msg ("maximum full well percentage set to: %s"%(opt.observation.obs_fw_percent.val), opt.diagnostics)
      
      opt.sat_time = ((FW / FPCOUNT.max()).value *opt.observation.obs_fw_percent.val/100.0 )*u.s
      opt.sat_limit = FW*opt.observation.obs_fw_percent.val/100.0  
      opt.sat_limit_fw = FW
        
      jexosim_msg ("saturation time adjusted for maximum full well percentage %s"%(opt.sat_time), opt.diagnostics)     
      jexosim_msg ("saturation time with no backgrounds or dc %s"%( (FW/(opt.fp_signal[1::3,1::3].max()))*opt.observation.obs_fw_percent.val/100.0), opt.diagnostics)

#==============================================================================
#      Pick a subarray and find n_groups, t_f, t_g, dead_time
#==============================================================================  
      if opt.observation.obs_auto_subarray.val == 1:
          opt = optimal_subarray(opt)
          jexosim_msg('Picking optimal subarray', opt.diagnostics)    
      else:
          opt = user_subarray(opt)
          jexosim_msg('Using user-defined subarray', opt.diagnostics)              
      
      if opt.observation.obs_use_sat.val == 1: 
          jexosim_msg('Using saturation time to set n_groups', opt.diagnostics)
          n_groups = int(opt.sat_time/opt.t_g) # does not include reset group (assume this is after final read so saturation in this period does not affect read counts)
          if n_groups <2:
              n_groups=2
      else:
          jexosim_msg('Using user-defined n_groups', opt.diagnostics)
          n_groups = opt.observation.obs_n_groups.val
          
      jexosim_msg('Subarray used %s'%(opt.subarray), opt.diagnostics)
      jexosim_msg('Readout pattern used %s'%(opt.pattern), opt.diagnostics)
      jexosim_msg('t_f %s'%(opt.t_f), opt.diagnostics)
      jexosim_msg('t_g %s'%(opt.t_g), opt.diagnostics)
      jexosim_msg('dead time %s'%(opt.dead_time), opt.diagnostics)
      jexosim_msg('zero time %s'%(opt.zero_time), opt.diagnostics)
      jexosim_msg('n_groups %s'%(n_groups), opt.diagnostics)        
      
      # t_sim is not currently used, and by default is set to the same value as t_f
      opt.t_sim = opt.simulation.sim_t_sim.val*opt.t_f             
      opt.t_int =  (n_groups-1)*opt.t_g   
      opt.t_cycle = n_groups*opt.t_g+ opt.dead_time
        
      if n_groups*opt.t_g > opt.sat_time:
          jexosim_msg ("Warning: some pixels will exceed saturation limit", opt.diagnostics  )
          opt.sat_flag = 1
      else:
          jexosim_msg ("Cycle time within saturation time", opt.diagnostics  )
          opt.sat_flag = 0
#==============================================================================
# 10.  Crop array to subarray
#==============================================================================
      if opt.fp_y == opt.fpn[0] and  opt.fp_x == opt.fpn[1]:         
            pass
      else: # set new subaary size for FPA
         opt =  crop_to_subarray(opt)         
#==============================================================================
# 10.  Set effective multiaccum
#==============================================================================
      if opt.simulation.sim_full_ramps.val == 0:
          jexosim_msg ("Approximating ramps with corrected CDS method, so only 2 NDRs simulated", 1)
          opt.effective_multiaccum = 2 # effective multiaccum is what is implemented in sim
          opt.projected_multiaccum = n_groups
      else:
          opt.effective_multiaccum = n_groups
          opt.projected_multiaccum = n_groups
          
      jexosim_msg ("projected multiaccum: %s"%(opt.projected_multiaccum), opt.diagnostics)
      jexosim_msg ("effective multiaccum: %s"%(opt.effective_multiaccum), opt.diagnostics)
                                  
      opt.exposure_time = (opt.t_int + opt.dead_time + opt.zero_time) #same as t_cycle
      
      jexosim_msg ("Integration time - zeroth read %s"%(opt.t_int), opt.diagnostics)  
      jexosim_msg ("Estimated integration time incl. zeroth read %s"%(opt.t_int  + opt.zero_time), opt.diagnostics)
      jexosim_msg ("Estimated TOTAL CYCLE TIME %s"%(opt.exposure_time), opt.diagnostics)
           
      jexosim_msg ("CDS time estimate %s"%(opt.t_int), opt.diagnostics)  
        
      jexosim_msg ("FP max %s"%(opt.fp[1::3,1::3].max()), opt.diagnostics)
      jexosim_msg ("DC SWITCH.......%s"%(opt.background.EnableDC.val), opt.diagnostics)
      jexosim_msg ("DISABLE ALL SWITCH.......%s"%(opt.background.DisableAll.val), opt.diagnostics)   
      jexosim_msg ("DARK CURRENT %s"%(opt.channel.detector_pixel.Idc.val) , opt.diagnostics)
  
      jexosim_plot('focal plane check', opt.diagnostics, image=True, 
                  image_data=opt.fp_signal[1::3,1::3], aspect='auto', interpolation = None,
                  xlabel = 'x \'spectral\' pixel', ylabel = 'y \'spatial\' pixel')
      if opt.diagnostics ==1:
          plt.figure('focal plane check')
          cbar = plt.colorbar()
          cbar.set_label(('Count (e$^-$/s)'), rotation=270, size=15,labelpad=20)
          cbar.ax.tick_params(labelsize=15) 
          ax = plt.gca()
          for item in ([ax.title, ax.xaxis.label, ax.yaxis.label] +
                 ax.get_xticklabels() + ax.get_yticklabels()):
              item.set_fontsize(15)

      if opt.noise.ApplyRandomPRNU.val == 1:
          opt.qe = np.random.normal(1, 0.01*opt.noise.sim_prnu_rms.val, opt.fp[1::3,1::3].shape) # for random uncertainty
          opt.qe_uncert = np.random.normal(1, 0.01*opt.noise.sim_flat_field_uncert.val, opt.fp[1::3,1::3].shape) # for random uncertainty  
          jexosim_msg ("RANDOM PRNU GRID SELECTED...",  opt.diagnostics)
      else:
          opt.qe = np.load('%s/data/JWST/PRNU/qe_rms.npy'%(opt.__path__))[0:opt.fp[1::3,1::3].shape[0],0:opt.fp[1::3,1::3].shape[1]]
          opt.qe_uncert = np.load('%s/data/JWST/PRNU/qe_uncert.npy'%(opt.__path__))[0:opt.fp[1::3,1::3].shape[0],0:opt.fp[1::3,1::3].shape[1]]      
          jexosim_msg ("PRNU GRID SELECTED FROM FILE...", opt.diagnostics)
         
      opt.fp_original = copy.deepcopy(opt.fp)
      opt.fp_signal_original = copy.deepcopy(opt.fp_signal)  
      opt.x_wav_osr_original = copy.deepcopy(opt.x_wav_osr)
      opt.x_pix_osr_original = copy.deepcopy(opt.x_pix_osr)  
      
      opt.zodi_sed_original = copy.deepcopy(opt.zodi.sed) # needed here due to possible cropping above for subarrays
      opt.emission_sed_original = copy.deepcopy(opt.emission.sed)
      opt.qe_original = copy.deepcopy(opt.qe)
      opt.qe_uncert_original = copy.deepcopy(opt.qe_uncert)
       
      if opt.channel.instrument.val =='NIRSpec':
         opt.channel.pipeline_params.wavrange_hi.val = opt.gap[3]
         opt.channel.pipeline_params.wavrange_lo.val = opt.gap[2]
         opt.channel.pipeline_params.end_wav.val = opt.gap[3]+0.1
         opt.channel.pipeline_params.start_wav.val = opt.gap[2]-0.1
  
      jexosim_plot('final wl solution on subarray', opt.diagnostics,
                   ydata=opt.x_wav_osr[1::3],
                   xlabel = 'x \'spectral\' pixel', ylabel = 'y \'spatial\' pixel',
                   grid=True)
             
      sanity_check(opt)
      
      return opt
# =============================================================================
#       
# =============================================================================
      
def sanity_check(opt):
    import scipy.constants as spc
    
    wl = opt.x_wav_osr[1::3]
    del_wl = abs(np.gradient(wl))
#    del_wl = opt.d_x_wav_osr[1::3]*3
    star_spec = opt.star_sed
    star_spec.rebin(wl)
    T = opt.planet.planet.star.T
    trans_sed = opt.total_transmission.sed*u.dimensionless_unscaled
    trans = Sed(opt.total_transmission.wl,trans_sed)
    trans.rebin(wl)
    QE = opt.qe_spec
    QE.rebin(wl)
    Rs = (opt.planet.planet.star.R).to(u.m)
    D = (opt.planet.planet.star.d).to(u.m)
    n= trans.sed*del_wl*np.pi*planck(wl,T)*(Rs/D)**2*opt.Aeff*QE.sed/(spc.h*spc.c/(wl*1e-6))

    n2= trans.sed*del_wl*star_spec.sed*opt.Aeff*QE.sed/(spc.h*spc.c/(wl*1e-6))
    
    jex_sig = opt.fp_signal[1::3,1::3].sum(axis=0)
    
    R = opt.pipeline.pipeline_R.val
    del_wav = wl/R
    opt.exp_sig  = opt.t_int*del_wav*jex_sig/del_wl
    
    if opt.diagnostics ==1:
        plt.figure('sanity check 1 - check focal plane signal')
        plt.plot(wl,n, 'bo', label='BB check')
        plt.plot(wl,n2, 'ro', label='Phoenix check')  # not convolved with PSF unlike JexoSim, so peak may be higher
        plt.plot(wl, jex_sig, 'gx', label='JexoSim')
        plt.ylabel('e/s/pixel col'); plt.xlabel('pixel col wavelength (microns)')
        plt.legend(loc='best')
        
        plt.figure('sanity check 2 - expected final star signal in R bin of %s'%((R)))
        plt.plot(wl, opt.exp_sig)
        plt.ylabel('e/bin'); plt.xlabel('Wavelength (microns)')
            
        plt.figure('sanity check 3 - expected photon noise (sd) in R bin of %s'%((R)))
        plt.plot(wl, opt.exp_sig**0.5)    
        plt.ylabel('e/bin'); plt.xlabel('Wavelength (microns)')  
       

def user_subarray(opt):
    
    s = (opt.observation.obs_user_subarray.val).replace(" ", "")
    start = 0
    idx=[]
    for i in range(3):
         idx0 = s.find('+', start)
         idx.append(idx0)
         start =idx0+1
    opt.subarray = s[idx[1]+1:idx[2]]
    opt.pattern = s[idx[2]+1:]

    idx1 = np.argwhere(np.array(opt.channel.detector_array.subarray_list.val) == opt.subarray)[0].item()
    idx2 = np.argwhere(np.array(opt.channel.detector_readout.pattern_list.val) == opt.pattern)[0].item()
    opt.nframes = opt.channel.detector_readout.pattern_params_list.val[idx2][0]
    opt.nskip = opt.channel.detector_readout.pattern_params_list.val[idx2][1]
    opt.fp_x = opt.channel.detector_array.subarray_geometry_list.val[idx1][1]
    opt.fp_y = opt.channel.detector_array.subarray_geometry_list.val[idx1][0]
    opt.t_f = opt.channel.detector_array.subarray_t_f_list.val[idx1]

    opt.t_g = (opt.nframes+opt.nskip)*opt.t_f 
    opt.dead_time = (opt.channel.detector_readout.nGND.val+ opt.channel.detector_readout.nRST.val)* opt.t_g
    opt.zero_time = opt.channel.detector_readout.nNDR0.val* opt.t_g
    
    if opt.channel.instrument.val =='NIRSpec': 
            opt.gap = opt.channel.detector_array.subarray_gap_list.val[idx1] 

    return opt
 
    
def optimal_subarray(opt):
    
    jexosim_msg ("Selecting optimal subarray...", 1) #assuming m=1 in all cases 
    SNR_list=[];subarray_list = []; pattern_list=[]; t_diff_list=[]
    dead_time_list=[]; zero_time_list=[]; t_f_list=[]; t_g_list=[]
    fp_x_list=[]; fp_y_list=[]
    nframes_list=[]; nskip_list=[]
    n_list=[]; gap_list=[]
        
    for i in range(len(opt.channel.detector_array.subarray_list.val)):
        
        for j in range(len(opt.channel.detector_readout.pattern_list.val)):
            
            subarray = opt.channel.detector_array.subarray_list.val[i]    
            fp_x = opt.channel.detector_array.subarray_geometry_list.val[i][1]  
            fp_y = opt.channel.detector_array.subarray_geometry_list.val[i][0]                                  
            t_f = opt.channel.detector_array.subarray_t_f_list.val[i]
            pattern = opt.channel.detector_readout.pattern_list.val[j]
            nframes = opt.channel.detector_readout.pattern_params_list.val[j][0]
            nskip = opt.channel.detector_readout.pattern_params_list.val[j][1]
            t_g = (nframes+nskip)*t_f
            dead_time = (opt.channel.detector_readout.nGND.val+ opt.channel.detector_readout.nRST.val)* t_g
            zero_time = opt.channel.detector_readout.nNDR0.val* t_g

            if opt.observation.obs_use_sat.val == 1:            
             
                n_groups =  int(opt.sat_time/t_g) # does not include reset group
  
                if n_groups < 2: # must have at least 2 groups; thus might breach sat time
                      n_groups = 2

            elif opt.observation.obs_use_sat.val == 0:
                
                n_groups = opt.observation.obs_n_groups.val
                
            t_cycle = n_groups*t_g + dead_time
            t_diff = (n_groups*t_g)-opt.sat_time                         
            
            if t_diff >0 : #i.e. saturation occurs 
                SNR_list.append(0) # exclude from SNR basis
            else:
                t_int =  (n_groups-1)*t_f  
                f = opt.FPCOUNT.value.max()  # max count rate on detector (includes dc and backgrounds)     
                # see Rauschser and Fox 2007
                RN_var = 12.*(n_groups-1)*(opt.channel.detector_pixel.sigma_ro.val)**2 /(n_groups*(n_groups+1))
                PN_var = ((6.*(n_groups**2+1)/(5*n_groups*(n_groups+1))) * t_int * f).value
                TN= np.sqrt(RN_var+PN_var) #total noise
                S = (t_int * f).value  # total signal (assumes first frame count is subtracted)
                SNR = S/TN
                SNR_list.append(SNR)
                
            subarray_list.append(subarray)
            pattern_list.append(pattern) 
            t_diff_list.append(t_diff.value)
            dead_time_list.append(dead_time); zero_time_list.append(zero_time)
            t_f_list.append(t_f); t_g_list.append(t_g)
            fp_x_list.append(fp_x); fp_y_list.append(fp_y)
            nframes_list.append(nframes); nskip_list.append(nskip)
            n_list.append(n_groups)
            
            if opt.channel.instrument.val =='NIRSpec': 
                gap = opt.channel.detector_array.subarray_gap_list.val[i]
                gap_list.append(gap)            
    
    jexosim_msg(subarray_list, opt.diagnostics)  
    jexosim_msg(t_diff_list, opt.diagnostics) 
    jexosim_msg(SNR_list, opt.diagnostics) 
    if np.max(SNR_list) ==0: #all saturate, pick one closest to sat time
        jexosim_msg ("All subarrays saturate - picking subarray closest to saturation time", 1)
        # All subarrays will saturate: pick one closest to sat time
        idx = np.argmin(np.array(t_diff_list))
    else:
        # At least one subarray does not saturate, pick the one with highest SNR                        
        idx = np.argmax(np.array(SNR_list))
          
    opt.subarray = subarray_list[idx]
    opt.pattern = pattern_list[idx]
    opt.t_f = t_f_list[idx]
    opt.t_g = t_g_list[idx]
    opt.dead_time = dead_time_list[idx]
    opt.zero_time = zero_time_list[idx]
    opt.n_groups = n_list[idx]
    opt.nframes = nframes_list[idx]
    opt.nskip = nskip_list[idx]
    opt.fp_x = fp_x_list[idx]
    opt.fp_y = fp_y_list[idx]

    if opt.channel.instrument.val =='NIRSpec': 
        opt.gap = gap_list[idx]
        
   
    return opt
   
def crop_to_subarray(opt):

    opt.fpn[0] = opt.fp_y*u.dimensionless_unscaled
    opt.fpn[1] = opt.fp_x*u.dimensionless_unscaled
            
    ycrop = int(((opt.fp_signal.shape[0]-opt.fpn[0]*3)/2).value)
    ycrop0 = -int(((opt.fp_signal.shape[0]-opt.fpn[0]*3)/2).value)
                              
    xcrop = int(((opt.fp_signal.shape[1]-opt.fpn[1]*3)/2).value)
    xcrop0 = -int(((opt.fp_signal.shape[1]-opt.fpn[1]*3)/2).value)
    
    if opt.fpn[0] == opt.fp_signal.shape[0]/3:
        ycrop=0; ycrop0=None
  
    if opt.fpn[1] == opt.fp_signal.shape[1]/3:
        xcrop=0; xcrop0=None 
 
    cond=0    
    # special case for NIRSpec subarrays
    if opt.channel.instrument.val =='NIRSpec':
        #wavelength solutions centered at division of subarrays to give right wavelength in each subarray    
        if opt.channel.name != 'NIRSpec_BOTS_G140H_F100LP' \
            and opt.channel.name != 'NIRSpec_BOTS_G395H_F290LP'  and opt.channel.name != 'NIRSpec_BOTS_G235H_F170LP' :
            #just use one detector
            if opt.subarray == 'SUB1024B':
                xcrop =1024*3
                xcrop0=None
            if opt.subarray == 'SUB1024A':
                xcrop =0
                xcrop0 =-1024*3
            if opt.subarray == 'SUB512' or opt.subarray == 'SUB512S':
                xcrop =1024*3
                xcrop0 =-512*3
        else:  # H modes start off with large array 4500 in x which we crop down      
            # idx = np.argwhere((opt.x_wav_osr[1::3].value>=opt.gap[0]) & (opt.x_wav_osr[1::3].value<=opt.gap[1]))
            # jexosim_msg('gap width in whole pixels: %s'%(len(idx)), opt.diagnostics)
      
            # if opt.subarray == 'SUB2048':
            #     xcrop= 0
            #     xcrop0 = 4096*3+len(idx)*3
                
            # if opt.subarray == 'SUB1024A':
            #     xcrop=0
            #     xcrop0= 2048*3+len(idx)*3
            
            # if opt.subarray == 'SUB1024B':    
            #     xcrop= 1024*3
            #     xcrop0 = 1024*3+ 2048*3+len(idx)*3
            # if opt.subarray == 'SUB512' or opt.subarray == 'SUB512S':    
            #     xcrop= 1024*3
            #     xcrop0 = 1024*3+ 512*3  +len(idx)*3 + 512*3
                
            # idx = np.argwhere((opt.x_wav_osr[1::3].value>=opt.gap[0]) & (opt.x_wav_osr[1::3].value<=opt.gap[1]))
            # jexosim_msg('gap width in whole pixels: %s'%(len(idx)), opt.diagnostics)
            gap = 172 # tried 157 based on 2048 subarrays and plotting the published gaps using above line, but with G2H a little short on NRS2; 172 seems to work best to obtain the gap values across all grisms that match the published values
      
            if opt.subarray == 'SUB2048':
                xcrop= 0
                xcrop0 = 4096*3+gap*3
                gap_idx0 = 2048
                opt.gap_len = gap
                
            if opt.subarray == 'SUB1024A':
                xcrop=0
                xcrop0= 2048*3+ 2048*3 + gap*3
                gap_idx0 = 1024
                opt.gap_len = 1024*2 +gap               
            
            if opt.subarray == 'SUB1024B':    
                xcrop= 1024*3
                xcrop0 = xcrop + 2048*3+ gap*3
                gap_idx0 = 1024
                opt.gap_len = gap          
                
            if opt.subarray == 'SUB512' or opt.subarray == 'SUB512S':    
                xcrop= 1024*3
                xcrop0 = xcrop + 2*512*3  +gap*3 + 2*512*3
                gap_idx0 = 512
                opt.gap_len = 512*2 + gap #length of gap in pix
                
            wav = opt.x_wav_osr[xcrop:xcrop0]
            wav = wav[1::3]
            opt.wav_gap_start = wav[gap_idx0] # first wavelength in gap - use to identify start of gap in noise after cropping
            opt.wav_gap_end = wav[gap_idx0+opt.gap_len] # first wavelength in gap - use to identify start of gap in noise after cropping
 
            cond=1
    
    # special case for NIRISS substrip 96
    if opt.subarray =='SUBSTRIP96' and opt.channel.instrument.val =='NIRISS':
          if opt.psf_type != 'airy': # should not really use airy however - potential problem in data reduction as designed for wfe psf.
              ycrop = 360; ycrop0= -120 
              xcrop =0
              xcrop0 = None
              
    # if ycrop > 0 or ycrop0 >0: 
    opt.fp_signal = opt.fp_signal[ycrop:ycrop0] # crop the oversampled FP array to 96 x 3 in y axis
    opt.fp = opt.fp[ycrop:ycrop0]
       
    opt.fp_signal = opt.fp_signal[:,xcrop:xcrop0] # crop the oversampled FP array to 96 x 3 in y axis
    opt.fp = opt.fp[:,xcrop:xcrop0]
    opt.x_wav_osr = opt.x_wav_osr[xcrop:xcrop0]
    opt.d_x_wav_osr = opt.d_x_wav_osr[xcrop:xcrop0]
    opt.x_pix_osr = opt.x_pix_osr[xcrop:xcrop0]
    opt.zodi.sed = opt.zodi.sed[xcrop:xcrop0]
    opt.emission.sed = opt.emission.sed[xcrop:xcrop0]
    opt.zodi.wl = opt.x_wav_osr
    opt.emission.wl = opt.x_wav_osr
    opt.planet.sed.sed =opt.planet.sed.sed[xcrop:xcrop0]                  
    opt.planet.sed.wl = opt.x_wav_osr
    
    if cond==1: #fix for resized NIRSpec Hi-res arrays with gaps
        opt.fpn[0] = opt.fp_signal.shape[0]/3 
        opt.fpn[1] = opt.fp_signal.shape[1]/3  
    print     (opt.fp_signal.shape[1]/3, opt.fpn[1] )   
    if opt.fp_signal.shape[0]/3 != opt.fpn[0]:
        jexosim_msg('Error: detector 1 - check code', 1)
        sys.exit()
    if opt.fp_signal.shape[1]/3 != opt.fpn[1]: 
        jexosim_msg('Error: detector 2 - check code', 1)
        sys.exit()
    jexosim_msg ("subarray dimensions %s x %s "%(opt.fpn[0], opt.fpn[1]), 1)
    
    return opt
        
