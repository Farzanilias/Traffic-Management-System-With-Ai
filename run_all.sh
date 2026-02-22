#!/usr/bin/env bash
set -euo pipefail

echo "Starting development services for Traffic-Management-System-With-Ai"

# Start MariaDB
echo "Starting MariaDB..."
sudo service mysql start || sudo service mariadb start || true

# Restore DB if missing
DB_EXISTS=$(sudo mysql -u root -proot -e "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = 'TrafficDB';" 2>/dev/null | tail -n +2 || true)
if [ -z "$DB_EXISTS" ]; then
  echo "TrafficDB not found — creating and restoring dump if available..."
  sudo mysql -u root -proot -e "CREATE DATABASE IF NOT EXISTS TrafficDB;" || true
  if [ -f TrafficDB_dump.sql ]; then
    echo "Restoring TrafficDB from TrafficDB_dump.sql"
    sudo mysql -u root -proot TrafficDB < TrafficDB_dump.sql || true
  fi
else
  echo "TrafficDB exists"
fi

# Start backend
echo "Starting Flask backend... (logs -> /tmp/app.log)"
pkill -f 'app.py' || true
nohup python3 app.py > /tmp/app.log 2>&1 &

# Start frontend
echo "Starting React frontend... (logs -> /tmp/frontend.log)"
if [ -d traffic-violation-frontend ]; then
  pushd traffic-violation-frontend >/dev/null
  npm install || true
  pkill -f 'npm start' || true
  nohup npm start > /tmp/frontend.log 2>&1 &
  popd >/dev/null
fi

echo "All services started. Check logs: /tmp/app.log and /tmp/frontend.log"
echo "To stop: pkill -f app.py; pkill -f 'npm start' ; sudo service mysql stop"
