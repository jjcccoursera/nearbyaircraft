import requests 
from google.cloud import bigquery
from datetime import datetime 
from dateutil.parser import parse 

def recolheVoos(data, context):
    lat = '41.1653349'
    long = '-8.6758848'
    alt = '0'
    url = f"https://nearbyaircraft.ew.r.appspot.com/api?lat={lat}&long={long}&alt={alt}"
    response = requests.get(url)
    
    try: 
        response = requests.get(url) 
        response.raise_for_status() # This will raise an HTTPError for bad responses 
    except requests.exceptions.RequestException as e: 
        print(f"Request failed: {e}")
    
    if response.status_code == 200:
        if 'aircraft' in response.json():
            aircraft_list = response.json()['aircraft']
            timestamp = response.json()['timestamp']
            # Parse the timestamp string using datetime.strptime
            dt_object = parse(timestamp, fuzzy=True)
            # Format the datetime object to the desired format
            formatted_timestamp = dt_object.strftime('%Y-%m-%d %H:%M:%S')
            print(formatted_timestamp, aircraft_list)
            processa_lista(formatted_timestamp, aircraft_list)
        else:
            print(response.json())
    else:
        print(f"Request failed with status code: {response.status_code}")
    
    current_date = datetime.utcnow().strftime('%Y-%m-%d')

    
def processa_lista(timestamp, aircraft_list):
    client = bigquery.Client()
    table_id = 'nearbyaircraft.voos.brutos'

    for aircraft in aircraft_list:
        call_sign = aircraft[0]
        country = aircraft[1]
        distance = aircraft[2]
        altitude = aircraft[3]
        if type(altitude) != int and type(altitude) != float:
            altitude = 0
        climbing_rate = aircraft[4]
        latitude = aircraft[5]
        if type(latitude) != int and type(latitude) != float:
            latitude = 0
        longitude = aircraft[6]
        if type(longitude) != int and type(longitude) != float:
            longitude = 0
        velocidade = aircraft[7]
        if type(velocidade) != int and type(velocidade) != float:
            velocidade = 0
        tipo = aircraft[8]
        if type(tipo) != int:
            tipo = 0
        
        rows_to_insert = [{
            'timestamp': timestamp,
            'call_sign': call_sign,
            'country': country,
            'distance': distance,
            'altitude': altitude,
            'climbing_rate': climbing_rate,
            'latitude': latitude,
            'longitude': longitude,
            'velocidade': velocidade,
            'tipo': tipo
        }]
        errors = client.insert_rows_json(table_id, rows_to_insert)
        if errors == []:
            print("Data inserted successfully.")
        else:
            print("Encountered errors during insertion:")
            for error in errors:
                print(f"Error: {error}")
        
