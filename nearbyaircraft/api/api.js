import path from 'path';
import express from 'express';
import fetch from 'node-fetch';
import _ from 'lodash'; 
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import { exec } from 'child_process'; 

// Equivalent of __dirname in ESM
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const port = process.env.PORT || 3001; // Use environment variable for port

// Function to calculate 3D distance (same as in api.html)
function calculate3DDistance(lat1, lon1, alt1, lat2, lon2, alt2) {
  const R = 6371e3; // Earth's radius in meters
  const phi1 = lat1 * Math.PI / 180;
  const phi2 = lat2 * Math.PI / 180;
  const deltaphi = (lat2 - lat1) * Math.PI / 180;
  const deltalambda = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(deltaphi / 2) * Math.sin(deltaphi / 2) +
              Math.cos(phi1) * Math.cos(phi2) *
              Math.sin(deltalambda / 2) * Math.sin(deltalambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  const d = R * c; // Distance on the surface
  const altDiff = alt2 - alt1; // Altitude difference

  const distance3D = Math.sqrt(d * d + altDiff * altDiff);
  return distance3D;
}

// Serve static files from the 'www' directory
app.use(express.static(path.join(__dirname, '..', 'www')));

// API endpoint to fetch and process aircraft data
app.get('/api', async (req, res) => {
  
  const { lat, long, alt } = req.query; // Get parameters from query string

  // Validate input parameters
  if (!lat || !long || !alt ||
      isNaN(parseFloat(lat)) || isNaN(parseFloat(long)) || isNaN(parseFloat(alt)) ||
      parseFloat(lat) < -90 || parseFloat(lat) > 90 || parseFloat(long) < -180 || parseFloat(long) > 180) {
    return res.status(400).json({ error: 'Please provide valid latitude, longitude, and altitude values.' });
  }

  const latNum = parseFloat(lat);
  const longNum = parseFloat(long);
  const url = "https://opensky-network.org/api/states/all?lamin=" + (latNum - 0.5) + "&lomin=" + (longNum - 0.5) + "&lamax=" + (latNum + 0.5) + "&lomax=" + (longNum + 0.5);
  
  try {
    console.log(url);
    const response = await fetch(url);
    if (!response.ok) {
      return res.status(response.status).json({ error: `Network response was not ok (status: ${response.status})` });
    }

    const data = await response.json();

    if (!data.states) {
      return res.json({ message: 'No aircraft nearby' });
    }

    const resultados = data.states.map(state => {
      const distance = calculate3DDistance(parseFloat(lat), parseFloat(long), parseFloat(alt), state[6], state[5], state[13]);
      let altit = "n.a.";
      if (state[13] !== null) {
        altit = state[13];
      }
      let rate = "n.a.";
      if (state[11] !== null) {
        rate = state[11].toFixed(1);
      }
      return [state[1], state[2], distance.toFixed(1), altit, rate, state[6], state[5], state[9]*3.6, state[17]];
    });

    const jsonObject = {
        timestamp: Date(data.time * 1000),
        latlongalt: [parseFloat(lat), parseFloat(long), parseFloat(alt)],
        header: ["Callsign", "Country", "Distance", "Altitude", "Climbing", "Latitude", "Longitude", "Velocidade", "Tipo"],
        aircraft: resultados,
        urlsource: "https://opensky-network.org/api/",
        source: "See Matthias Schäfer, Martin Strohmeier, Vincent Lenders, Ivan Martinovic and Matthias Wilhelm. Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research. In Proceedings of the 13th IEEE/ACM International Symposium on Information Processing in Sensor Networks (IPSN), pages 83-94, April 2014."
      };
      
      res.json(jsonObject); // Send the JSON object as the response
      
    } catch (error) {
        console.error(error);
        res.status(500).json({ error: 'An error occurred while fetching data' });
    }
});

// Serve the madrug.html file for the /madrug URL 
app.get('/madrug', (req, res) => { 
  res.setHeader('Cache-Control', 'no-store'); 
  res.sendFile(path.join(__dirname, '..', 'www', 'madrug.html')); 
}); 

// Serve the mapa.html file for the /mapa URL 
app.get('/mapa', (req, res) => { 
  res.setHeader('Cache-Control', 'no-store'); 
  res.sendFile(path.join(__dirname, '..', 'www', 'mapa.html')); 
}); 

// New endpoint to fetch flight path data from Google Cloud Function
app.get('/flightPaths', async (req, res) => {
  try {
    // Extract the 'dia' query parameter from the request 
    let { dia } = req.query; 
    // If 'dia' is not provided, set it to the current date in 'YYYY-MM-DD' format 
    if (!dia) { 
      const now = new Date(); 
      let today = new Date(); 
      // Check if the current time is before 8:15 AM 
      if (now.getHours() < 8 || (now.getHours() === 8 && now.getMinutes() < 15)) { 
        // Set today to yesterday's date 
        today.setDate(today.getDate() - 1); 
      } 
      const year = today.getFullYear(); 
      const month = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-based, so add 1 
      const day = String(today.getDate()).padStart(2, '0');
      /*** const today = new Date(); 
      const year = today.getFullYear(); 
      const month = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-based, so add 1 
      const day = String(today.getDate()).padStart(2, '0'); */
      dia = `${year}-${month}-${day}`; 
    } 
    console.log(133, dia);
    
    // URL of the flightPaths function deployed on Google Cloud with the query parameter 
    const flightPathsUrl = `https://europe-southwest1-nearbyaircraft.cloudfunctions.net/flightPaths?dia=${dia}`; 
    
    // Fetch data from the Cloud Function 
    const response = await fetch(flightPathsUrl);
    
    if (!response.ok) {
      return res.status(response.status).json({ error: `Failed to fetch flight paths: ${response.statusText}` });
    }

    const data = await response.json();
    console.log(data);
    
    // Process the data or return it as-is to the client
    res.json(data); // Return the flight path data in JSON format
  } catch (error) {
    console.error('Error fetching flight paths:', error);
    res.status(500).json({ error: 'Error fetching flight paths' });
  }
});

// Handle other requests
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname,  '..','www', 'index.html'));
}); 

app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
});
