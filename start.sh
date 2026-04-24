#!/bin/bash
cd /home/azureuser/effectus-api
source venv/bin/activate
export PYTHONPATH=/home/azureuser/effectus-api
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1 --log-level info
