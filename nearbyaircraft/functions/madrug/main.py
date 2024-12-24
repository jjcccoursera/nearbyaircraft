from google.cloud import bigquery 
from datetime import datetime, timedelta 
import requests 

def convert_datetime_to_string(flights): 
    for flight in flights: 
        for key, value in flight.items(): 
            if isinstance(value, datetime): 
                flight[key] = value.isoformat() 
    return flights
    

def madrug(request): 
    print(f"Request: {request}")
    
    # Add CORS headers to the response
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': 'https://nearbyaircraft.ew.r.appspot.com',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }

    # Handle preflight (OPTIONS) request
    if request.method == 'OPTIONS':
        return ('', 204, headers)

    # Allow only GET requests
    if request.method != 'GET':
        return ('Method not allowed', 405, headers)
    else:
        print('Valid method, GET')
    
    try: # Initialize a BigQuery client 
        client = bigquery.Client() 
        
        # Get the current date and time 
        current_datetime = datetime.now() 
        
        # Determine if we should query yesterday's flights 
        if current_datetime.time() < datetime.strptime('08:15', '%H:%M').time(): 
            query_date = (current_datetime - timedelta(days=1)).strftime('%Y-%m-%d') 
        else: 
            query_date = current_datetime.strftime('%Y-%m-%d') 
            
        # Define the SQL query 
        query = f""" SELECT * FROM (
                        SELECT FORMAT_TIMESTAMP('%d-%m  %H:%M:%S', timestamp, 'UTC-1') AS data, *, 
                        ROW_NUMBER() OVER (PARTITION BY call_sign ORDER BY distance) AS row_num 
                        FROM voos.distancias)
                     WHERE row_num = 1 AND DATE(timestamp) = '{query_date}' AND distance < 3000
                     ORDER BY data; 
                """ 
                
        # Execute the query 
        
        query_job = client.query(query) 
        results = query_job.result() 
        
        # Collect the results 
        flights = [dict(row) for row in results] 
        flights = convert_datetime_to_string(flights)
        return (flights, 200, headers) 
        
    except Exception as e: 
        print(f"Error: {e}") 
        error_response = {'error': 'An unexpected error occurred.', 'details': str(e)}
        return (error_response, 500, headers) 
