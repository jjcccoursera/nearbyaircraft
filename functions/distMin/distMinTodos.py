#!/usr/bin/env python3
"""
Pré-calcula as distâncias mínimas usando a MESMA lógica da webapp (app.js)
Guarda na tabela distancias_min apenas voos com distância < 3000m
Processa apenas dias que ainda não estão na tabela
"""
import sqlite3
import math
import logging
import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Configuração
DB_PATH = '/home/admin/nearbyaircraft/functions/recolheVoos/voos.db'

# Ponto de referência (mesmo da webapp)
REF_LAT = 41.163484
REF_LON = -8.669470
REF_ALT = 30

# Limite de distância para guardar (metros)
DISTANCE_LIMIT = 3000

def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):
    """Calcula distância 3D em metros (mesma função da webapp)"""
    R = 6371e3
    phi1 = lat1 * math.pi / 180
    phi2 = lat2 * math.pi / 180
    delta_phi = (lat2 - lat1) * math.pi / 180
    delta_lambda = (lon2 - lon1) * math.pi / 180

    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = R * c
    alt_diff = alt2 - alt1
    return math.sqrt(d**2 + alt_diff**2)

def safe_avg(val1, val2, fraction):
    """Interpolação linear entre dois valores"""
    if val1 is None or val2 is None:
        return val1 if val1 is not None else val2
    return val1 + (val2 - val1) * fraction

def interpolate_timestamp(timestamp1, timestamp2, fraction):
    """Interpola timestamp entre dois pontos"""
    ts1 = datetime.strptime(timestamp1, '%Y-%m-%d %H:%M:%S')
    ts2 = datetime.strptime(timestamp2, '%Y-%m-%d %H:%M:%S')
    delta = (ts2 - ts1).total_seconds()
    interpolated = ts1.timestamp() + delta * fraction
    return datetime.fromtimestamp(interpolated).strftime('%Y-%m-%d %H:%M:%S')

def find_closest_point(records: List[Dict]) -> Optional[Dict]:
    """
    Encontra o ponto de menor distância para uma aeronave
    Usa a MESMA lógica da webapp (app.js)
    """
    if not records:
        return None
    
    dist_min = float('inf')
    closest = None
    
    # Frações de interpolação (mesmas da webapp: 0.1 a 0.9)
    fractions = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    
    for i in range(len(records)):
        rec = records[i]
        
        # 1. Verificar o ponto atual
        dist = calculate_3d_distance(
            rec['latitude'], rec['longitude'], rec['altitude'],
            REF_LAT, REF_LON, REF_ALT
        )
        
        if dist < dist_min:
            dist_min = dist
            closest = {
                'call_sign': rec['call_sign'],
                'distance': dist,
                'timestamp': rec['timestamp'],
                'latitude': rec['latitude'],
                'longitude': rec['longitude'],
                'altitude': rec['altitude'],
                'velocidade': rec['velocidade'],
                'tipo': rec['tipo'],
                'country': rec['country'],
                'climbing_rate': rec['climbing_rate']
            }
        
        # 2. Verificar pontos interpolados entre current e next
        if i < len(records) - 1:
            next_rec = records[i + 1]
            
            for fraction in fractions:
                lat_interp = safe_avg(rec['latitude'], next_rec['latitude'], fraction)
                lon_interp = safe_avg(rec['longitude'], next_rec['longitude'], fraction)
                alt_interp = safe_avg(rec['altitude'], next_rec['altitude'], fraction)
                
                dist_interp = calculate_3d_distance(
                    lat_interp, lon_interp, alt_interp,
                    REF_LAT, REF_LON, REF_ALT
                )
                
                if dist_interp < dist_min:
                    dist_min = dist_interp
                    closest = {
                        'call_sign': rec['call_sign'],
                        'distance': dist_interp,
                        'timestamp': interpolate_timestamp(rec['timestamp'], next_rec['timestamp'], fraction),
                        'latitude': lat_interp,
                        'longitude': lon_interp,
                        'altitude': alt_interp,
                        'velocidade': safe_avg(rec['velocidade'], next_rec['velocidade'], fraction),
                        'tipo': rec['tipo'],
                        'country': rec['country'],
                        'climbing_rate': safe_avg(rec['climbing_rate'], next_rec['climbing_rate'], fraction)
                    }
    
    return closest

def create_table():
    """Cria a tabela distancias_min se não existir"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS distancias_min (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sign TEXT,
            distance REAL,
            timestamp TEXT,
            altitude REAL,
            latitude REAL,
            longitude REAL,
            velocidade REAL,
            tipo INTEGER,
            country TEXT,
            climbing_rate REAL,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Criar índice para consultas rápidas
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dmin_date ON distancias_min(DATE(timestamp))')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dmin_call ON distancias_min(call_sign)')
    
    conn.commit()
    conn.close()
    print("✅ Tabela distancias_min criada/verificada")

def get_processed_dates():
    """Retorna os dias que já estão processados na tabela distancias_min"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT DATE(timestamp) FROM distancias_min ORDER BY DATE(timestamp)")
    dates = [row[0] for row in cur.fetchall()]
    conn.close()
    return set(dates)

def get_available_dates():
    """Retorna os dias que têm dados na tabela brutos"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT DATE(timestamp) FROM brutos ORDER BY DATE(timestamp)")
    dates = [row[0] for row in cur.fetchall()]
    conn.close()
    return set(dates)

def clear_day_data(target_date: str):
    """Remove dados existentes para o dia específico"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM distancias_min WHERE DATE(timestamp) = ?", (target_date,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted

def process_day(target_date: str):
    """Processa todos os voos de um dia específico"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Buscar todos os registos do dia, ordenados por aeronave e timestamp
    cur.execute("""
        SELECT *
        FROM brutos
        WHERE DATE(timestamp) = ?
        ORDER BY call_sign, timestamp ASC
    """, (target_date,))
    
    rows = cur.fetchall()
    
    if not rows:
        print(f"⚠️ Nenhum dado encontrado para {target_date}")
        conn.close()
        return 0
    
    # Agrupar por call_sign
    aircraft_data = {}
    for row in rows:
        row_dict = dict(row)
        cs = row_dict['call_sign']
        if cs and cs != '':  # Ignorar call_sign vazio
            if cs not in aircraft_data:
                aircraft_data[cs] = []
            aircraft_data[cs].append(row_dict)
    
    print(f"   Aeronaves: {len(aircraft_data)}, Registos: {len(rows)}")
    
    # Calcular ponto mais próximo para cada aeronave
    results = []
    for cs, records in aircraft_data.items():
        closest = find_closest_point(records)
        if closest and closest['distance'] < DISTANCE_LIMIT:
            results.append(closest)
    
    conn.close()
    
    if results:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        inserted = 0
        for r in results:
            cur.execute("""
                INSERT INTO distancias_min (
                    call_sign, distance, timestamp, altitude, latitude,
                    longitude, velocidade, tipo, country, climbing_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['call_sign'], r['distance'], r['timestamp'],
                r['altitude'], r['latitude'], r['longitude'],
                r['velocidade'], r['tipo'], r['country'], r['climbing_rate']
            ))
            inserted += 1
        
        conn.commit()
        conn.close()
        return inserted
    
    return 0

def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description='Pré-calcula distâncias mínimas (cache persistente)')
    parser.add_argument('--date', type=str, help='Processa data específica (YYYY-MM-DD)')
    parser.add_argument('--today', action='store_true', help='Processa hoje')
    parser.add_argument('--all', action='store_true', help='Processa todos os dias (apenas os que faltam)')
    parser.add_argument('--force', action='store_true', help='Força reprocessamento mesmo se já existir')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 Pré-cálculo de Distâncias Mínimas (cache persistente)")
    print(f"📍 Ponto de referência: {REF_LAT}, {REF_LON}, {REF_ALT}m")
    print(f"📏 Limite: {DISTANCE_LIMIT}m")
    print("=" * 70)
    
    create_table()
    
    # Obter dias já processados
    processed = get_processed_dates()
    available = get_available_dates()
    
    print(f"📊 Dias com dados em brutos: {len(available)}")
    print(f"📊 Dias já processados: {len(processed)}")
    
    # Determinar dias a processar
    if args.date:
        dates_to_process = [args.date]
        force = args.force
    elif args.today:
        today = datetime.now().strftime('%Y-%m-%d')
        dates_to_process = [today]
        force = args.force
    elif args.all:
        dates_to_process = sorted(available - processed) if not args.force else sorted(available)
        force = args.force
    else:
        # Por defeito, processa apenas o dia de hoje se não estiver processado
        today = datetime.now().strftime('%Y-%m-%d')
        if today in processed and not args.force:
            print(f"ℹ️ Hoje ({today}) já está processado. Use --force para reprocessar.")
            return
        dates_to_process = [today]
        force = True  # Se pediu explicitamente, processa
    
    if not dates_to_process:
        print("✅ Nenhum dia novo para processar.")
        return
    
    print(f"\n📅 Dias a processar: {len(dates_to_process)}")
    
    total_inserted = 0
    for target_date in dates_to_process:
        print(f"\n📅 Processando: {target_date}")
        
        if target_date in processed and not force:
            print(f"   ⏭️ Já processado. Use --force para reprocessar.")
            continue
        
        deleted = clear_day_data(target_date)
        if deleted > 0:
            print(f"   🗑️ Removidos {deleted} registos antigos")
        
        inserted = process_day(target_date)
        if inserted > 0:
            print(f"   💾 Inseridos {inserted} registos (dist < {DISTANCE_LIMIT}m)")
            total_inserted += inserted
        else:
            print(f"   ℹ️ Nenhum voo com distância < {DISTANCE_LIMIT}m")
    
    print("\n" + "=" * 70)
    print(f"✅ Processamento concluído!")
    print(f"📊 Total de novos registos: {total_inserted}")
    print("=" * 70)

if __name__ == "__main__":
    main()