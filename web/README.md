# parrot-lab web

Static client. Run locally:

    cd web
    python3 -m http.server 8000

Open http://localhost:8000/. The mock /align is wired in api.js (USE_MOCK = true) — no backend needed for the basic UI loop. Set USE_MOCK = false once the serverless function ships.
