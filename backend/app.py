from flask import Flask, request, jsonify, send_from_directory
import requests
import math
import time
from datetime import datetime, timedelta
import os
from zoneinfo import ZoneInfo
import sqlite3
import logging
from flask.logging import default_handler
from logging.config import dictConfig
import sys


dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://sys.stderr',  # or 'ext://flask.logging.wsgi_errors_stream'
        'formatter': 'default'
    }},
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi']
    }
})        

app = Flask(__name__, static_folder='../www', static_url_path='/nearbyaircraft')

# ✅ Use app.logger directly — it's now properly configured
app.logger.debug("Logger initialized")
app.logger.debug(f"WSGI errors stream: {os.environ.get('wsgi.errors')}")

# Database configuration
DATABASE_PATH = '/home/admin/nearbyaircraft/functions/recolheVoos/voos.db'

# 🧠 In-memory cache (to avoid overloading OpenSky)
cache = {
    "timestamp": 0,
    "data": None
}
CACHE_DURATION = 30  # seconds

# https://chat.deepseek.com/a/chat/s/a8b5ad0e-1ee1-4f57-a6c5-59c3df57761b
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return response


# -------- API Endpoint: Aircraft Data --------

@app.route('/api/madrug3', methods=['POST', 'OPTIONS'], strict_slashes=False)
def madrug3_api():
    """Process flight data from SQLite"""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "*")
        response.headers.add("Access-Control-Allow-Methods", "*")
        return response

    try:
        data = request.get_json()
        required = ['dia', 'latitudeRef', 'longitudeRef', 'altitudeRef']
        if not all(k in data for k in required):
            return jsonify({"error": "Missing required parameters"}), 400

        # Get flights from SQLite
        flights = get_flights_for_date(data['dia'])
        
        # Process results
        resultados = []
        for callsign, records in flights.items():
            if not records:
                continue
                
            # Find closest point (using your existing Python functions)
            closest = find_closest_point3(
                records, 
                float(data['latitudeRef']), 
                float(data['longitudeRef']), 
                float(data['altitudeRef'])
            )
            if closest and closest.get("timestamp") is not None:
                resultados.append(closest)
            else:
                app.logger.warning(f"Skipping {callsign}: closest point is None or missing timestamp")
            
        # Sort by timestamp
        resultados.sort(key=lambda x: x['timestamp'])
        
        return jsonify(resultados), 200

    except Exception as e:
        app.logger.error(f"Error in madrug2: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/flightPaths')
def flight_paths():
    try:
        # Determine the default query date (today or yesterday based on time)
        now = datetime.now()
        query_time = now.replace(hour=8, minute=15, second=0, microsecond=0)
        query_date = now.date()

        if now < query_time:
            query_date = query_date - timedelta(days=1)

        # Check if 'dia' query parameter is provided and valid
        dia_param = request.args.get('dia')
        if dia_param:
            try:
                parsed_date = datetime.strptime(dia_param, '%Y-%m-%d').date()
                if dia_param == parsed_date.isoformat():
                    query_date = parsed_date
            except ValueError:
                pass  # Ignore invalid date format and use default

        print("Query date:", query_date)

        # Connect to SQLite and fetch data
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT
                call_sign,
                country,
                timestamp,
                latitude,
                longitude,
                altitude,
                climbing_rate,
                velocidade
            FROM brutos
            WHERE substring(timestamp, 1, 10) = ?
            ORDER BY call_sign, timestamp
        """
        cursor.execute(query, (query_date.isoformat(),))
        rows = cursor.fetchall()
        conn.close()

        # Group rows by call_sign
        flight_paths = {}
        for row in rows:
            record = dict(row)
            # Replace None values with defaults
            record['call_sign'] = record['call_sign'] if record['call_sign'] is not None else 'n.a.'
            record['climbing_rate'] = record['climbing_rate'] if record['climbing_rate'] is not None else 'n.a.'
            record['velocidade'] = record['velocidade'] if record['velocidade'] is not None else 'n.a.'
            record['altitude'] = record['altitude'] if record['altitude'] is not None else 'n.a.'
            record['latitude'] = record['latitude'] if record['latitude'] is not None else 'n.a.'
            record['longitude'] = record['longitude'] if record['longitude'] is not None else 'n.a.'
            record['timestamp'] = record['timestamp'] or ''
            
            for key, value in record.items():
                if value is None:
                    print(f"Warning: {key} is None in record {record}")
            call_sign = record['call_sign']
            if call_sign not in flight_paths:
                flight_paths[call_sign] = []
            flight_paths[call_sign].append(record)

        return jsonify(flight_paths)

    except Exception as e:
        print('Error fetching flight data:', e)
        return jsonify({'error': 'Error fetching flight data'}), 500

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

def get_flights_for_date(date):
    """Retrieve flights from SQLite for a specific date"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = """
        SELECT call_sign, timestamp, latitude, longitude, altitude, 
               velocidade, tipo, country, climbing_rate
        FROM brutos
        WHERE substring(timestamp, 1, 10) = ?
        ORDER BY call_sign, timestamp
    """
    
    cur.execute(query, (date,))
    rows = cur.fetchall()
    conn.close()
    
    # Group by callsign
    flights = {}
    for row in rows:
        callsign = row['call_sign']
        if callsign not in flights:
            flights[callsign] = []
        flights[callsign].append(dict(row))
    
    return flights
    
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

def interpolate_sql_timestamps(timestamp1, timestamp2, fraction=0.5):
    # Remove ' UTC' if present
    timestamp1 = timestamp1.replace(' UTC', '')
    timestamp2 = timestamp2.replace(' UTC', '')
    
    # Parse the input strings into datetime objects
    ts1 = datetime.strptime(timestamp1, '%Y-%m-%d %H:%M:%S')
    ts2 = datetime.strptime(timestamp2, '%Y-%m-%d %H:%M:%S')
    
    # Calculate the interpolated timestamp using the given fraction
    interpolated = datetime.fromtimestamp(ts1.timestamp() + fraction * (ts2.timestamp() - ts1.timestamp()))

    # Return formatted string
    return interpolated.strftime('%Y-%m-%d %H:%M:%S')

def safe_avg(a, b, fraction=0.5):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a + fraction * (b - a)  # Linear interpolation

def find_closest_point3(records, lat_ref, lon_ref, alt_ref, callsign_filter=None):
    import copy
    import logging
    from datetime import datetime

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')
    log = logging.getLogger()

    if not records:
        return None
    
    dist_min = float('inf')
    closest = None

    for i in range(len(records)):
        rec = records[i]
        if callsign_filter and rec.get('call_sign') != callsign_filter:
            continue  # Skip logging for other flights

        # 1. Always check the current record point
        dist = calculate_3d_distance(
            rec['latitude'], rec['longitude'], rec['altitude'],
            lat_ref, lon_ref, alt_ref
        )
        
        if dist < dist_min:
            dist_min = dist
            closest = copy.deepcopy(rec)
            closest['distance'] = dist
            
        # 2. Check interpolated points between current and next record
        # Only do this if we're not at the last record
        if i < len(records) - 1:
            next_rec = records[i + 1]
            
            # Define the interpolation fractions (25%, 50%, 75%)
            # fractions = [0.25, 0.5, 0.75]
            fractions = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

            for fraction in fractions:
                # Calculate interpolated values
                lat_interp = safe_avg(rec['latitude'], next_rec['latitude'], fraction)
                lon_interp = safe_avg(rec['longitude'], next_rec['longitude'], fraction)
                alt_interp = safe_avg(rec['altitude'], next_rec['altitude'], fraction)
                
                # Calculate distance for this interpolated point
                dist_interp = calculate_3d_distance(
                    lat_interp, lon_interp, alt_interp,
                    lat_ref, lon_ref, alt_ref
                )
                
                if dist_interp < dist_min:
                    dist_min = dist_interp
                    closest = {
                        'call_sign': rec['call_sign'],
                        'distance': dist_interp,
                        'timestamp': interpolate_sql_timestamps(rec['timestamp'], next_rec['timestamp'], fraction),
                        'latitude': lat_interp,
                        'longitude': lon_interp,
                        'altitude': alt_interp,
                        'velocidade': safe_avg(rec['velocidade'], next_rec['velocidade'], fraction),
                        'tipo': rec['tipo'],
                        'country': rec['country'],
                        'climbing_rate': safe_avg(rec['climbing_rate'], next_rec['climbing_rate'], fraction)
                    }
                    
    # Now the last record has been checked (as a point, not for interpolation)
    if closest:
        log.debug(f"[FINAL] Closest point for {closest['call_sign']}: {closest['timestamp']} | dist={closest['distance']:.2f}")
    else:
        log.debug("[FINAL] No closest point found.")
    return closest
    
# -------- App Runner --------
if __name__ == "__main__":
    app.debug = False
    app.run(host="0.0.0.0", port=5000)