from gpiozero import Servo
from time import sleep
import paho.mqtt.client as mqtt

# pip install cv2
# sudo pip install paho-mqtt

def moveX(move):
    # servoX.value = move
    print("X")

def moveY(move):
   # servoY.value = move
   print("Y")

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() - if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("CoreElectronics/x")
    client.subscribe("CoreElectronics/y")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))

    if msg.topic == "CoreElectronics/x":
        moveX(int(msg.payload))

    if msg.topic == "CoreElectronics/y":
        moveY(int(msg.payload))

#
# servoX = Servo(18)
# servoY = Servo(25)

# Create an MQTT client and attach our routines to it.
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("test.mosquitto.org", 1883, 60)

client.loop_forever()