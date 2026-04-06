// test-debug.js
const { calculaDistancia, safeAvg, interpolateSqlTimestamps } = require('./index.js');

// Função para testar um voo específico manualmente
async function testSpecificFlight() {
  console.log('=== TESTE ESPECÍFICO DE VOO ===\n');
  
  // Busca os dados reais
  const response = await fetch('https://europe-southwest1-nearbyaircraft.cloudfunctions.net/flightPaths?dia=2026-04-05');
  const voos = await response.json();
  
  // Procurar o callsign com ou sem espaços
  let callsign = null;
  for (const key in voos) {
    if (key.trim() === 'AEA37KP') {
      callsign = key;
      break;
    }
  }
  
  if (!callsign) {
    console.log('Voo AEA37KP não encontrado');
    console.log('Callsigns disponíveis:', Object.keys(voos).slice(0, 10));
    return;
  }
  
  const records = voos[callsign];
  const ref = { lat: 41.163484, lon: -8.66947, alt: 30 };
  const fractions = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
  
  console.log(`Voo: ${callsign}`);
  console.log(`Pontos: ${records.length}\n`);
  
  // Mostrar timestamps originais
  console.log('=== TIMESTAMPS ORIGINAIS ===');
  records.forEach((r, i) => {
    console.log(`[${i}] ${r.timestamp?.value} | lat=${r.latitude} | lon=${r.longitude} | alt=${r.altitude} | climb=${r.climbing_rate}`);
  });
  
  console.log('\n=== CÁLCULO DE DISTÂNCIAS ===');
  
  let distMin = Infinity;
  let melhor = null;
  
  for (let i = 0; i < records.length; i++) {
    const rec = records[i];
    
    // Converter climbing_rate para número se for string
    if (rec.climbing_rate && typeof rec.climbing_rate === 'string') {
      rec.climbing_rate = parseFloat(rec.climbing_rate);
    }
    
    // Ponto original
    const dist = calculaDistancia(rec.latitude, rec.longitude, rec.altitude, ref.lat, ref.lon, ref.alt);
    console.log(`[${i}] Original: dist=${dist.toFixed(0)}m | time=${rec.timestamp?.value}`);
    
    if (dist < distMin) {
      distMin = dist;
      melhor = { 
        tipo: 'original', 
        indice: i, 
        dist, 
        timestamp: rec.timestamp?.value,
        latitude: rec.latitude,
        longitude: rec.longitude,
        altitude: rec.altitude,
        climbing_rate: rec.climbing_rate,
        velocidade: rec.velocidade
      };
    }
    
    // Interpolações com próximo
    if (i < records.length - 1) {
      const next = records[i + 1];
      
      // Converter climbing_rate do próximo
      if (next.climbing_rate && typeof next.climbing_rate === 'string') {
        next.climbing_rate = parseFloat(next.climbing_rate);
      }
      
      for (const frac of fractions) {
        const lat = safeAvg(rec.latitude, next.latitude, frac);
        const lon = safeAvg(rec.longitude, next.longitude, frac);
        const alt = safeAvg(rec.altitude, next.altitude, frac);
        const climb = safeAvg(rec.climbing_rate, next.climbing_rate, frac);
        const vel = safeAvg(rec.velocidade, next.velocidade, frac);
        const distInterp = calculaDistancia(lat, lon, alt, ref.lat, ref.lon, ref.alt);
        
        const timestampInterp = interpolateSqlTimestamps(
          rec.timestamp?.value,
          next.timestamp?.value,
          frac
        );
        
        if (distInterp < distMin) {
          distMin = distInterp;
          melhor = { 
            tipo: 'interpolado', 
            indice: i, 
            frac, 
            dist: distInterp,
            timestamp: timestampInterp,
            latitude: lat,
            longitude: lon,
            altitude: alt,
            climbing_rate: climb,
            velocidade: vel
          };
        }
        
        // Mostrar apenas algumas frações
        if (frac === 0.1 || frac === 0.5 || frac === 0.9) {
          console.log(`  Interp [${i}-${i+1}] frac=${frac}: dist=${distInterp.toFixed(0)}m | time=${timestampInterp}`);
        }
      }
    }
  }
  
  console.log('\n=== MELHOR PONTO ENCONTRADO ===');
  console.log(`Tipo: ${melhor.tipo}`);
  if (melhor.tipo === 'interpolado') {
    console.log(`Entre índices: ${melhor.indice} e ${melhor.indice + 1}`);
    console.log(`Fração: ${melhor.frac}`);
  } else {
    console.log(`Índice: ${melhor.indice}`);
  }
  console.log(`Distância: ${melhor.dist.toFixed(0)}m`);
  console.log(`Timestamp: ${melhor.timestamp}`);
  console.log(`Latitude: ${melhor.latitude}`);
  console.log(`Longitude: ${melhor.longitude}`);
  console.log(`Altitude: ${melhor.altitude?.toFixed(0)}m`);
  console.log(`Climbing rate: ${typeof melhor.climbing_rate === 'number' ? melhor.climbing_rate.toFixed(1) : melhor.climbing_rate}`);
  console.log(`Velocidade: ${melhor.velocidade?.toFixed(0)}km/h`);
  
  // Comparar com o que o Python retornaria
  console.log('\n=== COMPARAÇÃO COM PYTHON (esperado) ===');
  console.log(`Python esperado:`);
  console.log(`  Timestamp: 2026-04-05 05:33:40`);
  console.log(`  Distância: 1018m`);
  console.log(`  Altitude: 572m`);
  console.log(`  Climbing rate: -4.1`);
  
  console.log('\n=== DIFERENÇAS ===');
  if (melhor.timestamp !== '2026-04-05 05:33:40') {
    console.log(`⚠️ Timestamp diferente: ${melhor.timestamp} vs 2026-04-05 05:33:40`);
  }
  if (Math.abs(melhor.dist - 1018) > 1) {
    console.log(`⚠️ Distância diferente: ${melhor.dist.toFixed(0)}m vs 1018m`);
  }
  if (Math.abs(melhor.altitude - 572) > 1) {
    console.log(`⚠️ Altitude diferente: ${melhor.altitude?.toFixed(0)}m vs 572m`);
  }
  if (melhor.climbing_rate && Math.abs(melhor.climbing_rate - (-4.1)) > 0.1) {
    console.log(`⚠️ Climbing rate diferente: ${melhor.climbing_rate?.toFixed(1)} vs -4.1`);
  }
  
  // Verificar timestamps originais em detalhe
  console.log('\n=== VERIFICAÇÃO DE TIMESTAMPS ORIGINAIS ===');
  for (let i = 0; i < Math.min(records.length, 5); i++) {
    const ts = records[i].timestamp?.value;
    console.log(`[${i}] Original: "${ts}"`);
    
    if (ts) {
      const cleanTs = ts.replace(' UTC', '').replace(' ', 'T') + 'Z';
      const date = new Date(cleanTs);
      console.log(`      → Unix timestamp: ${date.getTime()} (${date.toISOString()})`);
    }
  }
}

// Executar
testSpecificFlight()
  .then(() => {
    console.log('\n✅ Teste concluído');
    process.exit(0);
  })
  .catch(err => {
    console.error('❌ Erro:', err);
    process.exit(1);
  });