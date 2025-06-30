#this will hold the sql queries used

use agamadb;
CREATE TABLE metricstable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    metricsdata TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE agents (
    hostname VARCHAR(100) PRIMARY KEY,
    last_seen DATETIME NOT NULL,
    status ENUM('online', 'offline') NOT NULL
);
