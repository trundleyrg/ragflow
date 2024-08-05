#!/bin/bash

echo $SHELL
CONDA_HOME="/home/yinrigao/anaconda3"
export PYTHONPATH=$:/home/yinrigao/ragflow
source "$CONDA_HOME/bin/activate" py311torch
nohup python3 ./sdk/web_server/gr_interface.py &
#python3 ./sdk/web_server/gr_interface.py