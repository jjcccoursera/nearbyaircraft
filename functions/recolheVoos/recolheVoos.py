import requests
from datetime import datetime
from dateutil.parser import parse
import pytz
import sqlite3

def safe_get(url, retries=3, delay=5):
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 429:
                print(f"Attempt {attempt+1}: Rate limited. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                return response
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: Request error: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
    print("Max retries reached. Skipping this request.")
    return None
    
def recolheVoos():

    lat = '41.1653349'
    long = '-8.6758848'
    alt = '0'
    url = f"https://nearbyaircraft.ew.r.appspot.com/api?lat={lat}&long={long}&alt={alt}"

    
    response = safe_get(url)
    if not response:
        return

    try:
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        print(f"Status code: {response.status_code} on URL: {url}")
        return

    if response:
        data = response.json()
        if response.status_code == 200 and 'aircraft' in data and data['aircraft']:
            aircraft_list = data['aircraft']
            timestamp = data['timestamp']
            dt_object = parse(timestamp, fuzzy=True)
            portugal_tz = pytz.timezone('Europe/Lisbon')
            dt_object = dt_object.astimezone(portugal_tz)
            formatted_timestamp = dt_object.strftime('%Y-%m-%d %H:%M:%S')
            print(f"Portugal Time: {formatted_timestamp} | Aircraft found: {len(aircraft_list)}")
            processa_lista(formatted_timestamp, aircraft_list)
        else:
            print("Unexpected response format or missing keys")

def processa_lista(timestamp, aircraft_list):

    conn = sqlite3.connect('/home/admin/nearbyaircraft/functions/recolheVoos/voos.db')
    cur = conn.cursor()

    for i, aircraft in enumerate(aircraft_list):

        call_sign = aircraft[0] or ""
        country = aircraft[1] or ""
        distance = float(aircraft[2]) if aircraft[2] else 0.0
        altitude = float(aircraft[3]) if aircraft[3] else 0.0
        climbing_rate = float(aircraft[4]) if aircraft[4] else 0.0
        latitude = float(aircraft[5]) if aircraft[5] else 0.0
        longitude = float(aircraft[6]) if aircraft[6] else 0.0
        velocidade = float(aircraft[7]) if aircraft[7] else 0.0
        tipo = int(aircraft[8]) if isinstance(aircraft[8], int) else 0

        cur.execute("""
            INSERT INTO brutos (
                timestamp, call_sign, country, distance, altitude,
                climbing_rate, latitude, longitude, velocidade, tipo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, call_sign, country, distance, altitude,
              climbing_rate, latitude, longitude, velocidade, tipo))

    conn.commit()
    cur.close()
    conn.close()
    print("Data inserted successfully into voos.db")


recolheVoos()
