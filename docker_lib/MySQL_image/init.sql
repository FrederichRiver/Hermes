-- Example initialization SQL: creates a table and inserts sample data
CREATE DATABASE IF NOT EXISTS stock;
GRANT ALL PRIVILEGES ON stock.* TO 'db1'@'%';
FLUSH PRIVILEGES;

USE stock;

CREATE TABLE IF NOT EXISTS stock.users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL,
  email VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO stock.users (username, email) VALUES
('alice', 'alice@example.com'),
('bob', 'bob@example.com');
