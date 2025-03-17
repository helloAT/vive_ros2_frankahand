import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data


class ViveStateSubscriber():
    def __init(self, node_handle):
        self.subscription = node_handle.create_subscription(
            
        )