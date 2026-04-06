const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery();

// Função para calcular distância 3D (haversine + altitude) - RETORNA EM METROS
function calculaDistancia(lat1, lon1, alt1, lat2, lon2, alt2) {
  const R = 6371000; // Raio da Terra em metros
  
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const lat1Rad = lat1 * Math.PI / 180;
  const lat2Rad = lat2 * Math.PI / 180;
  
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.sin(dLon/2) * Math.sin(dLon/2) *
            Math.cos(lat1Rad) * Math.cos(lat2Rad);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  const distanciaHorizontal = R * c;
  
  const distanciaVertical = Math.abs(alt2 - alt1);
  
  return Math.sqrt(distanciaHorizontal * distanciaHorizontal + distanciaVertical * distanciaVertical);
}

// Função para interpolação de timestamps SQL
function interpolateSqlTimestamps(timestamp1, timestamp2, fraction = 0.5) {
    if (!timestamp1 || !timestamp2 || timestamp1 === 'null' || timestamp2 === 'null') {
        return timestamp1 || timestamp2 || null;
    }
    
    try {
        let ts1 = String(timestamp1).replace(' UTC', '');
        let ts2 = String(timestamp2).replace(' UTC', '');
        
        // Remove o 'Z' e 'T' se existirem
        ts1 = ts1.replace('T', ' ').replace('Z', '');
        ts2 = ts2.replace('T', ' ').replace('Z', '');
        
        const date1 = new Date(ts1 + ' UTC');
        const date2 = new Date(ts2 + ' UTC');
        
        if (isNaN(date1.getTime()) || isNaN(date2.getTime())) {
            return timestamp1;
        }
        
        const time1 = date1.getTime();
        const time2 = date2.getTime();
        const interpolatedTime = time1 + fraction * (time2 - time1);
        const interpolatedDate = new Date(interpolatedTime);
        
        if (isNaN(interpolatedDate.getTime())) {
            return timestamp1;
        }
        
        const year = interpolatedDate.getUTCFullYear();
        const month = String(interpolatedDate.getUTCMonth() + 1).padStart(2, '0');
        const day = String(interpolatedDate.getUTCDate()).padStart(2, '0');
        const hours = String(interpolatedDate.getUTCHours()).padStart(2, '0');
        const minutes = String(interpolatedDate.getUTCMinutes()).padStart(2, '0');
        const seconds = String(interpolatedDate.getUTCSeconds()).padStart(2, '0');
        
        // Retorna no formato Python: YYYY-MM-DD HH:MM:SS
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
        
    } catch (error) {
        console.error(`Erro interpolação: ${error.message}`);
        return timestamp1;
    }
}

// Função para interpolação segura
function safeAvg(a, b, fraction = 0.5) {
    let numA = (a === null || a === undefined) ? null : parseFloat(a);
    let numB = (b === null || b === undefined) ? null : parseFloat(b);
    
    if (numA === null && numB === null) return null;
    if (numA === null) return numB;
    if (numB === null) return numA;
    
    return numA + fraction * (numB - numA);
}

// Função principal da Cloud Function
async function voosProx(req, res) {
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
    const { dia, latitudeRef, longitudeRef, altitudeRef } = req.body;

    if (!dia || latitudeRef === undefined || longitudeRef === undefined || altitudeRef === undefined) {
      res.status(400).send('Falta pelo menos um dos parâmetros');
      return;
    }

    const response = await fetch('https://europe-southwest1-nearbyaircraft.cloudfunctions.net/flightPaths?dia=' + dia);
    const voos = await response.json();

    let resultados = [];
    const fractions = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];

    for (const callsign in voos) {
      const records = voos[callsign];
      
      if (!records || records.length === 0) continue;

      let distMin = Infinity;
      let maisProx = null;

      for (let i = 0; i < records.length; i++) {
        const rec = records[i];
        
        // Converter climbing_rate para número se for string
        if (rec.climbing_rate && typeof rec.climbing_rate === 'string') {
          rec.climbing_rate = parseFloat(rec.climbing_rate);
        }
        
        // Verifica o ponto atual
        const dist = calculaDistancia(
          rec.latitude, rec.longitude, rec.altitude,
          latitudeRef, longitudeRef, altitudeRef
        );
        
        if (dist < distMin) {
          distMin = dist;
          maisProx = JSON.parse(JSON.stringify(rec));
          maisProx.distance = dist;
        }
        
        // Interpola com o próximo registo
        if (i < records.length - 1) {
          const nextRec = records[i + 1];
          
          // Converter climbing_rate do próximo para número
          if (nextRec.climbing_rate && typeof nextRec.climbing_rate === 'string') {
            nextRec.climbing_rate = parseFloat(nextRec.climbing_rate);
          }
          
          for (const fraction of fractions) {
            const latInterp = safeAvg(rec.latitude, nextRec.latitude, fraction);
            const lonInterp = safeAvg(rec.longitude, nextRec.longitude, fraction);
            const altInterp = safeAvg(rec.altitude, nextRec.altitude, fraction);
            const velInterp = safeAvg(rec.velocidade, nextRec.velocidade, fraction);
            const climbInterp = safeAvg(rec.climbing_rate, nextRec.climbing_rate, fraction);
            
            const distInterp = calculaDistancia(
              latInterp, lonInterp, altInterp,
              latitudeRef, longitudeRef, altitudeRef
            );
            
            if (distInterp < distMin) {
              distMin = distInterp;
              
              // Interpola o timestamp
              let timestampInterp = interpolateSqlTimestamps(
                rec.timestamp?.value,
                nextRec.timestamp?.value,
                fraction
              );
              
              // Criar objeto interpolado (sem spread operator para evitar sobrescrever timestamp)
              maisProx = {
                call_sign: rec.call_sign,
                country: rec.country,
                timestamp: { value: timestampInterp || rec.timestamp?.value },
                latitude: latInterp,
                longitude: lonInterp,
                altitude: altInterp,
                climbing_rate: climbInterp,
                velocidade: velInterp,
                tipo: rec.tipo,
                distance: distInterp
              };
            }
          }
        }
      }
      
      if (maisProx) {
        // Arredonda climbing_rate para 1 casa decimal
        if (maisProx.climbing_rate !== null && maisProx.climbing_rate !== undefined) {
          maisProx.climbing_rate = Math.round(maisProx.climbing_rate * 10) / 10;
        }
        resultados.push(maisProx);
      }
    }

    // Ordena os resultados por timestamp
    resultados.sort((a, b) => {
      const timeA = a.timestamp?.value;
      const timeB = b.timestamp?.value;
      if (timeA < timeB) return -1;
      if (timeA > timeB) return 1;
      return 0;
    });

    res.status(200).json(resultados);

  } catch (error) {
    console.error(`Erro: ${error.message}`);
    res.status(500).send('Internal Server Error');
  }
}

// Exportar funções para uso em outros módulos e testes
module.exports = {
  voosProx,
  calculaDistancia,
  interpolateSqlTimestamps,
  safeAvg
};