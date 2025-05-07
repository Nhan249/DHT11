import adafruit_dht
import time
from adafruit_blinka.microcontroller.bcm283x.pin import Pin
# Khai báo trực tiếp pin GPIO4
dht_device = adafruit_dht.DHT11(Pin(4))
try:
    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            
            if temperature is not None and humidity is not None:
                print(f"Nhiệt độ: {temperature:.1f}°C, Độ ẩm: {humidity:.1f}%")
            else:
                print("Không thể đọc dữ liệu từ cảm biến!")
                
        except RuntimeError as e:
            print(f"Lỗi đọc: {e}")
            
        time.sleep(2)
        
except KeyboardInterrupt:
    print("Chương trình kết thúc")
finally:
    dht_device.exit()
