import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import math

def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):
    R = 6371e3  # Earth's radius in meters
    phi1 = lat1 * math.pi / 180
    phi2 = lat2 * math.pi / 180
    delta_phi = (lat2 - lat1) * math.pi / 180
    delta_lambda = (lon2 - lon1) * math.pi / 180

    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = R * c  # Surface distance
    alt_diff = alt2 - alt1

    return math.sqrt(d**2 + alt_diff**2)

def interpolate_sql_timestamps(timestamp1, timestamp2):
    ts1 = pd.to_datetime(timestamp1)
    ts2 = pd.to_datetime(timestamp2)
    delta_seconds = (ts2 - ts1).total_seconds()
    interpolated_seconds = ts1.timestamp() + delta_seconds / 2
    interpolated_ts = pd.to_datetime(interpolated_seconds, unit='s')
    return interpolated_ts.strftime('%Y-%m-%d %H:%M:%S')

def interpolar(results):
    rows_to_insert = []
    i = 0
    while i < len(results):
        call_sign = results[i]['call_sign']
        distance = results[i]['distance']
        timestamp = pd.to_datetime(results[i]['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        latitude = results[i]['latitude']
        longitude = results[i]['longitude']
        altitude = results[i]['altitude']
        velocidade = results[i]['velocidade']
        country = results[i]['country']
        tipo = results[i]['tipo']
        climbing_rate = results[i]['climbing_rate']

        if i + 1 < len(results) and results[i]['call_sign'] == results[i + 1]['call_sign']:
            dist_interpol = calculate_3d_distance(
                41.1653349, -8.67588, 0,
                (results[i]['latitude'] + results[i+1]['latitude']) / 2,
                (results[i]['longitude'] + results[i+1]['longitude']) / 2,
                (results[i]['altitude'] + results[i+1]['altitude']) / 2
            )
            if dist_interpol < distance:
                distance = dist_interpol
                latitude = (results[i]['latitude'] + results[i+1]['latitude']) / 2
                longitude = (results[i]['longitude'] + results[i+1]['longitude']) / 2
                altitude = round((results[i]['altitude'] + results[i+1]['altitude']) / 2)
                timestamp = interpolate_sql_timestamps(results[i]['timestamp'], results[i+1]['timestamp'])
                velocidade = (results[i]['velocidade'] + results[i+1]['velocidade']) / 2
                tipo = -results[i]['tipo'] - 1
            i += 1
        i += 1

        rows_to_insert.append({
            'call_sign': call_sign,
            'distance': round(distance, 1),
            'timestamp': timestamp,
            'altitude': round(altitude, 1),
            'latitude': round(latitude, 3),
            'longitude': round(longitude, 3),
            'velocidade': round(velocidade, 1),
            'tipo': tipo,
            'country': country,
            'climbing_rate': climbing_rate
        })
    return rows_to_insert

def distMin():
    conn = sqlite3.connect('/home/admin/nearbyaircraft/functions/recolheVoos/voos.db')
    cur = conn.cursor()

    query = """
        SELECT *
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY call_sign ORDER BY distance ASC) AS row_num
            FROM brutos
            WHERE DATE(timestamp) = DATE('now', 'localtime')
        )
        WHERE row_num = 1 OR row_num = 2;
    """

    results = cur.execute(query).fetchall()

    if not results:
        print("No data found for today — skipping interpolation.")
        conn.close()
        return

    column_names = [desc[0] for desc in cur.description]
    result_dicts = [dict(zip(column_names, row)) for row in results]
    interpolated_rows = interpolar(result_dicts)

    for row in interpolated_rows:
        cur.execute("""
            INSERT INTO distancias (
                call_sign, distance, timestamp, altitude, latitude,
                longitude, velocidade, tipo, country, climbing_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row['call_sign'], row['distance'], row['timestamp'],
            row['altitude'], row['latitude'], row['longitude'],
            row['velocidade'], row['tipo'], row['country'], row['climbing_rate']
        ))

    conn.commit()
    conn.close()
    print("Interpolated rows inserted into distancias")

if __name__ == "__main__":
    distMin()