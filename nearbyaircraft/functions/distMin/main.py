import requests 
from google.cloud import bigquery
from datetime import datetime, timedelta
from dateutil.parser import parse 
import pandas as pd
import math
import pytz


def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):

  R = 6371e3  # Earth's radius in meters

  phi1 = lat1 * math.pi / 180
  phi2 = lat2 * math.pi / 180
  delta_phi = (lat2 - lat1) * math.pi / 180
  delta_lambda = (lon2 - lon1) * math.pi / 180

  a = math.sin(delta_phi / 2) * math.sin(delta_phi / 2) + \
      math.cos(phi1) * math.cos(phi2) * \
      math.sin(delta_lambda / 2) * math.sin(delta_lambda / 2)
  c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

  d = R * c  # Distance on the surface
  alt_diff = alt2 - alt1  # Altitude difference

  distance_3d = math.sqrt(d * d + alt_diff * alt_diff)
  return distance_3d


def interpolate_sql_timestamps(timestamp1, timestamp2):

    # Convert SQL timestamps to pandas Timestamp objects
    ts1 = pd.to_datetime(timestamp1)
    ts2 = pd.to_datetime(timestamp2)

    # Calculate the difference between timestamps in seconds
    delta_seconds = (ts2 - ts1).total_seconds()

    # Calculate the interpolated timestamp in seconds
    interpolated_seconds = ts1.timestamp() + delta_seconds / 2

    # Convert interpolated seconds back to pandas Timestamp
    interpolated_ts = pd.to_datetime(interpolated_seconds, unit='s')

    # Format the interpolated timestamp in SQL format
    return interpolated_ts.strftime('%Y-%m-%d %H:%M:%S')



def interpolar (results):
    # table_id = 'voos.tempDist' 
    rows_to_insert = [] 
    
    i = 0
    while i < len(results):
        call_sign = results[i][1]
        distance = results[i]['distance']
        timestamp = results[i]['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        latitude = results[i]['latitude']
        longitude = results[i]['longitude']
        altitude = results[i]['altitude']
        velocidade = results[i]['velocidade']  
        country = results[i]['country']
        tipo = results[i]['tipo']
        climbing_rate = results[i][5]
        if i + 1 < len(results) and results[i][1] == results[i+1][1]:
            dist_interpol = calculate_3d_distance(
                41.1653349, -8.67588, 0, # ponto de referência
                # a seguir coordenadas do ponto interpolado
                (results[i]['latitude'] + results[i+1]['latitude']) / 2, 
                (results[i]['longitude'] + results[i+1]['longitude']) / 2, 
                (results[i]['altitude'] + results[i+1]['altitude']) / 2
            )
            if dist_interpol  < distance:
                distance = dist_interpol
                latitude = (results[i]['latitude'] + results[i+1]['latitude']) / 2
                longitude = (results[i]['longitude'] + results[i+1]['longitude']) / 2
                altitude = round((results[i]['altitude'] + results[i+1]['altitude']) / 2)
                timestamp = interpolate_sql_timestamps(
                    results[i]['timestamp'], results[i+1]['timestamp'])
                velocidade = (results[i]['velocidade'] + results[i+1]['velocidade']) / 2
                # para marcar que se trata de registo interpolado, sem perder info do tipo
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


def distMin(data, context):
    client = bigquery.Client() 
    current_date = (datetime.utcnow() - timedelta(days=0)).strftime('%Y-%m-%d')
    query = f"""    SELECT *
                    FROM (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (PARTITION BY call_sign ORDER BY distance) AS row_num
                    FROM
                        voos.brutos
                    WHERE DATE(timestamp) = '{current_date}'
                    )
                    WHERE
                    row_num = 1  or row_num = 2; """ 
    results = client.query(query).result()
    
    table_id = 'voos.distancias' 
    rows_to_insert = interpolar(list(results)) 
    
    if rows_to_insert:
        errors = client.insert_rows_json(table_id, rows_to_insert)
        print(errors)
