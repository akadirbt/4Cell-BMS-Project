import serial    #This is the library for using uart
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  #we need this module for live graph
from matplotlib.figure import Figure
import RPi.GPIO as GPIO
import Adafruit_DHT

# UART setup
uart = serial.Serial('/dev/serial0', 115200, timeout=1) # this is the baud speed for uart communication it means 115200 char per sec 

# Fan setup
FAN_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.output(FAN_PIN, GPIO.LOW)

# DHT11 setup for temp sens.
DHT_SENSOR = Adafruit_DHT.DHT11
DHT_PIN = 19

# Voltage and temp data
v1 = v2 = v3 = v4 = 0.0
temp = 25
time_now = 0 
reading = False # We need a flag for uart comm. start or not

# Lists for cell voltages
v1_list = []
v2_list = []
v3_list = []
v4_list = []
temp_list = []
time_list = []


#-------------------------------------------------------------------------------------------------------

# Read and update values
def update():
    global time_now, reading, v1, v2, v3, v4, temp

    if not reading:     
        return
    
#***************************************************************************
    try:
        for _ in range(6): #read max 69 line data
            line = uart.readline().decode(errors='ignore').strip() #read data convert to UTF-8 text and skip corrupted characters and get rid of sapaces
            if line.startswith("Cell"):      
                parts = line.split(":")                            #Split the part after ":"
                if len(parts) == 2:                                #Control for parts
                    num = int(parts[0].split()[1])                 #The first divided part is divided again and the cell number in the second part is assigned to num.
                    val = float(parts[1].replace("V", "").strip()) #The voltage values ​​in the second part of the divided part are converted to float by deleting the spaces at the end and beginning.
                    if num == 1: v1 = val                          #The converted float values ​​are assigned to the variable according to its cell.
                    elif num == 2: v2 = val
                    elif num == 3: v3 = val
                    elif num == 4: v4 = val
    except:
        print("read error")
#***************************************************************************

    # Temp read
    h, t = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
    if t is not None:
        temp = t

    # Update labels
    label_v1.config(text=f"Cell 1: {v1:.3f} V")
    label_v2.config(text=f"Cell 2: {v2:.3f} V")
    label_v3.config(text=f"Cell 3: {v3:.3f} V")
    label_v4.config(text=f"Cell 4: {v4:.3f} V")
    label_status.config(text="Reading...")


    # Fan status
    if GPIO.input(FAN_PIN):
        fan_label.config(text="FAN: ON", fg="green")
    else:
        fan_label.config(text="FAN: OFF", fg="red")

    # Cells Voltages list using for graph.
    v1_list.append(v1)
    v2_list.append(v2)
    v3_list.append(v3)
    v4_list.append(v4)
    temp_list.append(temp)
    time_list.append(time_now)
    time_now += 1

    draw_graphs()
    root.after(500, update)

#-------------------------------------------------------------------------------------------------------


def draw_graphs():
    graph1.clear()
    graph1.plot(time_list, v1_list, label="Cell 1", color="blue")
    graph1.plot(time_list, v2_list, label="Cell 2", color="green")
    graph1.plot(time_list, v3_list, label="Cell 3", color="red")
    graph1.plot(time_list, v4_list, label="Cell 4", color="purple")
    graph1.set_title("Voltages")
    graph1.legend()
    graph1.grid(True)

    graph2.clear()
    graph2.plot(time_list, temp_list, label="Temp (C)", color="orange")
    graph2.set_title("Temperature")
    graph2.legend()
    graph2.grid(True)

    graph3.clear()
    graph3.plot(time_list, v1_list, color='blue')
    graph3.set_title("Cell 1")

    graph4.clear()
    graph4.plot(time_list, v2_list, color='green')
    graph4.set_title("Cell 2")

    graph5.clear()
    graph5.plot(time_list, v3_list, color='red')
    graph5.set_title("Cell 3")

    graph6.clear()
    graph6.plot(time_list, v4_list, color='purple')
    graph6.set_title("Cell 4")

    canvas.draw()

def start():
    global reading
    reading = True
    update()

def stop():
    global reading
    reading = False

def fan_on():
    GPIO.output(FAN_PIN, GPIO.HIGH)

def fan_off():
    GPIO.output(FAN_PIN, GPIO.LOW)

# GUI
root = tk.Tk()
root.title("Battery GUI")
root.geometry("1300x850")

left = tk.Frame(root)
left.pack(side=tk.LEFT, padx=20, pady=20)
right = tk.Frame(root)
right.pack(side=tk.RIGHT, padx=10, pady=10)

label_v1 = tk.Label(left, text="Cell 1: 0.000 V", font=("Arial", 14))
label_v1.pack()

label_v2 = tk.Label(left, text="Cell 2: 0.000 V", font=("Arial", 14))
label_v2.pack()

label_v3 = tk.Label(left, text="Cell 3: 0.000 V", font=("Arial", 14))
label_v3.pack()

label_v4 = tk.Label(left, text="Cell 4: 0.000 V", font=("Arial", 14))
label_v4.pack()

fan_label = tk.Label(left, text="FAN: OFF", font=("Arial", 12), fg="red")
fan_label.pack()

btn_fan_on = tk.Button(left, text="Open Fan", command=fan_on)
btn_fan_on.pack(pady=2)
btn_fan_off = tk.Button(left, text="Close Fan", command=fan_off)
btn_fan_off.pack(pady=2)

label_status = tk.Label(left, text="Status: Waiting", font=("Arial", 12))
label_status.pack(pady=10)

btn_start = tk.Button(left, text="Start", command=start)
btn_start.pack(pady=2)
btn_stop = tk.Button(left, text="Stop", command=stop)
btn_stop.pack(pady=2)

fig = Figure(figsize=(13, 10), dpi=100)
fig.subplots_adjust(hspace=0.6, wspace=0.4)

graph1 = fig.add_subplot(321)
graph2 = fig.add_subplot(322)
graph3 = fig.add_subplot(323)
graph4 = fig.add_subplot(324)
graph5 = fig.add_subplot(325)
graph6 = fig.add_subplot(326)

canvas = FigureCanvasTkAgg(fig, master=right)  #for showing graphs
canvas.get_tk_widget().pack()                  #for showing graphs

root.mainloop()
GPIO.cleanup()
