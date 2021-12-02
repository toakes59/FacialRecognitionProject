# MQTT Publish Demo
# Publish two messages, to two different topics

import paho.mqtt.publish as publish

import paho.mqtt.publish as publish

print("Done")
publish.single("CoreElectronics/x", "Hello", hostname="test.mosquitto.org")
print("Done")
publish.single("CoreElectronics/y", "World!", hostname="test.mosquitto.org")
print("Done")