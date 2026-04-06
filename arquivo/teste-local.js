// test-local.js
const { voosProx } = require('./index.js');

// Simula a requisição
const req = {
  method: 'POST',
  body: {
    dia: '2026-04-05',
    latitudeRef: 41.163484,
    longitudeRef: -8.66947,
    altitudeRef: 30
  }
};

// Simula a resposta
const res = {
  set: () => {},
  status: (code) => {
    return {
      send: (msg) => {
        console.log(`Status ${code}:`, msg);
      },
      json: (data) => {
        console.log(`\n=== RESULTADOS (${data.length} voos) ===\n`);
        data.forEach((voo, idx) => {
          console.log(`${idx+1}. ${voo.call_sign?.trim()} | dist=${voo.distance?.toFixed(0)}m | time=${voo.timestamp?.value} | alt=${voo.altitude?.toFixed(0)}m | climb=${voo.climbing_rate}`);
        });
        
        // Mostrar detalhes do primeiro voo para comparação
        if (data.length > 0) {
          console.log(`\n=== DETALHES PRIMEIRO VOO ===`);
          console.log(JSON.stringify(data[0], null, 2));
        }
      }
    };
  }
};

// Executa a função
console.log('=== TESTE LOCAL ===\n');
console.log('Parâmetros:', req.body);
console.log('\nA processar...\n');

voosProx(req, res);