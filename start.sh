#!/bin/bash
# SALESHAX Pitchdeck App — lokal starten (nutzt Claude Plan-Usage)
cd "$(dirname "$0")"
python3 -m streamlit run app.py --server.port 8501 --server.headless true
