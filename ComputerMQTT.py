import cv2
import paho.mqtt.publish as publish

# pip install cv2
# sudo pip install paho-mqtt

faceCascade = cv2.CascadeClassifier("Resources/haarcascade_frontalface_default.xml")

cv2.namedWindow("Video")
cap = cv2.VideoCapture(0)

if cap.isOpened():  # try to get the first frame
    success, frame = cap.read()
else:
    success = False
cap.set(10, 100)

xMiddle = 0
yMiddle = 0
xPrev = 0
yPrev = 0
xMove = 0
yMove = 0
xRatio = cap.get(3)  # Video capture width
yRatio = cap.get(4)  # Video Capture height

while success:
    imgGray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = faceCascade.detectMultiScale(imgGray, 1.1, 4)

    # This is for debug
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

    # finds center of face
    xMiddle = (x + (w/2))
    yMiddle = (y + (h/2))
    #print("center")

    # calculates distance between current center and previous center
    #xMove = xMiddle - xPrev
    #yMove = yMiddle - yPrev

    # Determines how far x and y servo need to move
    xMove = (xMiddle / xRatio) * 180
    yMove = (yMiddle / yRatio) * 180

    xMove = round(xMove)
    yMove = round(yMove)
    #print("rounded")

    publish.single("faceServo/x", xMove, hostname="test.mosquitto.org")
    publish.single("faceServo/y", yMove, hostname="test.mosquitto.org")
    #print("sent")

    xPrev = xMiddle
    yPrev = yMiddle

    print(xMove)
    print(yMove)

    # debug code
    #cv2.imshow("Video", frame)

    success, frame = cap.read()
    key = cv2.waitKey(20)
    if key == 27: # exit on ESC
        break

cv2.destroyAllWindows()