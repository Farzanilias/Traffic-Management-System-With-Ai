from flask_bcrypt import Bcrypt
from flask import Flask
import mysql.connector

app = Flask(__name__)
bcrypt = Bcrypt(app)
hash_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')

try:
    db = mysql.connector.connect(host='localhost', user='root', passwd='root', database='TrafficDB')
    cursor = db.cursor()
    cursor.execute("DELETE FROM loginuser WHERE username='admin'")
    cursor.execute("INSERT INTO loginuser (username, password, role) VALUES (%s, %s, %s)", ('admin', hash_pw, 'admin'))
    db.commit()
    print('✅ SUCCESS: Admin user created!')
except Exception as e:
    print(f"❌ Error: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'db' in locals() and db.is_connected(): db.close()
