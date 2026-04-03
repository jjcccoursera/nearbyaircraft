import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from google.cloud import bigquery
from google.oauth2 import service_account
import os

# Constants
DB_PATH = 'voos.db'

def format_timestamp_for_bigquery(sqlite_timestamp):
    """Convert SQLite timestamp to BigQuery's expected format: 'YYYY-MM-DD HH:MM:SS UTC'"""
    if not sqlite_timestamp:
        return None
    
    # Handle both string and datetime objects
    if isinstance(sqlite_timestamp, str):
        # SQLite typically stores timestamps as 'YYYY-MM-DD HH:MM:SS'
        dt = datetime.strptime(sqlite_timestamp, '%Y-%m-%d %H:%M:%S')
    else:
        # Assume it's a datetime object
        dt = sqlite_timestamp
    
    # Format exactly as BigQuery expects: 'YYYY-MM-DD HH:MM:SS UTC'
    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')

def get_last_sync_date(sqlite_conn):
    """Get the newest timestamp already in SQLite"""
    cursor = sqlite_conn.execute("SELECT MAX(timestamp) FROM brutos")
    last_date = cursor.fetchone()[0]
    return datetime.fromisoformat(last_date).date() if last_date else None

def get_missing_dates(bq_client, sqlite_conn):
    """Get dates present in BigQuery but missing in SQLite"""
    # Query to get distinct dates from BigQuery
    bq_query = """
        SELECT DISTINCT DATE(timestamp) as date
        FROM `nearbyaircraft.voos.brutos`
        WHERE timestamp IS NOT NULL
        ORDER BY date
    """
    
    # Query to get distinct dates from SQLite
    sqlite_query = """
        SELECT DISTINCT DATE(timestamp) as date
        FROM brutos
        WHERE timestamp IS NOT NULL
        ORDER BY date
    """
    
    # Get BigQuery dates
    bq_dates = {row.date for row in bq_client.query(bq_query)}
    print(bq_dates)
    
    # Get SQLite dates
    cursor = sqlite_conn.cursor()
    cursor.execute(sqlite_query)
    sqlite_dates = {row[0] for row in cursor.fetchall()}
    print(sqlite_dates)
    
    # Return dates in SQLite but not in BigQuery
    return sqlite_dates - bq_dates 

def get_missing_dates(bq_client, sqlite_conn):
    """Returns the earliest missing date or None if up-to-date"""
    # Get latest BigQuery date
    bq_query = """
        SELECT DATE(MAX(timestamp)) as last_sync_date
        FROM `nearbyaircraft.voos.brutos`
    """
    #    WHERE DATE(timestamp) > COALESCE(@last_date, '1900-01-01')
    job_config = bigquery.QueryJobConfig()
    result = bq_client.query(bq_query, job_config=job_config).result()
    last_sync_date = next(result).last_sync_date
    print(last_sync_date)

    # Query SQLite for newer dates
    sqlite_query = """
        SELECT MIN(DATE(timestamp)) as min_new_date
        FROM brutos
        WHERE DATE(timestamp) > """ 
    sqlite_query = sqlite_query + "'" + str(last_sync_date) + "'" 
    print(sqlite_query)
    cursor = sqlite_conn.execute(sqlite_query)
    min_new_date = cursor.fetchone()[0]  # Returns YYYY-MM-DD string or None
    print(min_new_date)
    
    return min_new_date  # Single date instead of full set
 
def copy_data_for_dates(bq_client, sqlite_conn, cutoff_date):
    """Syncs all data newer than cutoff_date"""
    sqlite_query = """
        SELECT * FROM brutos
        WHERE DATE(timestamp) >= '""" 
    sqlite_query = sqlite_query + str(cutoff_date) + "'"
    sqlite_query = sqlite_query + " ORDER BY timestamp "

    sqlite_query = """
        SELECT 
            timestamp,
            call_sign,
            country,
            distance,
            altitude,
            CASE 
                WHEN climbing_rate IS NULL THEN 'n.a.'
                ELSE CAST(climbing_rate AS TEXT)
            END AS climbing_rate,
            latitude,
            longitude,
            velocidade,
            tipo
        FROM brutos
        WHERE DATE(timestamp) >= ?
        ORDER BY timestamp
    """
    print(sqlite_query)

    # Executar query no SQLite
    cursor = sqlite_conn.cursor()
    cursor.execute(sqlite_query, (cutoff_date,))
    sqlite_rows = cursor.fetchall()
    
    # Prepare SQLite insert statement
    rows_to_insert = [
        {
            'timestamp': format_timestamp_for_bigquery(row[0]),
            'call_sign': row[1],
            'country': row[2],
            'distance': row[3],
            'altitude': row[4],
            'climbing_rate': row[5],
            'latitude': row[6],
            'longitude': row[7],
            'velocidade': row[8],
            'tipo': row[9]
        }
        for row in sqlite_rows
    ]

    print(rows_to_insert)
    
    # Inserir em lote no BigQuery
    if rows_to_insert:
        errors = bq_client.insert_rows_json('nearbyaircraft.voos.brutos', rows_to_insert)
        if errors:
            print(f"Errors occurred: {errors}")
        else:
            print(f"Inserted {len(rows_to_insert)} rows into BigQuery")
    else:
        print("No new rows to insert")
        print(f"Inserted {inserted_rows} rows")

def main():
    # Path to your service account key file
    SERVICE_ACCOUNT_JSON = '/home/admin/nearbyaircraft/ignore/nearbyaircraft-49948b6822fb.json'

    # Initialize the BigQuery client
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)
    sqlite_conn = sqlite3.connect('voos.db')
    
    try:
        # Get sync cutoff
        cutoff_date = get_missing_dates(bq_client, sqlite_conn)
        
        if cutoff_date:
            print(f"Syncing data since {cutoff_date}")
            copy_data_for_dates(bq_client, sqlite_conn, cutoff_date)
        else:
            print("Database is already up-to-date")
            
    except Exception as e:
        # print(f"Error: {e}\nBackup available at: {backup_path}")
        print(f"Error: {e}\nBackup available at: ")
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    main()