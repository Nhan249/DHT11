from flask import Flask, render_template, jsonify, request
import sqlite3
import datetime
import threading
import time
import subprocess
import json
import os

# Khởi tạo Flask app
app = Flask(__name__)

# Đường dẫn tới cơ sở dữ liệu
DB_NAME = 'temperature_data.db'

# Ngưỡng nhiệt độ mặc định và hiện tại
threshold = {
    'min': 18.0,
    'max': 30.0
}

# Biến lưu trữ dữ liệu nhiệt độ hiện tại
current_data = {
    'temperature': None,
    'humidity': None,
    'timestamp': None,
    'threshold_min': threshold['min'],
    'threshold_max': threshold['max']
}

def init_db():
    """Khởi tạo cơ sở dữ liệu"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS temperature_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperature REAL,
        humidity REAL,
        timestamp TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS thresholds (
        id INTEGER PRIMARY KEY,
        min_temp REAL,
        max_temp REAL
    )
    ''')
    
    # Kiểm tra xem đã có ngưỡng nhiệt độ chưa
    cursor.execute('SELECT COUNT(*) FROM thresholds')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO thresholds (id, min_temp, max_temp) VALUES (1, ?, ?)', 
                      (threshold['min'], threshold['max']))
    else:
        # Cập nhật biến threshold từ cơ sở dữ liệu
        cursor.execute('SELECT min_temp, max_temp FROM thresholds WHERE id = 1')
        min_temp, max_temp = cursor.fetchone()
        threshold['min'] = min_temp
        threshold['max'] = max_temp
        current_data['threshold_min'] = min_temp
        current_data['threshold_max'] = max_temp
        
    conn.commit()
    conn.close()

def save_reading(temperature, humidity):
    """Lưu thông số đo được vào cơ sở dữ liệu"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO temperature_readings (temperature, humidity, timestamp) VALUES (?, ?, ?)',
                  (temperature, humidity, timestamp))
    conn.commit()
    conn.close()
    
    # Cập nhật dữ liệu hiện tại
    current_data['temperature'] = temperature
    current_data['humidity'] = humidity
    current_data['timestamp'] = timestamp

def get_latest_readings(limit=50):
    """Lấy dữ liệu nhiệt độ mới nhất từ cơ sở dữ liệu"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT temperature, humidity, timestamp FROM temperature_readings ORDER BY id DESC LIMIT ?', (limit,))
    readings = cursor.fetchall()
    conn.close()
    return readings

def parse_sensor_output(line):
    """Phân tích dữ liệu từ output của chương trình cảm biến"""
    try:
        if "Nhiệt độ:" in line and "Độ ẩm:" in line:
            # Phân tích dữ liệu từ định dạng "Nhiệt độ: XX.X°C, Độ ẩm: XX.X%"
            parts = line.split(',')
            temp_part = parts[0].strip()
            humid_part = parts[1].strip()
            
            temperature = float(temp_part.split(':')[1].replace('°C', '').strip())
            humidity = float(humid_part.split(':')[1].replace('%', '').strip())
            
            return temperature, humidity
    except Exception as e:
        print(f"Lỗi phân tích dữ liệu: {e}")
    
    return None, None

def monitor_sensor():
    """Theo dõi dữ liệu từ chương trình cảm biến"""
    try:
        # Khởi chạy chương trình cảm biến
        process = subprocess.Popen(['python3', 'dht11_sensor.py'], 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                                bufsize=1)
        
        # Đọc dữ liệu liên tục từ output
        for line in process.stdout:
            line = line.strip()
            print(f"Sensor output: {line}")
            
            temperature, humidity = parse_sensor_output(line)
            if temperature is not None and humidity is not None:
                print(f"Parsed: Temp={temperature}°C, Humidity={humidity}%")
                save_reading(temperature, humidity)
                
                # Kiểm tra ngưỡng nhiệt độ
                if temperature < threshold['min']:
                    print(f"CẢNH BÁO: Nhiệt độ {temperature:.1f}°C thấp hơn ngưỡng tối thiểu {threshold['min']}°C")
                elif temperature > threshold['max']:
                    print(f"CẢNH BÁO: Nhiệt độ {temperature:.1f}°C cao hơn ngưỡng tối đa {threshold['max']}°C")
    
    except Exception as e:
        print(f"Lỗi trong quá trình theo dõi cảm biến: {e}")
    finally:
        # Cố gắng đóng process nếu nó vẫn chạy
        if 'process' in locals() and process.poll() is None:
            process.terminate()

@app.route('/')
def index():
    """Trang chủ hiển thị dữ liệu nhiệt độ"""
    return render_template('index.html', thresholds=threshold)

@app.route('/api/temperature')
def get_temperature():
    """API trả về dữ liệu nhiệt độ"""
    readings = get_latest_readings()
    data = []
    for reading in readings:
        data.append({
            'temperature': reading[0],
            'humidity': reading[1],
            'timestamp': reading[2]
        })
    return jsonify(data)

@app.route('/api/current')
def get_current():
    """API trả về dữ liệu hiện tại"""
    return jsonify(current_data)

@app.route('/api/thresholds', methods=['GET', 'POST'])
def manage_thresholds():
    """API quản lý ngưỡng nhiệt độ"""
    global threshold
    
    if request.method == 'POST':
        data = request.get_json()
        min_temp = float(data.get('min', threshold['min']))
        max_temp = float(data.get('max', threshold['max']))
        
        # Cập nhật ngưỡng nhiệt độ trong cơ sở dữ liệu
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE thresholds SET min_temp = ?, max_temp = ? WHERE id = 1', (min_temp, max_temp))
        conn.commit()
        conn.close()
        
        # Cập nhật biến threshold và current_data
        threshold['min'] = min_temp
        threshold['max'] = max_temp
        current_data['threshold_min'] = min_temp
        current_data['threshold_max'] = max_temp
        
        return jsonify({'success': True, 'thresholds': threshold})
    
    return jsonify(threshold)

if __name__ == '__main__':
    # Khởi tạo cơ sở dữ liệu
    init_db()
    
    # Bắt đầu thread theo dõi cảm biến
    sensor_thread = threading.Thread(target=monitor_sensor, daemon=True)
    sensor_thread.start()
    
    # Khởi động ứng dụng Flask
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
