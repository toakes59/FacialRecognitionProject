import cv2
from gpiozero import Servo
from time import sleep

servoX = Servo(18)
servoY = Servo(25)

faceCascade = cv2.CascadeClassifier("Resources/haarcascade_frontalface_default.xml")

cv2.namedWindow("Video")
cap = cv2.VideoCapture(0)

if cap.isOpened():  # try to get the first frame
    success, frame = cap.read()
else:
    success = False
cap.set(10, 100)

xMiddle, yMiddle, xPrev, yPrev, xMove, yMove = 0
xRatio = cap.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)  # Video capture width
yRatio = cap.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)  # Video Capture height

while success:
    imgGray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = faceCascade.detectMultiScale(imgGray, 1.1, 4)

    # This is for debug
    for (x, y, w, h) in faces:
        # finds center of face
        xMiddle = (x + (w/2))
        yMiddle = (y + (h/2))

        # calculates distance between current center and previous center
        xMove = xMiddle - xPrev
        yMove = yMiddle - yPrev

        # Determines how far x and y servo need to move
        xMove = xMove / xRatio
        yMove = yMove / yRatio

        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

    # debug code
    cv2.imshow("Video", frame)

    success, frame = cap.read()
    key = cv2.waitKey(20)
    if key == 27: # exit on ESC
        break
