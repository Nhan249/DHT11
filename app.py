from flask import Flask, render_template, jsonify, request
import adafruit_dht
import time
import threading
import json
import os
from datetime import datetime
from adafruit_blinka.microcontroller.bcm283x.pin import Pin

app = Flask(__name__)

# Cấu hình
CONFIG_FILE = 'config.json'
DATA_FILE = 'temperature_data.json'

# Giá trị mặc định
default_config = {
    'temp_threshold_high': 30.0,
    'temp_threshold_low': 20.0,
    'humidity_threshold_high': 80.0,
    'humidity_threshold_low': 40.0
}

# Biến toàn cục lưu trữ dữ liệu hiện tại
current_data = {
    'temperature': 0,
    'humidity': 0,
    'timestamp': '',
    'alert': False
}

# Đảm bảo các tệp tồn tại
def ensure_files_exist():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f)
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)

# Đọc cấu hình
def read_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# Lưu cấu hình
def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# Lưu dữ liệu nhiệt độ
def save_temperature_data(data):
    try:
        with open(DATA_FILE, 'r') as f:
            history = json.load(f)
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        history = []
    
    # Giới hạn lịch sử lưu trữ (ví dụ: 1000 mẫu)
    while len(history) >= 1000:
        history.pop(0)
    
    history.append(data)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(history, f)

# Lấy dữ liệu lịch sử
def get_temperature_history(limit=100):
    try:
        with open(DATA_FILE, 'r') as f:
            history = json.load(f)
            return history[-limit:] if history else []
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        return []

# Hàm đọc dữ liệu từ cảm biến DHT11
def read_sensor_data():
    global current_data
    
    # Khởi tạo cảm biến DHT11 trên GPIO4
    dht_device = adafruit_dht.DHT11(Pin(4))
    
    # Số lần thử đọc lại khi gặp lỗi
    max_retries = 3
    
    try:
        while True:
            # Đọc cấu hình mới nhất
            config = read_config()
            
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Đọc nhiệt độ và độ ẩm
                    temperature = dht_device.temperature
                    humidity = dht_device.humidity
                    
                    if temperature is not None and humidity is not None:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Kiểm tra ngưỡng cảnh báo
                        alert = False
                        if (temperature > config['temp_threshold_high'] or 
                            temperature < config['temp_threshold_low'] or
                            humidity > config['humidity_threshold_high'] or
                            humidity < config['humidity_threshold_low']):
                            alert = True
                        
                        # Cập nhật dữ liệu hiện tại
                        current_data = {
                            'temperature': float(temperature),
                            'humidity': float(humidity),
                            'timestamp': timestamp,
                            'alert': alert
                        }
                        
                        # Lưu dữ liệu vào lịch sử (lưu mỗi 5 phút)
                        current_minute = datetime.now().minute
                        if current_minute % 5 == 0 and current_minute != getattr(read_sensor_data, 'last_save_minute', -1):
                            save_temperature_data(current_data.copy())
                            # Lưu phút cuối cùng đã lưu để tránh lưu nhiều lần trong cùng một phút
                            read_sensor_data.last_save_minute = current_minute
                        
                        print(f"Nhiệt độ: {temperature:.1f}°C, Độ ẩm: {humidity:.1f}%, Cảnh báo: {alert}")
                        success = True
                    else:
                        retry_count += 1
                        time.sleep(1)
                
                except RuntimeError as e:
                    print(f"Lỗi đọc cảm biến (lần {retry_count+1}/{max_retries}): {e}")
                    retry_count += 1
                    # Đợi ngắn trước khi thử lại
                    time.sleep(1)
                except Exception as e:
                    print(f"Lỗi không xác định: {e}")
                    retry_count += 1
                    time.sleep(1)
            
            # Nếu tất cả các lần thử đều thất bại, đợi lâu hơn trước khi thử lại
            if not success:
                print("Không thể đọc dữ liệu sau nhiều lần thử, đợi và thử lại...")
                time.sleep(5)
            else:
                # Đọc dữ liệu mỗi 2 giây nếu thành công
                time.sleep(2)
            
    except Exception as e:
        print(f"Lỗi luồng đọc cảm biến: {e}")
    finally:
        dht_device.exit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/current', methods=['GET'])
def get_current_data():
    # Thêm cache control header để tránh cache
    response = jsonify(current_data)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = request.args.get('limit', default=100, type=int)
    return jsonify(get_temperature_history(limit))

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    return jsonify(read_config())

@app.route('/api/thresholds', methods=['POST'])
def update_thresholds():
    new_config = request.get_json()
    
    # Kiểm tra và cập nhật cấu hình
    config = read_config()
    
    if 'temp_threshold_high' in new_config:
        config['temp_threshold_high'] = float(new_config['temp_threshold_high'])
    if 'temp_threshold_low' in new_config:
        config['temp_threshold_low'] = float(new_config['temp_threshold_low'])
    if 'humidity_threshold_high' in new_config:
        config['humidity_threshold_high'] = float(new_config['humidity_threshold_high'])
    if 'humidity_threshold_low' in new_config:
        config['humidity_threshold_low'] = float(new_config['humidity_threshold_low'])
    
    save_config(config)
    return jsonify({"status": "success", "config": config})

if __name__ == '__main__':
    # Đảm bảo tệp cấu hình và dữ liệu tồn tại
    ensure_files_exist()
    
    # Khởi động luồng đọc dữ liệu cảm biến
    sensor_thread = threading.Thread(target=read_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Khởi động server Flask
    # Tắt threaded để tránh xung đột với luồng đọc cảm biến
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
