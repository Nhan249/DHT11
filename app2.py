from flask import Flask, render_template, jsonify, request, send_from_directory
import adafruit_dht
import time
import threading
import json
import os
from datetime import datetime
from adafruit_blinka.microcontroller.bcm283x.pin import Pin
from RPLCD.i2c import CharLCD

app = Flask(__name__)

# Configuration
CONFIG_FILE = 'config.json'
DATA_FILE = 'temperature_data.json'
MESSAGES_FILE = 'messages.json'

# Default values
default_config = {
    'temp_threshold_high': 30.0,
    'temp_threshold_low': 20.0,
    'humidity_threshold_high': 80.0,
    'humidity_threshold_low': 40.0,
    'lcd_address': '0x27',  # Địa chỉ I2C mặc định của LCD
    'lcd_enabled': True
}

# Default message templates
default_messages = {
    'temp_high': 'Trời đang nóng! Nhiệt độ cao hơn {threshold}°C.',
    'temp_low': 'Trời đang lạnh! Nhiệt độ thấp hơn {threshold}°C.',
    'humidity_high': 'Độ ẩm cao! Độ ẩm cao hơn {threshold}%.',
    'humidity_low': 'Độ ẩm thấp! Độ ẩm thấp hơn {threshold}%.',
    'all_normal': 'Nhiệt độ và độ ẩm trong ngưỡng an toàn.'
}

# Global variables storing current data
current_data = {
    'temperature': 0,
    'humidity': 0,
    'timestamp': '',
    'alert': False,
    'message': ''
}

# LCD object
lcd = None

# Initialize LCD
def init_lcd():
    global lcd
    try:
        config = read_config()
        if config.get('lcd_enabled', True):
            # Chuyển đổi địa chỉ hex string thành int
            lcd_addr = int(config.get('lcd_address', '0x27'), 16)
            lcd = CharLCD('PCF8574', lcd_addr, cols=16, rows=2)
            lcd.clear()
            lcd.write_string('System Starting...')
            print(f"LCD initialized at address {hex(lcd_addr)}")
            return True
    except Exception as e:
        print(f"LCD initialization error: {e}")
        lcd = None
        return False
    return False

# Update LCD display
def update_lcd(temperature, humidity, alert=False):
    global lcd
    if lcd is None:
        return
    
    try:
        lcd.clear()
        
        # Dòng 1: Nhiệt độ và độ ẩm
        line1 = f"T:{temperature:.1f}C H:{humidity:.1f}%"
        lcd.write_string(line1)
        
        # Dòng 2: Thời gian hoặc cảnh báo
        lcd.cursor_pos = (1, 0)
        if alert:
            # Hiển thị cảnh báo nếu có
            if temperature > read_config()['temp_threshold_high']:
                lcd.write_string("!! NHIET DO CAO!")
            elif temperature < read_config()['temp_threshold_low']:
                lcd.write_string("!! NHIET DO THAP!")
            elif humidity > read_config()['humidity_threshold_high']:
                lcd.write_string("!! DO AM CAO!!")
            elif humidity < read_config()['humidity_threshold_low']:
                lcd.write_string("!! DO AM THAP!!")
        else:
            # Hiển thị thời gian
            current_time = datetime.now().strftime("%H:%M:%S")
            lcd.write_string(f"Time: {current_time}")
            
    except Exception as e:
        print(f"LCD update error: {e}")

# LCD display thread (cập nhật LCD với hiệu ứng cuộn)
def lcd_display_thread():
    global lcd, current_data
    
    if lcd is None:
        return
    
    last_alert_state = False
    alert_blink_count = 0
    
    try:
        while True:
            if current_data['temperature'] != 0:  # Chỉ hiển thị khi có dữ liệu
                current_alert = current_data['alert']
                
                # Nếu có cảnh báo, nhấp nháy LCD
                if current_alert:
                    if alert_blink_count % 2 == 0:
                        update_lcd(current_data['temperature'], current_data['humidity'], True)
                    else:
                        # Xóa màn hình để tạo hiệu ứng nhấp nháy
                        lcd.clear()
                    alert_blink_count += 1
                    time.sleep(1)  # Nhấp nháy mỗi giây
                else:
                    # Hiển thị bình thường
                    update_lcd(current_data['temperature'], current_data['humidity'], False)
                    alert_blink_count = 0
                    time.sleep(2)  # Cập nhật mỗi 2 giây
                
                last_alert_state = current_alert
            else:
                time.sleep(1)
                
    except Exception as e:
        print(f"LCD display thread error: {e}")

# Ensure files exist
def ensure_files_exist():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f)
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
            
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, 'w') as f:
            json.dump(default_messages, f)

# Read configuration
def read_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# Save configuration
def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# Read message templates
def read_messages():
    with open(MESSAGES_FILE, 'r') as f:
        return json.load(f)

# Save message templates
def save_messages(messages):
    with open(MESSAGES_FILE, 'w') as f:
        json.dump(messages, f)

# Save temperature data
def save_temperature_data(data):
    try:
        with open(DATA_FILE, 'r') as f:
            history = json.load(f)
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        history = []
    
    # Limit history storage (e.g., 1000 samples)
    while len(history) >= 1000:
        history.pop(0)
    
    history.append(data)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(history, f)

# Get history data
def get_temperature_history(limit=100):
    try:
        with open(DATA_FILE, 'r') as f:
            history = json.load(f)
            return history[-limit:] if history else []
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        return []

# Generate status message based on current readings
def generate_status_message(temperature, humidity, config):
    messages = read_messages()
    status_message = ""
    alert = False
    
    if temperature > config['temp_threshold_high']:
        status_message += messages['temp_high'].format(threshold=config['temp_threshold_high']) + " "
        alert = True
    elif temperature < config['temp_threshold_low']:
        status_message += messages['temp_low'].format(threshold=config['temp_threshold_low']) + " "
        alert = True
        
    if humidity > config['humidity_threshold_high']:
        status_message += messages['humidity_high'].format(threshold=config['humidity_threshold_high']) + " "
        alert = True
    elif humidity < config['humidity_threshold_low']:
        status_message += messages['humidity_low'].format(threshold=config['humidity_threshold_low']) + " "
        alert = True
        
    if not alert:
        status_message = messages['all_normal']
        
    return status_message.strip(), alert

# Read sensor data function
def read_sensor_data():
    global current_data
    
    # Initialize DHT11 sensor on GPIO4
    dht_device = adafruit_dht.DHT11(Pin(4))
    
    # Number of retries when error occurs
    max_retries = 3
    
    try:
        while True:
            # Read latest configuration
            config = read_config()
            
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Read temperature and humidity
                    temperature = dht_device.temperature
                    humidity = dht_device.humidity
                    
                    if temperature is not None and humidity is not None:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Generate status message
                        status_message, alert = generate_status_message(temperature, humidity, config)
                        
                        # Update current data
                        current_data = {
                            'temperature': float(temperature),
                            'humidity': float(humidity),
                            'timestamp': timestamp,
                            'alert': alert,
                            'message': status_message
                        }
                        
                        # Save data to history (save every 5 minutes)
                        current_minute = datetime.now().minute
                        if current_minute % 5 == 0 and current_minute != getattr(read_sensor_data, 'last_save_minute', -1):
                            save_temperature_data(current_data.copy())
                            # Save last minute to avoid saving multiple times in the same minute
                            read_sensor_data.last_save_minute = current_minute
                        
                        print(f"Temperature: {temperature:.1f}°C, Humidity: {humidity:.1f}%, Alert: {alert}, Message: {status_message}")
                        success = True
                    else:
                        retry_count += 1
                        time.sleep(1)
                
                except RuntimeError as e:
                    print(f"Sensor read error (try {retry_count+1}/{max_retries}): {e}")
                    retry_count += 1
                    # Short wait before retry
                    time.sleep(1)
                except Exception as e:
                    print(f"Unknown error: {e}")
                    retry_count += 1
                    time.sleep(1)
            
            # If all retries failed, wait longer before trying again
            if not success:
                print("Unable to read data after multiple attempts, waiting to try again...")
                time.sleep(5)
            else:
                # Read data every 2 seconds if successful
                time.sleep(2)
            
    except Exception as e:
        print(f"Sensor reading thread error: {e}")
    finally:
        dht_device.exit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/current', methods=['GET'])
def get_current_data():
    # Add cache control header to avoid caching
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
    
    # Check and update configuration
    config = read_config()
    
    if 'temp_threshold_high' in new_config:
        config['temp_threshold_high'] = float(new_config['temp_threshold_high'])
    if 'temp_threshold_low' in new_config:
        config['temp_threshold_low'] = float(new_config['temp_threshold_low'])
    if 'humidity_threshold_high' in new_config:
        config['humidity_threshold_high'] = float(new_config['humidity_threshold_high'])
    if 'humidity_threshold_low' in new_config:
        config['humidity_threshold_low'] = float(new_config['humidity_threshold_low'])
    if 'lcd_address' in new_config:
        config['lcd_address'] = new_config['lcd_address']
    if 'lcd_enabled' in new_config:
        config['lcd_enabled'] = bool(new_config['lcd_enabled'])
    
    save_config(config)
    
    # Khởi tạo lại LCD nếu cấu hình thay đổi
    if 'lcd_address' in new_config or 'lcd_enabled' in new_config:
        init_lcd()
    
    return jsonify({"status": "success", "config": config})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    return jsonify(read_messages())

@app.route('/api/messages', methods=['POST'])
def update_messages():
    new_messages = request.get_json()
    
    # Check and update messages
    messages = read_messages()
    
    for key in new_messages:
        if key in messages:  # Only update existing keys
            messages[key] = new_messages[key]
    
    save_messages(messages)
    return jsonify({"status": "success", "messages": messages})

# API để điều khiển LCD
@app.route('/api/lcd/toggle', methods=['POST'])
def toggle_lcd():
    config = read_config()
    config['lcd_enabled'] = not config.get('lcd_enabled', True)
    save_config(config)
    
    if config['lcd_enabled']:
        init_lcd()
    else:
        global lcd
        if lcd:
            try:
                lcd.clear()
                lcd.close()
            except:
                pass
            lcd = None
    
    return jsonify({"status": "success", "lcd_enabled": config['lcd_enabled']})

@app.route('/api/lcd/message', methods=['POST'])
def send_lcd_message():
    global lcd
    if lcd is None:
        return jsonify({"status": "error", "message": "LCD not initialized"})
    
    data = request.get_json()
    message = data.get('message', '')
    
    try:
        lcd.clear()
        # Chia message thành 2 dòng (16 ký tự mỗi dòng)
        line1 = message[:16]
        line2 = message[16:32] if len(message) > 16 else ""
        
        lcd.write_string(line1)
        if line2:
            lcd.cursor_pos = (1, 0)
            lcd.write_string(line2)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    # Ensure configuration and data files exist
    ensure_files_exist()
    
    # Initialize LCD
    init_lcd()
    
    # Start sensor data reading thread
    sensor_thread = threading.Thread(target=read_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Start LCD display thread
    if lcd is not None:
        lcd_thread = threading.Thread(target=lcd_display_thread, daemon=True)
        lcd_thread.start()
    
    # Start Flask server
    # Use host='0.0.0.0' to make it accessible to all devices on the network
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
