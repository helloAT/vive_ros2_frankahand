"""
Franka Robot Teleoperation with HTC Vive Controller

This script enables teleoperation of a Franka robot using an HTC Vive controller.
It translates the controller's position and orientation into robot joint commands
and provides gripper control functionality.
"""

import rclpy
from rclpy.node import Node
import roboticstoolbox as rtb

import numpy as np
from spatialmath import SE3, SO3

import time
from threading import Thread, Event
import copy

from vive_tracker_client import ViveTrackerClient
from franka_state_interface import FrankaStateInterface
from gripper_interfaces import FrankaGripperActionClient, wait_until_future_complete


class ViveRecieverThread():
    """
    Thread to handle communication with HTC Vive tracker/controller.
    
    This class creates a dedicated thread to receive and process data from
    a specified Vive tracker or controller.
    """
    
    def __init__(self, host, port, tracker_name):
        """
        Initialize the Vive receiver thread.
        
        Args:
            host (str): IP address of the Vive tracker server
            port (int): Port number for communication
            tracker_name (str): Name identifier for the tracker/controller
        """
        self.client = ViveTrackerClient(host=host,
                                        port=port,
                                        tracker_name=tracker_name,
                                        should_record=False)
        self.kill_thread = Event()
        self.client_thread = Thread(target=self.client.run_threaded, args=(self.kill_thread,))

        self.client_thread.start()

    def get_data(self):
        """
        Get the latest data received from the tracker/controller.
        
        Returns:
            The latest tracker message containing position, orientation, and button states
        """
        return self.client.latest_tracker_message

    def kill(self):
        """
        Terminate the receiver thread cleanly.
        """
        self.kill_thread.set()
        self.client_thread.join()


def main(args=None):
    """
    Main function for robot teleoperation.
    
    Sets up ROS2 nodes, interfaces with the robot's state and gripper,
    and runs the teleoperation control loop.
    
    Args:
        args: Command line arguments for ROS2 initialization
    """
    rclpy.init(args=args)
    node_handle = Node('teleoperation_node')

    fsi = FrankaStateInterface(node_handle)
    franka_gripper_client = FrankaGripperActionClient(node_handle)

    spin_func = lambda _: rclpy.spin(node_handle)
    spin_thread = Thread(target=spin_func, args=(0,))
    spin_thread.start()
    time.sleep(1)  # sleep to allow spin thread to get some messages
    
    # gripper homing
    future = franka_gripper_client.do_homing_async()
    wait_until_future_complete(future)
    goal_handle = future.result()
    result_future = goal_handle.get_result_async()
    wait_until_future_complete(result_future)
    gripper_open = True

    panda = rtb.models.DH.Panda()
    panda.tool = SE3()

    # print(fsi.joint_positions)
    initial_joint_pos = np.array(fsi.joint_positions)
    desired_transform_se3 = panda.fkine(initial_joint_pos)
    current_joint_positions = copy.deepcopy(initial_joint_pos)
    joint_solutions = copy.deepcopy(current_joint_positions)

    velocity_scale = 0.4  # m
    rot_vel_scale = 0.3  # deg

    calibration_transformation = np.eye(3)
    
    try:
        HOST, PORT = "192.168.1.103", 8000
        controller = ViveRecieverThread(HOST, PORT, "controller_1")
        # tracker = ViveRecieverThread(HOST, PORT, "tracker_1")
        controller_data = controller.get_data()
        last_pos = None

        while rclpy.ok():
            controller_data = controller.get_data()
            if controller_data is None:
                last_pos = None
                print("Controller not found")
                time.sleep(1)
                continue
            if last_pos is None:
                last_pos = np.array([controller_data.x, controller_data.y, controller_data.z])

            controller_vel = np.array([controller_data.x, 
                                       controller_data.y, 
                                       controller_data.z]) - last_pos

            controller_rot_vel = np.array([controller_data.p, 
                                           controller_data.q, 
                                           controller_data.r])
            controller_rot_vel = np.clip(controller_rot_vel, a_max=1.6, a_min=-1.6)
            controller_rot_vel[(-0.1 <= controller_rot_vel) & (controller_rot_vel <= 0.1)] = 0
            
            if controller_data.menu_button == 1:
                calibration_transformation = controller_data.rotation_as_scipy_transform().as_matrix()
                print(calibration_transformation)
            elif controller_data.trigger == 1:
                cartesian_increment = np.matmul(calibration_transformation, np.array([
                    -controller_vel[0] * velocity_scale,
                    controller_vel[2] * velocity_scale, 
                    controller_vel[1] * velocity_scale,
                ]))
                
                rpy_increment = np.matmul(calibration_transformation, np.array([
                    -controller_rot_vel[1] * rot_vel_scale, 
                    -controller_rot_vel[2] * rot_vel_scale,
                    controller_rot_vel[0] * rot_vel_scale, 
                ]))
                
                desired_transform_se3 = SE3(cartesian_increment) * desired_transform_se3 * SE3.RPY(rpy_increment, order='xyz', unit="deg")
                
                sol = panda.ikine_LM(desired_transform_se3, q0=current_joint_positions)

                if sol.success:
                    joint_solutions = sol.q
                    current_joint_positions = sol.q
                    fsi.publish_joints(joint_solutions.tolist())

            if (controller_data.grip_button == 1) and (result_future.done() or result_future.cancelled()):
                if gripper_open:
                    print("closing gripper")
                    future = franka_gripper_client.do_grasp_async(width=0.035, speed=0.2, epsilon=0.06)
                    if future is not None:
                        wait_until_future_complete(future)
                        goal_handle = future.result()
                        result_future = goal_handle.get_result_async()
                        gripper_open = False
                else:
                    print("opening gripper")
                    future = franka_gripper_client.do_move_async(width=0.08, speed=0.2)
                    if future is not None:
                        wait_until_future_complete(future)
                        goal_handle = future.result()
                        result_future = goal_handle.get_result_async()
                        gripper_open = True

            time.sleep(0.02)
            
            last_pos = np.array([controller_data.x, controller_data.y, controller_data.z])
    finally:
        controller.kill()
        # tracker.kill()


if __name__ == "__main__":
    main()