from flask import Flask, request, jsonify, send_from_directory
import requests
import math
import time
from datetime import datetime
import os
from zoneinfo import ZoneInfo
        

app = Flask(__name__, static_folder='../www', static_url_path='/nearbyaircraft')

# Database configuration
DATABASE_PATH = '/home/admin/nearbyaircraft/functions/recolheVoos/voos.db'

# 🧠 In-memory cache (to avoid overloading OpenSky)
cache = {
    "timestamp": 0,
    "data": None
}
CACHE_DURATION = 30  # seconds


# -------- API Endpoint: Aircraft Data --------
@app.route("/api/copilot")
def get_aircraft():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("long"))
        alt = float(request.args.get("alt"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing lat/long/alt parameters"}), 400

    now = time.time()
    if cache["data"] and (now - cache["timestamp"] < CACHE_DURATION):
        return jsonify(cache["data"])

    lamin, lamax = lat - 0.5, lat + 0.5
    lomin, lomax = lon - 0.5, lon + 0.5
    opensky_url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"

    try:
        response = requests.get(opensky_url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return jsonify({"error": f"Error fetching data from OpenSky: {e}"}), 502

    if not data.get("states"):
        return jsonify({"message": "No aircraft nearby"})

    results = []
    for state in data["states"]:
        distance = calculate_3d_distance(lat, lon, alt, state[6], state[5], state[13] or 0)
        altit = state[13] if state[13] is not None else "n.a."
        rate = f"{state[11]:.1f}" if state[11] is not None else "n.a."
        velocity = f"{state[9] * 3.6:.1f}" if state[9] else "n.a."
        tipo = state[17] if len(state) > 17 else "n.a."
        results.append([
            state[1], state[2], f"{distance:.1f}", altit, rate,
            state[6], state[5], velocity, tipo
        ])

    response_object = {
        "timestamp": datetime.utcfromtimestamp(data["time"]).isoformat(),
        "latlongalt": [lat, lon, alt],
        "header": ["Callsign", "Country", "Distance", "Altitude", "Climbing", "Latitude", "Longitude", "Velocidade", "Tipo"],
        "aircraft": results,
        "urlsource": opensky_url,
        "source": "Adapted from OpenSky Network ADS-B data"
    }

    cache["timestamp"] = time.time()
    cache["data"] = response_object
    return jsonify(response_object)

@app.route('/api/madrug2', methods=['POST', 'OPTIONS'])
def madrug2_api():
    """Process flight data from SQLite"""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    try:
        data = request.get_json()
        # ... (your existing SQLite implementation)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/flightPaths')
def flight_paths():
    # [Your flight path fetching logic]
    ...

@app.route('/api', methods=['GET'])
def aircraft_api():
    """OpenSky endpoint with Node.js-compatible timestamp"""
    try:
        # Validate parameters
        lat = request.args.get('lat', type=float)
        long = request.args.get('long', type=float)
        alt = request.args.get('alt', type=float)
        
        if None in (lat, long, alt) or not (-90 <= lat <= 90) or not (-180 <= long <= 180):
            return jsonify({"error": "Invalid latitude, longitude or altitude"}), 400

        # Call OpenSky API
        url = f"https://opensky-network.org/api/states/all?lamin={lat-0.5}&lomin={long-0.5}&lamax={lat+0.5}&lomax={long+0.5}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("states"):
            return jsonify({"message": "No aircraft nearby"})

        # Process aircraft data
        resultados = []
        for state in data["states"]:
            distance = calculate_3d_distance(lat, long, alt, state[6], state[5], state[13] or 0)
            resultados.append([
                state[1], state[2], f"{distance:.1f}",
                state[13] if state[13] is not None else "n.a.",
                f"{state[11]:.1f}" if state[11] is not None else "n.a.",
                state[6], state[5],
                state[9] * 3.6 if state[9] else "n.a.",
                state[17] if len(state) > 17 else "n.a."
            ])

        # Node.js-compatible timestamp formatting
        dt = datetime.fromtimestamp(data["time"], ZoneInfo("Europe/Lisbon"))
        nodejs_timestamp = dt.strftime("%a %b %d %Y %H:%M:%S GMT%z (%Z)")

        return jsonify({
            "timestamp": nodejs_timestamp,  # Matches Node.js output
            "iso_timestamp": dt.isoformat(),  # Bonus: machine-readable format
            "latlongalt": [lat, long, alt],
            "header": ["Callsign", "Country", "Distance", "Altitude", "Climbing", 
                      "Latitude", "Longitude", "Velocity", "Type"],
            "aircraft": resultados,
            "urlsource": url,
            "source": "OpenSky Network"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- Frontend Routes --------
@app.route('/madrug')
def serve_madrug():
    return send_from_directory(app.static_folder, 'madrug.html')

@app.route('/madrug2')
def serve_madrug2():
    return send_from_directory(app.static_folder, 'madrug2.html')

@app.route('/mapa')
def serve_mapa():
    return send_from_directory(app.static_folder, 'mapa.html')

@app.route('/nearbyaircraft/')
def serve_index():
    return app.send_static_file('index.html')

# -------- Catch-All for Static Assets --------
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# -------- Root Route (index.html) --------
@app.route('/')
def serve_root():
    return send_from_directory(app.static_folder, 'index.html')

# -------- Optional: Disable Caching --------
@app.after_request
def disable_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response

# --------------------------
# Helper Functions
# --------------------------

def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):
    R = 6371e3  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    surface_distance = R * c
    vertical_distance = alt2 - alt1
    
    return math.sqrt(surface_distance**2 + vertical_distance**2)
    
# -------- App Runner --------
if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0", port=5000)