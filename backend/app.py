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

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)
# logger.debug("This will show up in logs")

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

app.logger.debug(21)

# Database configuration
DATABASE_PATH = '/home/admin/nearbyaircraft/functions/recolheVoos/voos.db'

# 🧠 In-memory cache (to avoid overloading OpenSky)
cache = {
    "timestamp": 0,
    "data": None
}
CACHE_DURATION = 30  # seconds


# -------- API Endpoint: Aircraft Data --------

@app.route('/api/madrug2', methods=['POST', 'OPTIONS'], strict_slashes=False)
def madrug2_api():
    """Process flight data from SQLite"""
    app.logger.debug("34")
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
            closest = find_closest_point(
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

        # print(rows)

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

def get_flights_for_date(date):
    """Retrieve flights from SQLite for a specific date"""
    app.logger.debug("240")
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

def interpolate_sql_timestamps(timestamp1, timestamp2):
    # Remove ' UTC' if present
    timestamp1 = timestamp1.replace(' UTC', '')
    timestamp2 = timestamp2.replace(' UTC', '')
    app.logger.debug(f"[278] Raw timestamps: {timestamp1}, {timestamp2}")

    # Parse the input strings into datetime objects
    ts1 = datetime.strptime(timestamp1, '%Y-%m-%d %H:%M:%S')
    ts2 = datetime.strptime(timestamp2, '%Y-%m-%d %H:%M:%S')
    app.logger.debug(f"[283] Parsed datetimes: {ts1}, {ts2}")
    
    # Calculate the midpoint using datetime arithmetic
    midpoint = datetime.fromtimestamp((ts1.timestamp() + ts2.timestamp()) / 2)
    app.logger.debug(f"[288] Midpoint: {midpoint}")

    # Return formatted string
    return midpoint.strftime('%Y-%m-%d %H:%M:%S')

def safe_avg(a, b):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2

def find_closest_point(records, lat_ref, lon_ref, alt_ref):
    if not records:
        return None

    closest = records[0]
    min_dist = calculate_3d_distance(
        closest['latitude'], closest['longitude'], closest['altitude'],
        lat_ref, lon_ref, alt_ref
    )
    closest['distance'] = min_dist

    # Check midpoint between first and second record
    if len(records) > 1:
        lat_avg = (records[0]['latitude'] + records[1]['latitude']) / 2
        lon_avg = (records[0]['longitude'] + records[1]['longitude']) / 2
        alt_avg = (records[0]['altitude'] + records[1]['altitude']) / 2
        dist = calculate_3d_distance(lat_avg, lon_avg, alt_avg, lat_ref, lon_ref, alt_ref)
        if dist < min_dist:
            min_dist = dist
            closest = {
                'call_sign': records[0]['call_sign'],
                'distance': dist,
                'timestamp': interpolate_sql_timestamps(records[0]['timestamp'], records[1]['timestamp']),
                'latitude': lat_avg,
                'longitude': lon_avg,
                'altitude': alt_avg,
                'velocidade': safe_avg(records[0]['velocidade'], records[1]['velocidade']),
                'tipo': records[0]['tipo'],
                'country': records[0]['country'],
                'climbing_rate': safe_avg(records[0]['climbing_rate'], records[1]['climbing_rate'])
            }

    for i in range(1, len(records)):
        current = records[i]
        dist = calculate_3d_distance(
            current['latitude'], current['longitude'], current['altitude'],
            lat_ref, lon_ref, alt_ref
        )
        if dist < min_dist:
            min_dist = dist
            closest = current.copy()
            closest['distance'] = dist

        # Interpolate with previous
        prev = records[i - 1]
        lat_avg = (current['latitude'] + prev['latitude']) / 2
        lon_avg = (current['longitude'] + prev['longitude']) / 2
        alt_avg = (current['altitude'] + prev['altitude']) / 2
        dist = calculate_3d_distance(lat_avg, lon_avg, alt_avg, lat_ref, lon_ref, alt_ref)
        if dist < min_dist:
            min_dist = dist
            closest = {
                'call_sign': current['call_sign'],
                'distance': dist,
                'timestamp': interpolate_sql_timestamps(prev['timestamp'], current['timestamp']),
                'latitude': lat_avg,
                'longitude': lon_avg,
                'altitude': alt_avg,
                'velocidade': safe_avg(prev['velocidade'], current['velocidade']),
                'tipo': current['tipo'],
                'country': current['country'],
                'climbing_rate': safe_avg(prev['climbing_rate'], current['climbing_rate'])
            }

        # Interpolate with next (if exists)
        if i + 1 < len(records):
            next_rec = records[i + 1]
            lat_avg = (current['latitude'] + next_rec['latitude']) / 2
            lon_avg = (current['longitude'] + next_rec['longitude']) / 2
            alt_avg = (current['altitude'] + next_rec['altitude']) / 2
            dist = calculate_3d_distance(lat_avg, lon_avg, alt_avg, lat_ref, lon_ref, alt_ref)
            if dist < min_dist:
                min_dist = dist
                closest = {
                    'call_sign': current['call_sign'],
                    'distance': dist,
                    'timestamp': interpolate_sql_timestamps(current['timestamp'], next_rec['timestamp']),
                    'latitude': lat_avg,
                    'longitude': lon_avg,
                    'altitude': alt_avg,
                    'velocidade': safe_avg(current['velocidade'], next_rec['velocidade']),
                    'tipo': current['tipo'],
                    'country': current['country'],
                    'climbing_rate': safe_avg(current['climbing_rate'], next_rec['climbing_rate'])
                }

    return closest

    
# -------- App Runner --------
if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0", port=5000)