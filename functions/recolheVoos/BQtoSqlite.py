import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from google.cloud import bigquery
from google.oauth2 import service_account
import os

# Constants
MAX_BACKUPS = 7
DB_PATH = 'voos.db'
BACKUP_DIR = 'backups'

def rotate_backups():
    """ Keep only the newest MAX_BACKUPS backups """
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(exist_ok=True)
    
    backups = sorted(backup_dir.glob('voos_backup_*.db'), key=os.path.getmtime)
    for old_backup in backups[:-MAX_BACKUPS]:
        old_backup.unlink()
        print(f"Deleted old backup: {old_backup}")

def create_backup():
    """Create a backup with rotation"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(BACKUP_DIR) / f"voos_backup_{timestamp}.db"
    
    shutil.copy2(DB_PATH, backup_path)
    print(f"Created backup: {backup_path}")
    rotate_backups()
    return backup_path

def format_timestamp_for_sqlite(bq_timestamp):
    """Convert ANY BigQuery timestamp to SQLite's expected format"""
    if not bq_timestamp:
        return None
    
    # Handle both string and datetime objects
    if isinstance(bq_timestamp, str):
        try:
            # Parse ISO format (with or without timezone)
            dt = datetime.fromisoformat(bq_timestamp.replace('Z', '+00:00'))
        except ValueError:
            # Fallback for other string formats
            dt = datetime.strptime(bq_timestamp, '%Y-%m-%d %H:%M:%S')
    else:
        # Assume it's a datetime object
        dt = bq_timestamp
    
    # Format exactly as SQLite expects
    return dt.strftime('%Y-%m-%d %H:%M:%S')

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
    
    # Get SQLite dates
    cursor = sqlite_conn.cursor()
    cursor.execute(sqlite_query)
    sqlite_dates = {row[0] for row in cursor.fetchall()}
    
    # Return dates in BigQuery but not in SQLite
    return bq_dates - sqlite_dates

def get_missing_dates(bq_client, sqlite_conn):
    """Returns the earliest missing date or None if up-to-date"""
    # Get latest SQLite date
    cursor = sqlite_conn.execute("SELECT MAX(DATE(timestamp)) FROM brutos")
    last_sync_date = cursor.fetchone()[0]  # Returns YYYY-MM-DD string or None
    
    # Query BigQuery for newer dates
    query = """
        SELECT DATE(MIN(timestamp)) as min_new_date
        FROM `nearbyaircraft.voos.brutos`
        WHERE DATE(timestamp) > COALESCE(@last_date, '1900-01-01')
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("last_date", "DATE", last_sync_date)
        ]
    )
    
    result = bq_client.query(query, job_config=job_config).result()
    min_new_date = next(result).min_new_date  # Returns datetime.date or None
    
    return min_new_date  # Single date instead of full set

def copy_data_for_dates(bq_client, sqlite_conn, cutoff_date):
    """Syncs all data newer than cutoff_date"""
    query = """
        SELECT * FROM `nearbyaircraft.voos.brutos`
        WHERE DATE(timestamp) >= @cutoff_date
        ORDER BY timestamp
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("cutoff_date", "DATE", cutoff_date)
        ]
    )
    
    # Query BigQuery for data on the missing dates
    bq_query = f"""
        SELECT 
            timestamp,
            call_sign,
            country,
            distance,
            altitude,
            CASE 
                WHEN climbing_rate = 'n.a.' THEN NULL
                WHEN SAFE_CAST(climbing_rate AS FLOAT64) IS NULL THEN NULL
                ELSE CAST(climbing_rate AS FLOAT64)
            END AS climbing_rate,
            latitude,
            longitude,
            velocidade,
            tipo
        FROM `nearbyaircraft.voos.brutos`
        WHERE DATE(timestamp) >= @cutoff_date
        ORDER BY timestamp
    """
    
    # Execute the query and get results
    bq_rows = bq_client.query(bq_query, job_config=job_config).result()
    
    # Prepare SQLite insert statement
    insert_sql = """
        INSERT INTO brutos (
            timestamp, call_sign, country, distance, altitude,
            climbing_rate, latitude, longitude, velocidade, tipo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    cursor = sqlite_conn.cursor()
    inserted_rows = 0
    
    # Insert rows into SQLite
    for row in bq_rows:
        # SAFE timestamp conversion
        timestamp_str = format_timestamp_for_sqlite(row.timestamp)
        
        # DEBUG: Uncomment to verify formatting
        print(f"Before: {row.timestamp} -> After: {timestamp_str}")
        
        cursor.execute(insert_sql, (
            timestamp_str,
            row.call_sign,
            row.country,
            row.distance,
            row.altitude,
            row.climbing_rate,
            row.latitude,
            row.longitude,
            row.velocidade,
            row.tipo
        ))
        inserted_rows += 1
    
    sqlite_conn.commit()
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
        # Create backup
        backup_path = create_backup()
        
        # Get sync cutoff
        cutoff_date = get_missing_dates(bq_client, sqlite_conn)
        
        if cutoff_date:
            print(f"Syncing data since {cutoff_date}")
            copy_data_for_dates(bq_client, sqlite_conn, cutoff_date)
        else:
            print("Database is already up-to-date")
            
    except Exception as e:
        print(f"Error: {e}\nBackup available at: {backup_path}")
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    main()