#!/usr/bin/env python3
"""
Validação do distMin - processa um dia específico da BD principal
"""

import sqlite3
import math
from datetime import datetime

DB_PATH = 'voos.db'
TARGET_DATE = '2026-02-25'
REF_LAT = 41.1653349
REF_LON = -8.6758848
REF_ALT = 30

def calculate_3d_distance(lat1, lon1, alt1, lat2, lon2, alt2):
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

def interpolate_timestamp(timestamp1, timestamp2):
    ts1 = datetime.strptime(timestamp1, '%Y-%m-%d %H:%M:%S')
    ts2 = datetime.strptime(timestamp2, '%Y-%m-%d %H:%M:%S')
    delta_seconds = (ts2 - ts1).total_seconds()
    interpolated_seconds = ts1.timestamp() + delta_seconds / 2
    return datetime.fromtimestamp(interpolated_seconds).strftime('%Y-%m-%d %H:%M:%S')

print("=" * 60)
print(f"📊 Validando distMin para {TARGET_DATE}")
print("=" * 60)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Obter as 2 posições mais próximas por aeronave
query = f"""
    SELECT *
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY call_sign ORDER BY distance ASC) AS row_num
        FROM brutos
        WHERE DATE(timestamp) = '{TARGET_DATE}' AND call_sign != ''
    )
    WHERE row_num = 1 OR row_num = 2
    ORDER BY call_sign, row_num
"""

results = cur.execute(query).fetchall()
results_dicts = [dict(row) for row in results]

print(f"📊 Dados brutos selecionados: {len(results_dicts)} registos")

# Agrupar por call_sign
aircraft_data = {}
for row in results_dicts:
    cs = row['call_sign']
    if cs not in aircraft_data:
        aircraft_data[cs] = []
    aircraft_data[cs].append(row)

print(f"✈️ Aeronaves únicas: {len(aircraft_data)}")
print("\n" + "-" * 60)
print("Comparação: Distância Mínima Bruta vs Interpolada")
print("-" * 60)

comparison = []
for cs, rows in aircraft_data.items():
    # Ordenar por distance (já está, mas garantir)
    rows_sorted = sorted(rows, key=lambda x: x['distance'])
    
    # Melhor distância bruta
    best_before = rows_sorted[0]
    best_distance = best_before['distance']
    
    # Se há pelo menos 2 registos, calcular interpolado
    if len(rows_sorted) >= 2:
        row1 = rows_sorted[0]
        row2 = rows_sorted[1]
        
        # Ponto interpolado
        mid_lat = (row1['latitude'] + row2['latitude']) / 2
        mid_lon = (row1['longitude'] + row2['longitude']) / 2
        mid_alt = (row1['altitude'] + row2['altitude']) / 2
        
        dist_interpol = calculate_3d_distance(
            REF_LAT, REF_LON, REF_ALT,
            mid_lat, mid_lon, mid_alt
        )
        
        comparison.append({
            'call_sign': cs,
            'country': row1['country'],
            'best_before': best_distance,
            'best_interpol': dist_interpol,
            'difference': best_distance - dist_interpol,
            'improvement': (best_distance - dist_interpol) / best_distance * 100 if best_distance > 0 else 0,
            'timestamp_before': row1['timestamp'],
            'timestamp_after': row2['timestamp'] if len(rows_sorted) >= 2 else None
        })

# Mostrar aeronaves com melhoria significativa
comparison_sorted = sorted(comparison, key=lambda x: x['improvement'], reverse=True)

print(f"{'Call Sign':<12} {'País':<15} {'Dist Bruta':<12} {'Dist Interp':<12} {'Melhoria':<10}")
print("-" * 65)
for c in comparison_sorted[:15]:
    print(f"{c['call_sign']:<12} {c['country']:<15} {c['best_before']:<12.1f} {c['best_interpol']:<12.1f} {c['improvement']:<9.1f}%")

print("\n" + "-" * 60)
print(f"📈 Estatísticas:")
print(f"   Aeronaves processadas: {len(comparison)}")
print(f"   Melhoria média: {sum(c['improvement'] for c in comparison)/len(comparison):.1f}%")
print(f"   Melhor melhoria: {max(c['improvement'] for c in comparison):.1f}%")
print("=" * 60)

conn.close()
