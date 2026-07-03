#!/bin/bash
cd /home/yova/Mark-XLVII
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000
./venv/bin/python3 main.py > run.log 2>&1
