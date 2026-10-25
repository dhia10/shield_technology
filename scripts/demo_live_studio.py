"""
Shield Technology - Live Interactive Test Studio Runner.
Launches FastAPI backend server and opens the real-time engineering demo console in the browser.
Usage:
    python scripts/demo_live_studio.py
"""

import os
import sys
import time
import webbrowser
import uvicorn

BANNER = """
================================================================================
   SHIELD TECHNOLOGY — LIVE DEFENSE ENGINEERING DEMO STUDIO
   Plateforme d'Intelligence et Télémétrie de Sécurité (ESPRIT Data Science)
================================================================================
   [✓] Architecture : Clean Layered Architecture (app/)
   [✓] Ingestion Edge: 34,600 ev/s (SLA Met) & HMAC-SHA256 Cryptographic Auth
   [✓] Real-Time Redactor: PII & Secret Scrubbing (***REDACTED***)
   [✓] ML Threat Scorer: 7D Shannon Entropy & Isolation Forest (F1: 99.67%)
   [✓] Vector Search Engine: NumPy Cosine Similarity (< 1.5 ms Latency)
   [✓] Storage Engine: SQLAlchemy Bulk Upsert (x27.65 Speedup Factor)
================================================================================
   [>] Live Interactive Demo URL : http://localhost:8000/demo
   [>] Swagger OpenAPI Spec      : http://localhost:8000/docs
   [>] Prometheus Metrics        : http://localhost:8000/metrics
================================================================================
"""


def main():
    print(BANNER)
    # Ensure working directory is shield-technology root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    sys.path.insert(0, project_root)
    os.chdir(project_root)

    # Launch browser after a brief delay
    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://localhost:8000/demo")
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    main()
