#!/bin/bash
echo "Starting Store Intelligence Pipeline"
echo "====================================="

# Step 1 — Run detection
echo "Step 1: Running detection pipeline..."
python detect.py

# Step 2 — Ingest events into API
echo "Step 2: Ingesting events into API..."
python ingest.py

echo "====================================="
echo "Pipeline complete"docker compose up --build