#! /usr/bin/python

"""
Calibration with a Watts Up
---------------------------

Requires wattsup UNIX tool available from here:
https://www.wattsupmeters.com/secure/support.php

NEW CALIBRATION TECHNIQUE:
    Plug in a WattsUp
        run ./calibrate.py
    This will update (or create) a config.CALIBRATION_FILENAME file containing 
    the calibration parameters.

OLD CALIBRATION TECHNIQUE:

Log data from Watts Up using
   screen -dmL wattsup ttyUSB0 volts
"""

from __future__ import print_function, division
import snd_card_power_meter.scpm as scpm
from snd_card_power_meter.sampler import Sampler
from snd_card_power_meter.wattsup import WattsUp
import logging
log = logging.getLogger("scpm")

def main():
    scpm.init_logger()
    sampler = Sampler()
    wu = WattsUp()
    
    try:
        sampler.open()
        sampler.start()
        wu.open()        
        scpm.calibrate(sampler.adc_data_queue, wu)
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("")
        wu.terminate()
        sampler.terminate()
        raise
    
    wu.terminate()
    sampler.terminate()

if __name__ == '__main__':
    main()
