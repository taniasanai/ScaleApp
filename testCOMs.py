import serial.tools.list_ports

# List all available COM ports
ports = serial.tools.list_ports.comports()

if not ports:
    print("No COM ports found. Please check your connection.")
else:
    print("Available COM ports:")
    for port in ports:
        print(f"Port: {port.device} - Description: {port.description}")
