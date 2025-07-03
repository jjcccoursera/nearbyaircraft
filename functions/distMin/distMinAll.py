import sqlite3
import os
from datetime import datetime, timedelta
import pandas as pd
import math

"""
Script para processar dados de voos da tabela 'brutos' e calcular distâncias mínimas

Funcionalidades principais:
1. Identifica datas presentes na tabela 'brutos' que ainda não foram processadas na tabela 'distancias'
2. Para cada voo, encontra os 2 pontos mais próximos de uma referência (Porto: 41.1653349, -8.67588)
3. Calcula distância 3D (incluindo altitude) entre a referência e cada ponto do voo
4. Interpola posições entre os 2 pontos mais próximos quando possível
5. Armazena os resultados na tabela 'distancias' com informações consolidadas

Métodos principais:
- calculate_3d_distance: Calcula distância 3D entre dois pontos geográficos
- interpolar: Processa os dados brutos e gera pontos interpolados quando vantajoso
- get_missing_dates: Identifica datas não processadas
- process_date: Processa todos os voos de uma data específica
- distMin: Função principal que orquestra todo o processamento

"""

def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):
    """
    Calcula a distância 3D entre dois pontos geográficos considerando altitude
    Usa fórmula de Haversine para cálculo da distância superficial e
    adiciona componente vertical (altitude) para distância final
    """
    
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

def get_missing_dates(conn):
    """
    Identifica datas presentes na tabela 'brutos' que ainda não foram
    processadas na tabela 'distancias'
    
    Retorna:
        Lista de strings no formato 'YYYY-MM-DD' com as datas faltantes
    """
    
    cur = conn.cursor()
    
    # First try to get dates using SQLite's DATE function
    query = """
        SELECT DISTINCT substr(timestamp, 1, 10) as date
        FROM brutos
        WHERE substr(timestamp, 1, 10) NOT IN (
            SELECT DISTINCT substr(timestamp, 1, 10)
            FROM distancias
        )
        ORDER BY date;
    """
    
    cur.execute(query)
    dates = [row[0] for row in cur.fetchall()]
    
    if not dates:
        # Alternative approach if the first one fails
        query = """
            SELECT DISTINCT timestamp
            FROM brutos
            WHERE substr(timestamp, 1, 10) NOT IN (
                SELECT DISTINCT substr(timestamp, 1, 10)
                FROM distancias
            )
            ORDER BY timestamp;
        """
        cur.execute(query)
        timestamps = [row[0] for row in cur.fetchall()]
        dates = list({ts.split()[0] for ts in timestamps})
    
    return dates

def process_date(conn, date):
    """Process all records for a specific date"""
    cur = conn.cursor()
    
    query = """
        SELECT *
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY call_sign ORDER BY distance ASC) AS row_num
            FROM brutos
            WHERE substr(timestamp, 1, 10) = ?
        )
        WHERE row_num = 1 OR row_num = 2;
    """

    results = cur.execute(query, (date,)).fetchall()

    if not results:
        print(f"No data found for {date} — skipping.")
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
    print(f"Processed and inserted data for {date}")

def distMin():
    # Get the absolute path to the database file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    db_path = os.path.join(parent_dir, 'recolheVoos', 'voos.db')
    
    conn = sqlite3.connect(db_path)
    
    # Enable write-ahead logging for better performance
    conn.execute("PRAGMA journal_mode=WAL")
    
    missing_dates = get_missing_dates(conn)
    
    if not missing_dates:
        print("All dates in brutos are already processed in distancias.")
        conn.close()
        return
    
    print(f"Found {len(missing_dates)} dates to process")
    
    for date in missing_dates:
        process_date(conn, date)
    
    conn.close()
    print("Processing complete.")

if __name__ == "__main__":
    distMin()