#! /usr/bin/python

from __future__ import print_function, division
import snd_card_power_meter.scpm as scpm
from snd_card_power_meter.sampler import Sampler

def main():
    calibration = scpm.load_calibration_file()
    sampler = Sampler()
    sampler.open()
    sampler.start()
    adc_data = sampler.adc_data_queue.get()
    sampler.terminate()
    
    split_adc_data = scpm.split_channels(adc_data.data)
    voltage, current = scpm.convert_adc_to_numpy_float(split_adc_data)
    scpm.plot(voltage, current, calibration)

if __name__ == '__main__':
    main()