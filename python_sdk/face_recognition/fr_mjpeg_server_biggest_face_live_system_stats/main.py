"""Main Face Recognition Processor"""
from trueface.recognition import FaceRecognizer
from trueface.video import VideoStream, QVideoStream
from trueface.server import create_server
import cv2
import time
import configparser
from multiprocessing import Process, Queue, Value
import traceback
import requests

#configuration
config = configparser.ConfigParser()
config.read('config.ini')
url = config['config']['url']
url = int(url) if len(url) == 1 else url
threshold = config['config']['threshold']
webhook_url = config['config']['webhook_url']
webhook_holdout = config['config']['webhook_holdout']
license = config['config']['license']

#initialize FR class
fr = FaceRecognizer(ctx='gpu',
                   fd_model_path='./fd_model',
                   fr_model_path='./model-tfv2/model.trueface', 
                   params_path='./model-tfv2/model.params',
                   gpu=0,
                   license=license)


#start camera capture
vcap = VideoStream(src=url).start()

  #webhook function
def webhook(identity):
    """performs webhook"""
    data = {
      "identity":identity,
      "timestamp":time.time()
    }
    r = requests.post(webhook_url, json=data)
    print(r.text)

#simple streaming server
def start_server(port, q):
    """starts a simple MJPEG streaming server"""
    app = create_server()
    app.config['q'] = q
    p = Process(target=app.run, kwargs={"host":'0.0.0.0',"port":port, "threaded":True})
    p.daemon = True
    p.start()


q = Queue(maxsize=10)
start_server(8086, q)

#last webhook timestamp for holdout
last_webhook_timestamp = 0

#main loop
while(True):
    try:
        frame = vcap.read()
        timestamp = time.time()
        face = fr.find_biggest_face(frame, return_chips=True, chip_size=112, padding=0.2, return_binary=True)
        if face:
            identity = fr.identify(face[0]['chip'], threshold=float(threshold), collection='./trueface-collection.npz')
            print identity
            if identity['predicted_label']:
                fr.draw_label(frame, 
                             (int(face[0]['bounding_box'][0]), 
                              int(face[0]['bounding_box'][1])), 
                             identity['predicted_label'], 2, 2)
                if int(config['config']['webhook']) == 1 and \
                  time.time() - last_webhook_timestamp > int(webhook_holdout):
                    p = Process(target=webhook, args=(identity,))
                    p.daemon = True
                    p.start()
                    last_webhook_timestamp = time.time()
            fr.draw_box(frame, face[0]['bounding_box'])

        print 'face detect time', time.time() - timestamp
        if q.full():
            q.get()
        q.put(frame)
    except Exception as e:
      print traceback.format_exc()