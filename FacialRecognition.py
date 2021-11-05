import cv2

faceCascade = cv2.CascadeClassifier("Resources/haarcascade_frontalface_default.xml")

cv2.namedWindow("Video")
cap = cv2.VideoCapture(0)

if cap.isOpened(): #try to get the first frame
    success, frame = cap.read()
else:
    success = False
cap.set(10, 100)

while success:
    imgGray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = faceCascade.detectMultiScale(imgGray, 1.1, 4)

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

    cv2.imshow("Video", frame)
    success, frame = cap.read()
    key = cv2.waitKey(20)
    if key == 27: # exit on ESC
        break
