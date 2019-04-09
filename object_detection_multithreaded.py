import os
import cv2
import time
import json
import argparse
import numpy as np
import subprocess as sp
import tensorflow as tf

from queue import Queue
from threading import Thread
from utils.app_utils import FPS, HLSVideoStream, WebCamVideoStream, draw_boxes_and_labels
from object_detection.utils import label_map_util


CWD_PATH = os.getcwd()
# List of the strings that is used to add correct label for each box.
PATH_TO_LABELS = "./model/mscoco_label_map.pbtxt"
NUM_CLASSES = 90

# Loading label map
label_map = label_map_util.load_labelmap(PATH_TO_LABELS)
categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=NUM_CLASSES,
                                                            use_display_name=True)
category_index = label_map_util.create_category_index(categories)

def detect_objects(image_np, sess, detection_graph):
    # Expand dimensions since the model expects images to have shape: [1, None, None, 3]
    image_np_expanded = np.expand_dims(image_np, axis=0)
    image_tensor = detection_graph.get_tensor_by_name('image_tensor:0')

    # Each box represents a part of the image where a particular object was detected.
    boxes = detection_graph.get_tensor_by_name('detection_boxes:0')

    # Each score represent how level of confidence for each of the objects.
    # Score is shown on the result image, together with the class label.
    scores = detection_graph.get_tensor_by_name('detection_scores:0')
    classes = detection_graph.get_tensor_by_name('detection_classes:0')
    num_detections = detection_graph.get_tensor_by_name('num_detections:0')

    # Actual detection.
    (boxes, scores, classes, num_detections) = sess.run(
        [boxes, scores, classes, num_detections],
        feed_dict={image_tensor: image_np_expanded})

    # Visualization of the results of a detection.
    rect_points, class_names, class_colors = draw_boxes_and_labels(
        boxes=np.squeeze(boxes),
        classes=np.squeeze(classes).astype(np.int32),
        scores=np.squeeze(scores),
        category_index=category_index,
        min_score_thresh=.5
    )
    return dict(rect_points=rect_points, class_names=class_names, class_colors=class_colors)

def load_model(PATH_TO_CKPT):
    detection_graph = tf.Graph()
    with detection_graph.as_default():
        od_graph_def = tf.GraphDef()
        with tf.gfile.GFile(PATH_TO_CKPT, 'rb') as fid:
            serialized_graph = fid.read()
            od_graph_def.ParseFromString(serialized_graph)
            tf.import_graph_def(od_graph_def, name='')
    session = tf.Session(graph=detection_graph)
    return detection_graph, session

def worker(input_q, output_q):
    # load tensorflow model into memory
    PATH_TO_CKPT = "./model/frozen_inference_graph.pb"
    detection_graph, sess = load_model(PATH_TO_CKPT)
    fps = FPS().start()
    while True:
        fps.update()
        frame = input_q.get()
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        output_q.put(detect_objects(frame_rgb, sess, detection_graph))

    fps.stop()
    sess.close()

if __name__ == "__main__":
    PATH_TO_LABELS = "./model/mscoco_label_map.pbtxt"
    NUM_CLASSES = 90
    parser = argparse.ArgumentParser()
    parser.add_argument('-strin', '--stream-input', dest="stream_in", action='store', type=str, default=None)
    parser.add_argument('-src', '--source', dest='video_source', type=int,
                        default=0, help='Device index of the camera.')
    parser.add_argument('-wd', '--width', dest='width', type=int,
                        default=640, help='Width of the frames in the video stream.')
    parser.add_argument('-ht', '--height', dest='height', type=int,
                        default=480, help='Height of the frames in the video stream.')
    parser.add_argument('-strout','--stream-output', dest="stream_out", help='The URL to send the livestreamed object detection to.')
    args = parser.parse_args()
    input_q = Queue(2)
    output_q = Queue()

    for i in range(2):
        t = Thread(target=worker, args=(input_q, output_q))
        t.daemon = True
        t.start()

    if (args.stream_in):
        video_cap = HLSVideoStream(src=args.stream_in).start()
    else:
        video_cap = WebCamVideoStream(src=args.video_source,
                                   width=args.width,
                                   height=args.height).start()

    fps = FPS().start()
    t = time.time()
    while True:
        frame = video_cap.read()
        input_q.put(frame)

        if output_q.empty():
            pass
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            data = output_q.get()
            rec_points = data['rect_points']
            class_names = data['class_names']
            class_colors = data['class_colors']
            for point, name, color in zip(rec_points, class_names, class_colors):
                cv2.rectangle(frame, (int(point['xmin'] * args.width), int(point['ymin'] * args.height)), (int(point['xmax'] * args.width), int(point['ymax'] * args.height)), color, 3) 
                cv2.rectangle(frame, (int(point['xmin'] * args.width), int(point['ymin'] * args.height)), (int(point['xmin'] * args.width) + len(name[0]) * 6, int(point['ymin'] * args.height) - 10), color, -1, cv2.LINE_AA)
                cv2.putText(frame, name[0], (int(point['xmin'] * args.width), int(point['ymin'] * args.height)), font, 0.3, (0, 0, 0), 1)

            if args.stream_out:
                print ('streaming somewhere else')
            else:
                cv2.imshow('Video', frame)
        fps.update()

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    fps.stop()
    print ('[INFO] elapsed time (total): {:.2f}'.format(fps.elapsed()))
    print ('[INFO] approx. FPS : {:.2f}'.format(fps.fps())) 

    video_cap.stop()
    cv2.destroyAllWindows()




