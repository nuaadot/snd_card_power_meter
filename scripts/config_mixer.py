#! /usr/bin/python

import subprocess, sys

def run_command(cmd):
    """Run a UNIX shell command.
    
    Args:
        cmd (list of strings)
    """
    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        proc.wait()
    except Exception, e:
        print("ERROR: Failed to run '{}'".format(" ".join(cmd)), file=sys.stderr)
        print("ERROR:", str(e), file=sys.stderr)
    else:
        if proc.returncode == 0:
            print("Successfully ran '{}'".format(" ".join(cmd)))
        else:
            print("ERROR: Failed to run '{}'".format(" ".join(cmd)),
                   file=sys.stderr)
            print(proc.stderr.read(), file=sys.stderr)


def config_mixer():
    print("Configuring mixer...")
    run_command(["amixer", "sset", "Input Source", "Rear Mic"])
    run_command(["amixer", "set", "Digital", "60", "capture"])
    run_command(["amixer", "set", "Capture", "16", "capture"])


if __name__=="__main__":
    config_mixer()