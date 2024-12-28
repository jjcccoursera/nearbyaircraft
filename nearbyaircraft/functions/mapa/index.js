const { BigQuery } = require('@google-cloud/bigquery');
// import { BigQuery } from '@google-cloud/bigquery';

const bigquery = new BigQuery();

exports.flightPaths = async (req, res) => {
  // Set CORS headers for preflight requests
  res.set('Access-Control-Allow-Origin', '*'); // Allow any origin, or specify your domain
  res.set('Access-Control-Allow-Methods', 'GET, OPTIONS'); // Restrict to GET
  res.set('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    // Preflight request handling
    res.status(204).send(''); // No content response
    return;
  }

  if (req.method !== 'GET') {
    // Reject non-GET requests
    res.status(405).send('Method Not Allowed');
    return;
  }

  try {
    // Get the current date and time
    const now = new Date();

    // Determine if we should query yesterday's flights
    const queryTime = new Date().setHours(8, 15, 0, 0); // 8:15 AM in milliseconds
    queryDate = now.toISOString().slice(0, 10);
    if (now.getTime() < queryTime) {
      const yesterday = new Date(now.getTime() - (1000 * 60 * 60 * 24));
      queryDate = yesterday.toISOString().slice(0, 10); // YYYY-MM-DD format
    }
    console.log("Query date:", queryDate);

    console.log("Request URL:", req.url); // Extract query parameters from URL 
    const url = new URL(req.url, `http://${req.headers.host}`); 
    const dia = url.searchParams.get('dia'); 
    console.log("Dia from manually parsed URL:", dia);
    
    // Validate input parameter, if valid update queryDate
    const date = new Date(dia);
    if (date instanceof Date && !isNaN(date) && dia === date.toISOString().split('T')[0]) {
      queryDate = dia;
    }
    
    const query = `
      SELECT
        call_sign,
        timestamp,
        latitude,
        longitude,
        altitude,
        climbing_rate,
        velocidade
      FROM \`nearbyaircraft.voos.brutos\`
      WHERE DATE(timestamp) = '${queryDate}'
      ORDER BY call_sign, timestamp
    `;

    const [rows] = await bigquery.query(query);

    // Group records by call_sign
    const flightPaths = rows.reduce((acc, row) => {
      if (!acc[row.call_sign]) acc[row.call_sign] = [];
      acc[row.call_sign].push(row);
      return acc;
    }, {});

    res.status(200).json(flightPaths);
  } catch (error) {
    console.error('Error fetching flight data:', error);
    res.status(500).send('Error fetching flight data');
  }
};
