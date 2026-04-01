#!/usr/bin/env python3
"""
Recolha de dados OpenSky - Script simples e parametrizável
Uso: python fetch_opensky.py [duracao_horas] [intervalo_segundos]
Exemplo: python fetch_opensky.py 3 60  # 3 horas, 1 chamada por minuto
"""

import requests
import sqlite3
import time
import math
import sys
from datetime import datetime

# Configuração padrão
LAT_REF = 41.1653349
LONG_REF = -8.6758848
ALT_REF = 0
DB_PATH = 'voos.db'

def calc_dist(lat1, lon1, alt1, lat2, lon2, alt2):
    """Calcula distância 3D em metros."""
    R = 6371000
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_r)*math.cos(lat2_r)*math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    h = R * c
    v = abs(alt2 - alt1)
    return math.sqrt(h**2 + v**2)

def fetch_and_save():
    """Faz uma chamada à API e guarda na BD."""
    lamin = LAT_REF - 0.5
    lomin = LONG_REF - 0.5
    lamax = LAT_REF + 0.5
    lomax = LONG_REF + 0.5
    url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return -1
            
        data = response.json()
        states = data.get('states')
        
        timestamp = data.get('time', int(datetime.now().timestamp()))
        ts = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        if states:
            for state in states:
                call = state[1] or ""
                country = state[2] or ""
                lat = state[6] or 0
                lon = state[5] or 0
                alt = state[13] or (state[7] or 0)
                vel = (state[9] * 3.6) if state[9] else 0
                rate = state[11] or 0
                dist = calc_dist(LAT_REF, LONG_REF, ALT_REF, lat, lon, alt)
                tipo = state[17] if len(state) > 17 and state[17] else 0
                
                cur.execute("""INSERT INTO brutos 
                    (timestamp, call_sign, country, distance, altitude, climbing_rate, latitude, longitude, velocidade, tipo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, call, country, round(dist,1), round(alt,1), round(rate,1), round(lat,6), round(lon,6), round(vel,1), tipo))
        
        conn.commit()
        conn.close()
        return len(states) if states else 0
    except Exception as e:
        print(f"Erro: {e}")
        return -1

def main():
    # Parâmetros
    duracao_horas = float(sys.argv[1]) if len(sys.argv) > 1 else 3
    intervalo = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    print(f"🚀 Recolha de dados OpenSky")
    print(f"📁 BD: {DB_PATH}")
    print(f"⏱️ Duração: {duracao_horas}h | Intervalo: {intervalo}s")
    print(f"🕐 Início: {datetime.now().strftime('%H:%M:%S')}")
    print("-" * 50)
    
    start_time = datetime.now()
    end_time = start_time.timestamp() + (duracao_horas * 3600)
    
    success = 0
    fail = 0
    
    while datetime.now().timestamp() < end_time:
        now = datetime.now()
        result = fetch_and_save()
        
        if result >= 0:
            success += 1
            print(f"{now.strftime('%H:%M:%S')} ✅ {result} voos")
        else:
            fail += 1
            print(f"{now.strftime('%H:%M:%S')} ❌ falha")
        
        # Aguardar próximo intervalo
        time.sleep(intervalo)
    
    print("\n" + "=" * 50)
    print(f"✅ Concluído!")
    print(f"✅ Sucessos: {success}")
    print(f"❌ Falhas: {fail}")
    print(f"🕐 Fim: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
