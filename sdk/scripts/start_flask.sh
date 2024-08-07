#!/bin/bash

echo $SHELL
CONDA_HOME="/home/yinrigao/anaconda3"
source "$CONDA_HOME/bin/activate" py311torch
export PYTHONPATH=$:/home/yinrigao/ragflow
nohup python3 ./sdk/web_server/flask_server.py -m flask run &
#python3 ./sdk/web_server/flask_server.py -m flask run
