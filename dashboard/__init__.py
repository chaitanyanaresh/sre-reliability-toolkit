"""Web dashboard for the SRE Reliability Toolkit.

A zero-dependency front end over the toolkit's pipeline outputs: the SLO
report, the burn-rate alert decisions, the post-incident review impact,
and a live health-check snapshot. The server is Python standard library
only (``http.server``); the page is vanilla HTML/CSS/JS with charts drawn
as inline SVG — no CDN, no build step, works fully offline.

Flow:

    bash scripts/run_all.sh          # pipeline -> outputs/
    python -m dashboard.build_data   # outputs/  -> dashboard/data/*.json
    python -m dashboard.server       # http://127.0.0.1:8080/
"""
