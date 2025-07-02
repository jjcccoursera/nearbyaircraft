CREATE TABLE brutos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
	timestamp TEXT NOT NULL, 
	call_sign TEXT, 
	country TEXT, 
	distance REAL, 
	altitude REAL, 
	climbing_rate REAL, 
	latitude REAL, 
	longitude REAL, 
	velocidade REAL, 
	tipo INTEGER
);
