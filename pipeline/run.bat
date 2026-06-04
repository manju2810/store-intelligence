@echo off
echo Starting Store Intelligence Pipeline
echo =====================================

echo Step 1: Running detection pipeline...
python detect.py

echo Step 2: Ingesting events into API...
python ingest.py

echo =====================================
echo Pipeline complete
pause