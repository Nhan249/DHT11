import adafruit_dht
import time
import sqlite3
import datetime
from adafruit_blinka.microcontroller.bcm283x.pin import Pin

# Khai báo trực tiếp pin GPIO4
dht_device = adafruit_dht.DHT11(Pin(4))

# Thông số ngưỡng nhiệt độ
threshold_min = 18.0
threshold_max = 30.0

# Tên cơ sở dữ liệu
DB_NAME = 'temperature_data.db'

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
                      (threshold_min, threshold_max))
    else:
        # Lấy ngưỡng nhiệt độ từ cơ sở dữ liệu
        cursor.execute('SELECT min_temp, max_temp FROM thresholds WHERE id = 1')
        min_temp, max_temp = cursor.fetchone()
        global threshold_min, threshold_max
        threshold_min = min_temp
        threshold_max = max_temp
        
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

def main():
    # Khởi tạo cơ sở dữ liệu
    init_db()
    
    print("Bắt đầu theo dõi nhiệt độ và độ ẩm...")
    try:
        while True:
            try:
                temperature = dht_device.temperature
                humidity = dht_device.humidity
                
                if temperature is not None and humidity is not None:
                    print(f"Nhiệt độ: {temperature:.1f}°C, Độ ẩm: {humidity:.1f}%")
                    
                    # Lưu dữ liệu vào cơ sở dữ liệu
                    save_reading(temperature, humidity)
                    
                    # Kiểm tra ngưỡng nhiệt độ
                    if temperature < threshold_min:
                        print(f"CẢNH BÁO: Nhiệt độ {temperature:.1f}°C thấp hơn ngưỡng tối thiểu {threshold_min}°C")
                    elif temperature > threshold_max:
                        print(f"CẢNH BÁO: Nhiệt độ {temperature:.1f}°C cao hơn ngưỡng tối đa {threshold_max}°C")
                else:
                    print("Không thể đọc dữ liệu từ cảm biến!")
                    
            except RuntimeError as e:
                print(f"Lỗi đọc: {e}")
                
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("Chương trình kết thúc")
    finally:
        dht_device.exit()

if __name__ == "__main__":
    main()
