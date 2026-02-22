#!/usr/bin/env bash
set -euo pipefail

echo "Running development setup script... (requires sudo)"

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo ./setup_dev.sh"
  exit 1
fi

apt-get update -y
apt-get install -y mariadb-server python3-pip

# Start MariaDB
service mysql start || service mariadb start || true

# Ensure root can authenticate with password 'root' for dev convenience
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'root'; FLUSH PRIVILEGES;" || true

# Create database and import schema
mysql -u root -proot -e "CREATE DATABASE IF NOT EXISTS TrafficDB;"
mysql -u root -proot TrafficDB < /workspaces/Traffic-Management-System-With-Ai/TrafficDB.sql || true

echo "Creating any missing tables and columns (idempotent)..."
cat > /tmp/create_tables_dev.sql <<'SQL'
USE TrafficDB;
CREATE TABLE IF NOT EXISTS Vehicle (
    VehicleID INT PRIMARY KEY AUTO_INCREMENT,
    OwnerName VARCHAR(255) NOT NULL,
    LicensePlate VARCHAR(50) UNIQUE NOT NULL,
    VehicleType VARCHAR(50),
    Contact VARCHAR(20),
    Address TEXT,
    RegisteredBy VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS Violations (
    ViolationID INT PRIMARY KEY AUTO_INCREMENT,
    VehicleID INT,
    DateTime DATETIME DEFAULT CURRENT_TIMESTAMP,
    ViolationType VARCHAR(255),
    FineAmount DECIMAL(10,2),
    Status ENUM('Unpaid','Paid') DEFAULT 'Unpaid',
    Location TEXT,
    ReportedBy VARCHAR(80),
    evidence_image VARCHAR(255),
    violation_hash VARCHAR(64),
    FOREIGN KEY (VehicleID) REFERENCES Vehicle(VehicleID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Fines (
    FineID INT PRIMARY KEY AUTO_INCREMENT,
    ViolationID INT,
    PaymentStatus ENUM('Pending','Completed') DEFAULT 'Pending',
    PaymentMethod VARCHAR(50),
    DatePaid DATETIME,
    Amount DECIMAL(10,2),
    FOREIGN KEY (ViolationID) REFERENCES Violations(ViolationID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    Username VARCHAR(50) UNIQUE NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,
    Role ENUM('admin','user') NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS loginuser (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin','officer','user') NOT NULL DEFAULT 'user'
);
SQL

mysql -u root -proot TrafficDB < /tmp/create_tables_dev.sql || true

echo "Installing Python requirements (if requirements.txt exists)..."
if [ -f requirements.txt ]; then
  pip3 install -r requirements.txt || true
fi

echo "Setup finished. To run the app:
  1) Start backend: python3 app.py
  2) In another terminal: cd traffic-violation-frontend && npm install && npm start
Note: create traffic-violation-frontend/.env with REACT_APP_BACKEND_URL set to your forwarded URL if needed."

exit 0
