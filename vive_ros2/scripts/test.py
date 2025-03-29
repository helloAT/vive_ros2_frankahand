from vive_tracker_client import ViveTrackerClient
from threading import Thread, Event
import time

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

HOST, PORT = "192.168.1.103", 8000
controller = ViveRecieverThread(HOST, PORT, "controller_1")
time.sleep(5)

l = []

start = time.time()
for i in range(1000 * 100):
    d = controller.get_data()
    # print(d)
    l.append(controller.get_data())
end = time.time()

print(end - start)
print(l.count(None))