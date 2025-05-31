from flask import Flask, render_template, jsonify, request, send_from_directory
import adafruit_dht
import time
import threading
import json
import os
from datetime import datetime
from adafruit_blinka.microcontroller.bcm283x.pin import Pin
from RPLCD.i2c import CharLCD
import smbus2

app = Flask(__name__)

# Configuration
CONFIG_FILE = 'config.json'
DATA_FILE = 'temperature_data.json'
MESSAGES_FILE = 'messages.json'

# LCD Configuration
LCD_I2C_ADDRESS = 0x27  # Địa chỉ I2C của LCD (có thể là 0x3F tùy module)
LCD_COLS = 16  # Số cột LCD
LCD_ROWS = 2   # Số hàng LCD

# Default values
default_config = {
    'temp_threshold_high': 30.0,
    'temp_threshold_low': 20.0,
    'humidity_threshold_high': 80.0,
    'humidity_threshold_low': 40.0
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
        # Khởi tạo LCD với I2C
        lcd = CharLCD(i2c_expander='PCF8574', address=LCD_I2C_ADDRESS, 
                     port=1, cols=LCD_COLS, rows=LCD_ROWS, 
                     dotsize=8, charmap='A02', auto_linebreaks=True)
        
        # Xóa màn hình và hiển thị thông báo khởi động
        lcd.clear()
        lcd.write_string("DHT11 Monitor")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Starting...")
        time.sleep(2)
        
        print("LCD initialized successfully")
        return True
        
    except Exception as e:
        print(f"Failed to initialize LCD: {e}")
        print("Check I2C connection and address")
        return False

# Update LCD display with temperature and humidity
def update_lcd_temp_humidity(temperature, humidity):
    global lcd
    if lcd is None:
        return
        
    try:
        # Xóa màn hình
        lcd.clear()
        
        # Dòng 1: Nhiệt độ
        temp_str = f"Temp: {temperature:.1f}C"
        lcd.write_string(temp_str)
        
        # Dòng 2: Độ ẩm
        lcd.cursor_pos = (1, 0)
        hum_str = f"Hum: {humidity:.1f}%"
        lcd.write_string(hum_str)
        
    except Exception as e:
        print(f"Error updating LCD: {e}")

# Update LCD display with current date and time
def update_lcd_datetime():
    global lcd
    if lcd is None:
        return
        
    try:
        # Lấy thời gian hiện tại
        now = datetime.now()
        
        # Xóa màn hình
        lcd.clear()
        
        # Dòng 1: Ngày tháng năm (dd/mm/yyyy)
        date_str = now.strftime("%d/%m/%Y")
        lcd.write_string(date_str.center(16))
        
        # Dòng 2: Giờ phút giây (hh:mm:ss)
        lcd.cursor_pos = (1, 0)
        time_str = now.strftime("%H:%M:%S")
        lcd.write_string(time_str.center(16))
        
    except Exception as e:
        print(f"Error updating LCD with datetime: {e}")

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
        json.dump(messages, f, ensure_ascii=False)

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

# Check I2C devices
def scan_i2c_devices():
    try:
        bus = smbus2.SMBus(1)  # I2C bus 1 trên Raspberry Pi 5
        devices = []
        
        print("Scanning I2C devices...")
        for address in range(0x03, 0x78):
            try:
                bus.read_byte(address)
                devices.append(hex(address))
                print(f"Found device at address: {hex(address)}")
            except:
                pass
        
        bus.close()
        return devices
        
    except Exception as e:
        print(f"Error scanning I2C: {e}")
        return []

# Read sensor data function
def read_sensor_data():
    global current_data
    
    # Initialize DHT11 sensor on GPIO4
    dht_device = adafruit_dht.DHT11(Pin(4))
    
    # Number of retries when error occurs
    max_retries = 3
    
    # Biến để theo dõi việc hiển thị luân phiên
    display_cycle_counter = 0  # 0: hiển thị temp/humidity, 1: hiển thị thời gian
    last_display_change = time.time()
    display_temp_duration = 10  # Hiển thị nhiệt độ/độ ẩm trong 10 giây
    display_time_duration = 3   # Hiển thị thời gian trong 3 giây
    
    try:
        while True:
            # Read latest configuration
            config = read_config()
            
            current_time = time.time()
            
            # Xử lý chu kỳ hiển thị
            if display_cycle_counter == 0:  # Đang hiển thị nhiệt độ/độ ẩm
                if current_time - last_display_change >= display_temp_duration:
                    # Chuyển sang hiển thị thời gian
                    display_cycle_counter = 1
                    last_display_change = current_time
                    update_lcd_datetime()
                    print("Switching to display date/time")
            else:  # Đang hiển thị thời gian
                if current_time - last_display_change >= display_time_duration:
                    # Chuyển sang hiển thị nhiệt độ/độ ẩm
                    display_cycle_counter = 0
                    last_display_change = current_time
                    print("Switching to display temperature/humidity")
            
            # Đọc dữ liệu từ sensor
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Read temperature and humidity
                    raw_temperature = dht_device.temperature
                    temperature = raw_temperature - 2.0 if raw_temperature is not None else None
                    humidity = dht_device.humidity
                    
                    if temperature is not None and humidity is not None:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Generate status message (vẫn tạo để lưu vào API)
                        status_message, alert = generate_status_message(temperature, humidity, config)
                        
                        # Update current data
                        current_data = {
                            'temperature': float(temperature),
                            'humidity': float(humidity),
                            'timestamp': timestamp,
                            'alert': alert,
                            'message': status_message
                        }
                        
                        # Chỉ cập nhật LCD khi đang trong chu kỳ hiển thị nhiệt độ/độ ẩm
                        if display_cycle_counter == 0:
                            update_lcd_temp_humidity(temperature, humidity)
                        
                        # Save data to history (save every 5 minutes)
                        current_minute = datetime.now().minute
                        if current_minute % 5 == 0 and current_minute != getattr(read_sensor_data, 'last_save_minute', -1):
                            save_temperature_data(current_data.copy())
                            # Save last minute to avoid saving multiple times in the same minute
                            read_sensor_data.last_save_minute = current_minute
                        
                        print(f"Temperature: {temperature:.1f}°C, Humidity: {humidity:.1f}%")
                        
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
                if lcd:
                    try:
                        lcd.clear()
                        lcd.write_string("Sensor Error!")
                        lcd.cursor_pos = (1, 0)
                        lcd.write_string("Retrying...")
                    except:
                        pass
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
    
    save_config(config)
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

# API endpoint để kiểm tra trạng thái LCD
@app.route('/api/lcd/status', methods=['GET'])
def lcd_status():
    return jsonify({"lcd_connected": lcd is not None})

# API endpoint để hiển thị message tùy chỉnh trên LCD
@app.route('/api/lcd/message', methods=['POST'])
def display_custom_message():
    global lcd
    if lcd is None:
        return jsonify({"status": "error", "message": "LCD not connected"})
    
    data = request.get_json()
    message = data.get('message', '')
    duration = data.get('duration', 5)
    
    try:
        lcd.clear()
        if len(message) <= 32:  # Fit in 2 lines
            lines = [message[i:i+16] for i in range(0, len(message), 16)]
            lcd.write_string(lines[0])
            if len(lines) > 1:
                lcd.cursor_pos = (1, 0)
                lcd.write_string(lines[1])
        else:
            # For long messages, display first 32 characters
            lines = [message[i:i+16] for i in range(0, min(len(message), 32), 16)]
            lcd.write_string(lines[0])
            if len(lines) > 1:
                lcd.cursor_pos = (1, 0)
                lcd.write_string(lines[1])
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    print("Starting DHT11 + LCD Monitor...")
    
    # Ensure configuration and data files exist
    ensure_files_exist()
    
    # Scan I2C devices
    i2c_devices = scan_i2c_devices()
    if i2c_devices:
        print(f"Found I2C devices: {i2c_devices}")
    else:
        print("No I2C devices found. Check connections.")
    
    # Initialize LCD
    lcd_initialized = init_lcd()
    if not lcd_initialized:
        print("Warning: LCD not initialized. Continuing without LCD display.")
        print("To fix LCD issues:")
        print("1. Check I2C connections (SDA to GPIO2, SCL to GPIO3)")
        print("2. Enable I2C: sudo raspi-config -> Interface Options -> I2C -> Enable")
        print("3. Install I2C tools: sudo apt install i2c-tools")
        print("4. Check I2C address: sudo i2cdetect -y 1")
        print("5. Common LCD I2C addresses: 0x27, 0x3F")
    
    # Start sensor data reading thread
    sensor_thread = threading.Thread(target=read_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Start Flask server
    # Use host='0.0.0.0' to make it accessible to all devices on the network
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if lcd:
            try:
                lcd.clear()
                lcd.write_string("System stopped")
            except:
                pass
    except Exception as e:
        print(f"Flask server error: {e}")
        if lcd:
            try:
                lcd.clear()
                lcd.write_string("Server Error!")
            except:
                pass
