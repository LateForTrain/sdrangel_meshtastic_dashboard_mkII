#!/usr/bin/env python

import subprocess

if __name__ == "__main__":
    result = subprocess.run(["python", "-m", "src.meshtastic_frontend.main"], check=True)