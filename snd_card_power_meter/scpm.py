#! /usr/bin/python

""" 
THIS CODE IS JUST ME LEARNING TO USE ALSAAUDIO.
IT DOESN'T YET DO ANY POWER MEASUREMENT STUFF! 

Requirements
------------

  Ubuntu packages
     sudo apt-get install python-dev python-pip alsa alsa-tools libasound2-dev

  pyalsaaudio
     * Install on Linux using "sudo pip install pyalsaaudio"
                           or "sudo easy_install pyalsaaudio".

  On Linux, add yourself to the audio users:
     sudo adduser USERNAME audio
     (then log out and log back in for this change to take effect)
  
Calibration with a Watts Up
---------------------------

NEW CALIBRATION TECHNIQUE:
    Plug in a WattsUp
        run ./scpm --calibrate
    This will update (or create) a config.cfg file with the calibration
    parameters.

OLD CALIBRATION TECHNIQUE:

Log data from Watts Up using
   screen -dmL ./wattsup ttyUSB0 volts
  
"""

from __future__ import print_function, division
import numpy as np
import pyaudio # docs: http://people.csail.mit.edu/hubert/pyaudio/
import wave
import subprocess
import sys
import argparse
import audioop # docs: http://docs.python.org/2/library/audioop.html
import time
import wattsup
import collections
import os
import ConfigParser # docs: http://docs.python.org/2/library/configparser.html
from threading import Thread

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty # python 3.x

# Load configuration file
CONFIG_FILE = os.path.dirname(__file__) + "/../config.cfg"
config = ConfigParser.RawConfigParser()
config.read(CONFIG_FILE)
try:
    config.add_section("Calibration")
except ConfigParser.DuplicateSectionError:
    pass


CHUNK = 1024
FORMAT = pyaudio.paInt32
CHANNELS = 2
RATE = 96000
RECORD_SECONDS = 1

VOLTS_PER_ADC_STEP = config.getfloat("Calibration", "volts_per_adc_step")
AMPS_PER_ADC_STEP = config.getfloat("Calibration", "amps_per_adc_step")
if VOLTS_PER_ADC_STEP and AMPS_PER_ADC_STEP:
    WATTS_PER_ADC_STEP = VOLTS_PER_ADC_STEP * AMPS_PER_ADC_STEP

p = pyaudio.PyAudio()
audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                      input=True, frames_per_buffer=CHUNK)


# Named tuple for storing voltage and current
VA = collections.namedtuple('VA', ['time', 'voltage', 'current'])

def run_command(cmd):
    """Run a UNIX shell command.
    
    Args:
        cmd (list of strings)
    """
    try:
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        p.wait()
    except Exception, e:
        print("ERROR: Failed to run '{}'".format(" ".join(cmd)), file=sys.stderr)
        print("ERROR:", str(e), file=sys.stderr)
    else:
        if p.returncode == 0:
            print("Successfully ran '{}'".format(" ".join(cmd)))
        else:
            print("ERROR: Failed to run '{}'".format(" ".join(cmd)), file=sys.stderr)
            print(p.stderr.read(), file=sys.stderr)


def config_mixer():
    print("Configuring mixer...")
    run_command(["amixer", "sset", "Input Source", "Rear Mic"])
    run_command(["amixer", "set", "Digital", "60", "capture"])
    run_command(["amixer", "set", "Capture", "16", "capture"])
    

def get_adc_data():
    """
    Get data from the sound card's analogue to digital converter (ADC).
    
    Returns:
        A named tuple with fields:
        - t (float): UNIX timestamp immediately prior to sampling
        - voltage (binary string): raw ADC data 
        - current (binary string): see 'voltage'
    """
    t = time.time()
    frames = []
    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        try:
            data = audio_stream.read(CHUNK)
        except IOError, e:
            print("ERROR: ", str(e), file=sys.stderr)
            # TODO: should we do i-=1 ?
        else:
            frames.append(data)

    stereo = b''.join(frames)
    width = p.get_sample_size(FORMAT)
    voltage = audioop.tomono(stereo, width, 1, 0)
    current = audioop.tomono(stereo, width, 0, 1)
    return VA(t, voltage, current)


def enqueue_adc_data(adc_data_queue):
    """This will be run as a separate thread""" 
    while True:
        adc_data_queue.put(get_adc_data())


def convert_adc_to_numpy_float(adc_data):
    # Convert from binary string to numpy array
    voltage = np.fromstring(adc_data.voltage, dtype='int32')
    current = np.fromstring(adc_data.current, dtype='int32')
    
    # Cast to floating point so the multiplications below work correctly
    voltage = np.array(voltage, dtype='float')
    current = np.array(current, dtype='float')
    
    return voltage, current    


def record_data(adc_data_queue):
    adc_data = adc_data_queue.get()
    voltage, current = convert_adc_to_numpy_float(adc_data)
    
    inst_power = voltage * current # instantaneous power
    real_power = inst_power.mean() * WATTS_PER_ADC_STEP
    
    v_rms = audioop.rms(adc_data.voltage, p.get_sample_size(FORMAT))
    i_rms = audioop.rms(adc_data.current, p.get_sample_size(FORMAT))
    apparent_power = v_rms * i_rms * WATTS_PER_ADC_STEP
    
    power_factor = real_power / apparent_power
    
    # TODO: leading / lagging phase
    
    print("real power = {:4.2f}W, apparent_power = {:4.2f}VA, "
          "power factor = {:1.3f}, v_rms = {:4.2f}V, i_rms = {:4.2f}A"
          .format(real_power, apparent_power, power_factor,
                  v_rms * VOLTS_PER_ADC_STEP, i_rms * AMPS_PER_ADC_STEP))


def plot(adc_data_queue):
    import matplotlib.pyplot as plt
    
    adc_data = adc_data_queue.get()
    voltage, current = convert_adc_to_numpy_float(adc_data)
    
    if VOLTS_PER_ADC_STEP:
        print("VOLS_PER_ADC_STEP =", VOLTS_PER_ADC_STEP)        
        v_unit = "v"
        voltage *= VOLTS_PER_ADC_STEP
    else:
        v_unit = "ADC steps"
        
    if AMPS_PER_ADC_STEP:
        print("AMPS_PER_ADC_STEP =", AMPS_PER_ADC_STEP)
        i_unit = "A"
        current *= AMPS_PER_ADC_STEP
    else:
        i_unit = "ADC steps"
        
    print("VOLTAGE: mean = {:3.3f}{:s}, rms = {:3.3f}{:s}"
          .format(voltage.mean(), v_unit,
                  audioop.rms(adc_data.voltage, p.get_sample_size(FORMAT)) 
                              * VOLTS_PER_ADC_STEP, v_unit))

    print("CURRENT: mean = {:3.3f}{:s}, rms = {:3.3f}{:s}"
          .format(current.mean(), i_unit,
                  audioop.rms(adc_data.current, p.get_sample_size(FORMAT)) 
                              * AMPS_PER_ADC_STEP, i_unit))

    def center_yaxis(ax):
        NUM_TICKS = 9
        ymin, ymax = ax.get_ylim()
        largest = max(abs(ymin), abs(ymax))
        ax.set_yticks(np.linspace(-largest, largest, NUM_TICKS))
        

    # two scales code adapted from matplotlib.org/examples/api/two_scales.html
    fig = plt.figure()
    v_ax = fig.add_subplot(111) # v_ax = voltage axes
    v_ax.plot(voltage, "b-")
    center_yaxis(v_ax)    
    v_ax.set_xlabel("time (samples)")
    
    # Make the y-axis label and tick labels match the line colour.
    v_ax.set_ylabel("potential different ({:s})".format(v_unit), color="b")
    for tl in v_ax.get_yticklabels():
        tl.set_color("b")
    
    # The function twinx() give us access to a second plot that
    # overlays the graph ax2 and shares the same X axis, but not the Y axis.     
    i_ax = v_ax.twinx()
    i_ax.plot(current, "g-")
    center_yaxis(i_ax)
    i_ax.set_ylabel("current ({:s})".format(i_unit), color="g")
    for tl in i_ax.get_yticklabels():
        tl.set_color("g")

    plt.grid()
    plt.show()
    
def find_time(adc_data_queue, target_time):
    """
    Looks through adc_data_queue for an entry with time=t.
    If an entry is found then that entry is returned and that entry and all
    previous entries are deleted from the Queue.
    If no matching entry is found the None is returned.
    
    Beware: If the queue contains at least one entry then EVERY call to this
        function will take at least one item off the queue, even if that
        item is not returned! 
    
    Args:
        adc_data_queue (Queue)
        target_time (int): UNIX timestamp
    """
    t = 0
    target_time = int(round(target_time))
    while t < target_time:
        adc_data = None                    
        try:
            adc_data = adc_data_queue.get_nowait()
        except Empty:
            return None
        else:            
            t = int(round(adc_data.time))
            print("Read", t)
    
    if t == target_time:
        return adc_data
    else:
        return None

def calibrate(adc_data_queue):    
    wu = wattsup.WattsUp()
    
    v_acumulator = 0.0 # accumulator for voltage
    i_acumulator = 0.0 # accumulator for current
    n_v_samples = 0 # number of voltage samples
    n_i_samples = 0 # number of current samples
    av_i_calibration = 0.0
    adc_i_rms = 0.0
    
    while True:
        wu_data = wu.get() # blocking
        
        # Now get ADC data recorded at wu_data.time
        adc_data = find_time(adc_data_queue, wu_data.time)
        
        if adc_data:
            # Voltage
            adc_v_rms = audioop.rms(adc_data.voltage, p.get_sample_size(FORMAT)) 
            n_v_samples += 1
            v_acumulator += wu_data.volts / adc_v_rms
            av_v_calibration = v_acumulator / n_v_samples # average voltage calibration
            
            # Current
            if wu_data.amps > 0.1:
                adc_i_rms = audioop.rms(adc_data.current, p.get_sample_size(FORMAT))
                n_i_samples += 1 
                i_acumulator += wu_data.amps / adc_i_rms
                av_i_calibration = i_acumulator / n_i_samples # average voltage calibration
            else:
                print("Not sampling amps because the WattsUp reading is too low.")    
            
            print("WattsUp Volts = {}, WattsUp amps = {}, \n"
                  "v_calibration = {}, i_calibration = {}, \n"
                  "adc_data.time = {}, wu_data.time = {}, time diff = {:1.3f}s"
                  .format(wu_data.volts, wu_data.amps,
                          av_v_calibration, av_i_calibration,
                          adc_data.time, wu_data.time, adc_data.time - wu_data.time))
            print("Calculated volts = {}, amps = {}"
                  .format(adc_v_rms * av_v_calibration,
                          adc_i_rms * av_i_calibration))
            config.set("Calibration", "volts_per_adc_step", av_v_calibration)
            config.set("Calibration", "amps_per_adc_step", av_i_calibration)
            with open(CONFIG_FILE, "wb") as configfile:
                config.write(configfile)
        else:
            print("Could not find match for", wu_data.time, file=sys.stderr)
            time.sleep(RECORD_SECONDS*2)
            
        # TODO:
        #  * do calcs for amps        


def setup_argparser():
    # Process command line _args
    parser = argparse.ArgumentParser(description="Record voltage and current"
                                     "  waveforms using the sound card.")
       
    parser.add_argument("--no-mixer-config", dest="config_mixer", 
                        action="store_false",
                        help="Don't modify ALSA mixer (i.e. use existing system settings)")
    
    parser.add_argument("--calibrate", 
                        action="store_true",
                        help="Run calibration using a WattsUp meter")
    
    parser.add_argument("--plot", 
                    action="store_true",
                    help="Plot one second's worth of data")

    
    args = parser.parse_args()

    return args

def start_adc_data_queue_and_thread():
    adc_data_queue = Queue()
    adc_thread = Thread(target=enqueue_adc_data, args=(adc_data_queue, ))
    adc_thread.daemon = True # this thread dies with the program
    adc_thread.start()
    
    return adc_data_queue, adc_thread    
    

def main():
    args = setup_argparser()
    
    if args.config_mixer:
        config_mixer()

    adc_data_queue, adc_thread = start_adc_data_queue_and_thread()

    if args.calibrate:
        calibrate(adc_data_queue)
    elif args.plot:
        plot(adc_data_queue)
    else:
        while True:
            try:
                record_data(adc_data_queue)
            except KeyboardInterrupt:
                audio_stream.stop_stream()
                audio_stream.close()
                p.terminate()
                break
        
    print("")

if __name__=="__main__":
    main()
