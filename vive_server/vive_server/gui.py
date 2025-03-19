from abc import ABC, abstractmethod
import queue
from pathlib import Path
import math

import dearpygui.dearpygui as dpg

from models import Configuration

RED = [255, 0, 0, 255]
PURPLE = [128, 0, 128, 255]
GREEN = [0, 255, 0, 255]
BLUE = [0, 0, 255, 255]
GREY = [128, 128, 128, 255]
GRIDLINES = [128, 128, 128, 50]
BLACK = [0, 0, 0, 255]

TRACKER_COLOR = [0, 255, 255, 255]
REFERENCE_COLOR = [255, 0, 255, 255]
CONTROLLER_COLOR = [255, 255, 255, 255]


class Page(ABC):
    def __init__(self, name: str, gui_manager):
        self.name = name
        self.gui_manager = gui_manager

    def show(self) -> bool:
        if not dpg.does_item_exist(self.name):
            with dpg.window(label=self.name, autosize=True, tag=self.name) as window:
                dpg.set_item_callback(window, self.clear)
            return True
        return False

    @abstractmethod
    def update(self, system_state: dict):
        pass

    def clear(self, sender, data):
        dpg.delete_item(self.name)


# render 3d scene from the top down (size of dot represent the scale on the z)
# Moving in and out changes the x and y axis by changing the virtual camera configuration
class Scene:
    def __init__(self, width=1000, height=500, name="scene"):
        self.name = name
        self.width = width
        self.height = height
        self.scale_x, self.scale_y = self.width / 10, self.width / 10
        self.z_scale, self.z_offset = 10, 1.0

        self.center = [self.width / 2, self.height / 2]
        self.bottom_left = [self.width, self.height]
        self.wheel_callback_id = None

    def add(self):
        dpg.add_spacing()
        with dpg.drawlist(width=self.width, height=self.height, tag=self.name):
            pass
        self.wheel_callback_id = dpg.add_mouse_wheel_handler(callback=self.mouse_wheel)

    def real_pose_from_pixels(self, point):
        return [(point[0] - self.center[0]) / self.scale_x, (point[1] - self.center[1]) / self.scale_y]

    def real_pose_to_pixels(self, point):
        return [(point[0] * self.scale_x + self.center[0]), (point[1] * self.scale_y + self.center[1])]

    def mouse_wheel(self, sender, data):
        if dpg.get_active_window() == dpg.get_item_parent(self.name):
            self.scale_x, self.scale_y = self.scale_x + data * 3, self.scale_y + data * 3
            self.z_scale += data / 2

    def draw_tracker(self, tracker_msg):
        point = self.real_pose_to_pixels([tracker_msg.x, tracker_msg.y])
        diameter = abs(tracker_msg.z) + self.z_offset * self.z_scale
        dpg.draw_text(pos=[point[0], point[1] - diameter - 15], text=f'{tracker_msg.device_name}', color=TRACKER_COLOR,
                  size=13, parent=self.name, tag=f"{tracker_msg.device_name}txt")
        dpg.draw_circle(center=point, radius=diameter, color=TRACKER_COLOR, fill=TRACKER_COLOR,
                    parent=self.name, tag=f"{tracker_msg.device_name}dot")
        _, _, yaw = tracker_msg.rotation_as_scipy_transform().as_euler("xyz")
        radius = 20 + diameter / 2
        pt2 = [point[0] - radius * math.cos(yaw), point[1] + radius * math.sin(yaw)]
        dpg.draw_line(p1=point, p2=pt2, color=PURPLE, thickness=3, parent=self.name, tag=f"{tracker_msg.device_name}line")

    def draw_reference(self, reference_msg):
        pass

    def draw_scales(self):
        tick_h = 5
        for x in range(0, self.width, 50):
            dpg.draw_line(p1=[x, self.height], p2=[x, 0], color=GRIDLINES, thickness=1, parent=self.name, tag=f"{x}xgridline")
            dpg.draw_line(p1=[x, self.height], p2=[x, self.height - tick_h], color=GREY, thickness=1, parent=self.name, tag=f"{x}xtick")
            x_real = self.real_pose_from_pixels([x, 0])[0]
            dpg.draw_text(pos=[x, self.height - tick_h - 20], text=f'{round(x_real, 1)}m', color=GREY, size=13,
                      parent=self.name, tag=f"{x}xticktext")
        for y in range(0, self.height, 50):
            dpg.draw_line(p1=[0, y], p2=[self.width, y], color=GRIDLINES, thickness=1, parent=self.name, tag=f"{y}ygridline")
            dpg.draw_line(p1=[0, y], p2=[tick_h, y], color=GREY, thickness=1, parent=self.name, tag=f"{y}ytick")
            y_real = self.real_pose_from_pixels([0, y])[1]
            dpg.draw_text(pos=[tick_h + 5, y - 2], text=f'{round(y_real, 1)}m', color=GREY, size=13,
                      parent=self.name, tag=f"{y}yticktext")

    def add_axes(self):
        length = 40
        dpg.draw_line(p1=self.center, p2=[self.center[0], self.center[1] + length], color=GREEN, thickness=3, parent=self.name, tag="axis1")
        dpg.draw_line(p1=self.center, p2=[self.center[0] + length, self.center[1]], color=RED, thickness=3, parent=self.name, tag="axis2")
        dpg.draw_circle(center=self.center, radius=4, color=BLUE, fill=BLUE,
                    parent=self.name, tag="axis3")

    def draw(self, device_state):
        dpg.delete_item(self.name, children_only=True)
        dpg.push_container_stack(self.name)
        dpg.draw_rectangle(pmin=[0, 0], pmax=self.bottom_left, color=BLACK, fill=BLACK, tag="backround")
        self.draw_scales()
        self.add_axes()
        for device in device_state:
            if 'tracker' in device:
                if device_state[device] is not None:
                    self.draw_tracker(device_state[device])
        dpg.pop_container_stack()


class DevicesPage(Page):
    def __init__(self, gui_manager, name="devices"):
        super().__init__(name, gui_manager)
        self.devices_shown = []

    def update(self, system_state):
        for device in system_state:
            serial = system_state[device].serial_num
            if device not in self.devices_shown:
                self.devices_shown.append(device)
                dpg.add_input_text(label=f"{device}:{serial}##name", default_value=system_state[device].device_name,
                               parent=self.name, on_enter=True, callback=self.update_device_name, 
                               user_data=(device, serial))
                dpg.add_text(f"{serial}_txt", parent=self.name, color=GREY)
            else:
                dpg.set_value(f"{serial}_txt", f"x: {round(system_state[device].x, 2)}, "
                                           f"y: {round(system_state[device].y, 2)}, "
                                           f"z: {round(system_state[device].z, 2)}")

    def update_device_name(self, sender, data):
        device, serial = data
        new_name = dpg.get_value(f"{device}:{serial}##name")
        config = self.gui_manager.get_config()
        config.name_mappings[serial] = new_name
        self.gui_manager.update_config(config)

    def clear(self, sender, data):
        super(DevicesPage, self).clear(sender, data)
        self.devices_shown = []


# Calibration page includes scene with special configuration
class CalibrationPage(Page):
    def __init__(self, name: str, gui_manager):
        super(CalibrationPage, self).__init__(name, gui_manager)
        self.trackers = []
        self.origin_tracker = None
        self.pos_x_tracker = None
        self.pos_y_tracker = None

    def show(self):
        if super(CalibrationPage, self).show():
            dpg.add_text("Please select a tracker for each axis. Available trackers are listed below for convenience:", parent=self.name)
            dpg.add_spacing(parent=self.name)
            dpg.add_text("trackers##calibration", default_value=str(self.trackers), parent=self.name)
            dpg.add_input_text(label="origin##calibration", default_value="", callback=self.update_origin, parent=self.name)
            dpg.add_input_text(label="+x##calibration", default_value="", callback=self.update_pos_x, parent=self.name)
            dpg.add_input_text(label="+y##calibration", default_value="", callback=self.update_pos_y, parent=self.name)
            dpg.add_button(label="Start calibration", callback=self.run_calibration, parent=self.name)
            return True
        return False

    def update_origin(self, sender, data):
        self.origin_tracker = dpg.get_value("origin##calibration")

    def update_pos_x(self, sender, data):
        self.pos_x_tracker = dpg.get_value("+x##calibration")

    def update_pos_y(self, sender, data):
        self.pos_y_tracker = dpg.get_value("+y##calibration")

    def run_calibration(self, sender, data):
        # verify valid input (trackers + unique)
        if self.origin_tracker in self.trackers and \
                self.pos_y_tracker in self.trackers and \
                self.pos_x_tracker in self.trackers and \
                self.origin_tracker != self.pos_x_tracker and \
                self.origin_tracker != self.pos_y_tracker and \
                self.pos_x_tracker != self.pos_y_tracker:
            self.gui_manager.call_calibration(self.origin_tracker, self.pos_x_tracker, self.pos_y_tracker)
        else:
            dpg.log_warning("Invalid tracker entered for calibration")

    def update(self, system_state: dict):
        trackers = []
        for key in system_state:
            if "tracker" in key:
                trackers.append(system_state[key].device_name)
        if len(trackers) > len(self.trackers):
            self.trackers = trackers
            dpg.set_value("trackers##calibration", str(trackers))

    def clear(self, sender, data):
        super(CalibrationPage, self).clear(sender, data)
        self.trackers = []


class TestCalibrationPage:
    def __init__(self):
        pass


class ConfigurationPage(Page):
    def show(self):
        super(ConfigurationPage, self).show()

    def update(self, system_state):
        config = self.gui_manager.get_config()
        if config is not None:
            config_dict = dict(self.gui_manager.get_config())
            for value in config_dict:
                if not dpg.does_item_exist(f"{value}##config"):
                    dpg.add_input_text(label=f"{value}##config", default_value=str(config_dict[value]),
                                   on_enter=True, callback=self.update_config_entry,
                                   user_data=value, parent=self.name)
                else:
                    dpg.set_value(f"{value}##config", str(config_dict[value]))

    def update_config_entry(self, sender, data):
        config = self.gui_manager.get_config()


class VisualizationPage:
    def __init__(self, gui_manager):
        self.gui_manager = gui_manager
        self.scene = Scene()
        self.devices_page = DevicesPage(name="Devices List", gui_manager=self.gui_manager)
        self.configuration_page = ConfigurationPage(name="Configuration", gui_manager=self.gui_manager)
        self.calibrattion_page = CalibrationPage(name="Calibration", gui_manager=self.gui_manager)

    def show(self):
        dpg.add_button(label="Save Configuration", callback=self.save_config)
        dpg.add_same_line()
        dpg.add_button(label="Refresh", callback=self.refresh)
        dpg.add_same_line()
        dpg.add_button(label="Calibrate", callback=self.calibrate)
        dpg.add_same_line()
        dpg.add_button(label="Test Calibration", callback=self.test_calibration)
        dpg.add_same_line()
        dpg.add_button(label="List Devices", callback=self.list_devices)
        dpg.add_same_line()
        dpg.add_button(label="Show Configuration", callback=self.show_configuration)
        dpg.add_same_line()
        dpg.add_button(label="Logs", callback=self.logs)
        self.scene.add()

    def save_config(self, sender, data):
        self.gui_manager.save_config()

    def refresh(self, sender, data):
        self.gui_manager.refresh_system()

    def calibrate(self, sender, data):
        self.calibrattion_page.show()

    def test_calibration(self, sender, data):
        pass

    def list_devices(self, sender, data):
        self.devices_page.show()

    def show_configuration(self, sender, data):
        self.configuration_page.show()

    def logs(self, sender, data):
        dpg.show_logger()

    def update(self, system_state: dict):
        self.scene.draw(system_state)
        if dpg.does_item_exist("Devices List"):
            self.devices_page.update(system_state)
        if dpg.does_item_exist("Configuration"):
            self.configuration_page.update(system_state)
        if dpg.does_item_exist("Calibration"):
            self.calibrattion_page.update(system_state)

    def clear(self):
        pass


class GuiManager:
    def __init__(self, pipe, logging_queue):
        self._pipe = pipe
        self._logging_queue = logging_queue
        self._server_config: Configuration() = None
        self._page = VisualizationPage(self)

    def on_render(self, sender, data):
        while self._logging_queue.qsize() > 0:
            try:
                record = self._logging_queue.get_nowait()
                message = record.getMessage()
                logging_level = record.levelname
                if logging_level == "DEBUG":
                    dpg.log_debug(message)
                elif logging_level == "INFO":
                    dpg.log_info(message)
                elif logging_level == "WARNING":
                    dpg.log_warning(message)
                else:
                    dpg.log_error(message)
            except queue.Empty:
                pass

        system_state = {}
        while self._pipe.poll():
            data = self._pipe.recv()
            if "state" in data:
                system_state = data["state"]
            if "config" in data:
                self._server_config = data["config"]
        self._page.update(system_state)

    def update_config(self, config):
        self._server_config = config
        self._pipe.send({"config": self._server_config})

    def get_config(self) -> Configuration:
        if self._server_config is not None:
            return self._server_config.copy()

    def save_config(self, path: Path = None):
        self._pipe.send({"save": path})

    def refresh_system(self):
        self._pipe.send({"refresh": None})

    def call_calibration(self, origin, pos_x, pos_y):
        self._pipe.send({"calibrate": (origin, pos_x, pos_y)})

    # Will Run the main gui
    def start(self):
        dpg.create_context()
        
        with dpg.window(label="Vive Server", autosize=True, pos=(20, 20), tag="main_window"):
            self._page.show()

        dpg.set_frame_callback(0, self.on_render)
        
        dpg.create_viewport(title="Vive Server", width=1200, height=800)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()
