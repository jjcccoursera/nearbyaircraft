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
    const query = `
      SELECT
        call_sign,
        timestamp,
        latitude,
        longitude
      FROM \`nearbyaircraft.voos.brutos\`
      WHERE TIMESTAMP(timestamp) BETWEEN 
        TIMESTAMP(CURRENT_DATE(), "UTC") + INTERVAL 5 HOUR
        AND TIMESTAMP(CURRENT_DATE(), "UTC") + INTERVAL 7 HOUR
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
