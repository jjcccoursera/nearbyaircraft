const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery();

exports.voosProx = async (req, res) => {
  console.log(`Received request: ${req.method} ${req.url}`);
  res.set('Access-Control-Allow-Origin', 'https://nearbyaircraft.ew.r.appspot.com');
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.set('Access-Control-Max-Age', '86400');
    res.status(204).send('');
    return;
  }

  if (req.method !== 'POST') {
    res.status(405).send('Method Not Allowed');
    return;
  }

  try {
    // Obtém os parâmetros relevantes para o cálculo de distâncias 
    const { dia, latitudeRef, longitudeRef, altitudeRef } = req.body;

    if (!dia || latitudeRef === undefined || longitudeRef === undefined || altitudeRef === undefined) {
      console.log(26, dia, latitudeRef, longitudeRef, altitudeRef);
      res.status(400).send('Falta pelo menos um dos parâmetros', dia, latitudeRef, longitudeRef, altitudeRef);
      return;
    }
    
    // Obtém os voos do dia especificado
    const response = await fetch('https://europe-southwest1-nearbyaircraft.cloudfunctions.net/flightPaths?dia=' + dia); 
    const voos = await response.json();
    
    let resultados = [];
    
    // Calcula as distâncias
    for (const callsign in voos) {
      
      const records = voos[callsign];

      let recAnt = records[0];
      let distMin = calculaDistancia(recAnt.latitude, recAnt.longitude, recAnt.altitude, 
                      latitudeRef, longitudeRef, altitudeRef);
      recAnt.distance = distMin;
      let maisProx = recAnt;

      if (1 < records.length) { // interpola com o seguinte, se existente
            const latMedia = (records[0].latitude + records[1].latitude) / 2;
            const longMedia = (records[0].longitude + records[1].longitude) / 2;
            const altMedia = (records[0].altitude + records[1].altitude) / 2;
            const distInt = calculaDistancia(latMedia, longMedia, altMedia, 
                      latitudeRef, longitudeRef, altitudeRef);
            if (distInt < distMin) {
              distMin = distInt;
              maisProx.timestamp.value = interpolateSqlTimestamps(records[0].timestamp.value, records[1].timestamp.value);
              maisProx.latitude = latMedia; 
              maisProx.longitude = longMedia;
              maisProx.altitude = altMedia;
              maisProx.velocidade = (records[0].velocidade + records[1].velocidade) / 2;
              console.log(62, distInt, maisProx);
            } 
          }  
      
      for (let i=1; i < records.length; i++) {
        const dist = calculaDistancia(records[i].latitude, records[i].longitude, records[i].altitude, 
                      latitudeRef, longitudeRef, altitudeRef);
        
        console.log(53, callsign, records[i].timestamp.value, records[i].altitude, dist);
        if (dist < distMin) { // interpola com registos anterior e posterior, se existente
          distMin = dist; // primeiro o anterior
          maisProx = records[i];
          const latMedia = (records[i].latitude + records[i-1].latitude) / 2;
          const longMedia = (records[i].longitude + records[i-1].longitude) / 2;
          const altMedia = (records[i].altitude + records[i-1].altitude) / 2;
          const distInt = calculaDistancia(latMedia, longMedia, altMedia, 
                      latitudeRef, longitudeRef, altitudeRef);
          if (distInt < distMin) {
            distMin = distInt;
            maisProx.timestamp.value = interpolateSqlTimestamps(records[i].timestamp.value, records[i-1].timestamp.value);
            maisProx.latitude = latMedia; 
            maisProx.longitude = longMedia;
            maisProx.altitude = altMedia;
            maisProx.velocidade = (records[i].velocidade + records[i-1].velocidade) / 2;
            console.log(69, distInt, maisProx);
          } 
          if (i + 1 < records.length) { // depois o seguinte, se existente
            const latMedia = (records[i].latitude + records[i+1].latitude) / 2;
            const longMedia = (records[i].longitude + records[i+1].longitude) / 2;
            const altMedia = (records[i].altitude + records[i+1].altitude) / 2;
            const distInt = calculaDistancia(latMedia, longMedia, altMedia, 
                      latitudeRef, longitudeRef, altitudeRef);
            if (distInt < distMin) {
              distMin = distInt;
              maisProx.timestamp.value = interpolateSqlTimestamps(records[i].timestamp.value, records[i+1].timestamp.value);
              maisProx.latitude = latMedia; 
              maisProx.longitude = longMedia;
              maisProx.altitude = altMedia;
              maisProx.velocidade = (records[i].velocidade + records[i+1].velocidade) / 2;
              console.log(84, distInt, maisProx);
            } 
          }  
        }
        recAnt = records[i];
      }
      maisProx.distance = distMin;
      console.log(75, callsign, '----', distMin, maisProx);
      resultados.push(maisProx);
    }
    console.log(78, resultados);

    // Ordena os resultados por data
    resultados.sort((a, b) => {
      const timeA = a.timestamp.value;
      const timeB = b.timestamp.value;

      if (timeA < timeB) return -1;
      if (timeA > timeB) return 1;
      return 0;
    });
    console.log(89, resultados);
    
    res.status(200).json(resultados);
  
  } catch (error) {
    console.error(`Erro no processamento: ${error.message}`, {
      stack: error.stack,
      body: req.body
    });
    res.status(500).send('Internal Server Error');
  } 

};

const calculaDistancia = (lat1, lon1, alt1, lat2, lon2, alt2) => { 
  const R = 6371000; // Earth's radius in meters 
  
  const toRadians = (degrees) => degrees * Math.PI / 180; 
  
  const phi1 = toRadians(lat1); 
  const phi2 = toRadians(lat2); 
  const deltaPhi = toRadians(lat2 - lat1); 
  const deltaLambda = toRadians(lon2 - lon1); 
  
  const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) 
            + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2); 
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)); 
  
  const distanceHorizontal = R * c; 
  const distanceVertical = alt2 - alt1; 
  
  return Math.sqrt(Math.pow(distanceHorizontal, 2) + Math.pow(distanceVertical, 2)); 
}

function interpolateSqlTimestamps(timestamp1, timestamp2) {
    // Convert SQL timestamps to JavaScript Date objects
    const ts1 = new Date(timestamp1);
    const ts2 = new Date(timestamp2);

    // Calculate the difference between timestamps in milliseconds
    const deltaMilliseconds = ts2 - ts1;

    // Calculate the interpolated timestamp in milliseconds
    const interpolatedMilliseconds = ts1.getTime() + deltaMilliseconds / 2;

    // Convert interpolated milliseconds back to a Date object
    const interpolatedDate = new Date(interpolatedMilliseconds);

    // Format the interpolated timestamp in SQL format
    const formattedDate = interpolatedDate.toISOString().replace('T', ' ').slice(0, 19);

    console.log(133, ts1, ts2, formattedDate);
    
    return formattedDate;
}
