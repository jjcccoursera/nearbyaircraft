CREATE TABLE distancias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sign TEXT,
    distance REAL,
    timestamp TEXT,
    altitude REAL,
    latitude REAL,
    longitude REAL,
    velocidade REAL,
    tipo INTEGER,
    country TEXT,
    climbing_rate REAL
);