import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
import time

from threading import Thread, Event
from queue import Queue

from vive_tracker_client import ViveTrackerClient


class ViveRecieverThread():
    def __init__(self, host, port, tracker_name):
        self.client = ViveTrackerClient(host=host,
                                        port=port,
                                        tracker_name=tracker_name,
                                        should_record=False)
        self.kill_thread = Event()
        self.client_thread = Thread(target=self.client.run_threaded, args=(self.kill_thread,))

        self.client_thread.start()

    def get_data(self):
        return self.client.latest_tracker_message

    def kill(self):
        self.kill_thread.set()
        self.client_thread.join()        


def main():
    HOST, PORT = "192.168.1.103", 8000
    controller = ViveRecieverThread(HOST, PORT, "controller_1")
    tracker = ViveRecieverThread(HOST, PORT, "tracker_1")
    
    try:
        while True:
            print(controller.get_data())
            time.sleep(1)
    finally:
        controller.kill()
        tracker.kill()


if __name__ == "__main__":
    main()