Twisted MJPEG Streamer from a watch folder

    twistd -ny run.tac

Add an image tag to a webpage to watch an mjpeg video

    <img src="http://localhost:8080/video.jpg" />

Run an ffmpeg command to stream a file

    ffmpeg -re -i ~/videos/video.mp4 -f image2 -updatefirst 1 -vf fps=fps=24 /var/mjpeg/video.jpg

Watch the video play.

    google-chrome http://localhost:8080/video.jpg
