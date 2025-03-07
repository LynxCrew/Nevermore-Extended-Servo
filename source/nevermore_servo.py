import collections
import logging
import threading

from extras.nevermore_servo_profile_manager import ProfileManager

KELVIN_TO_CELSIUS = -273.15
AMBIENT_TEMP = 25.0
PID_PARAM_BASE = 255.0
SERVO_PROFILE_VERSION = 1

WATERMARK_PROFILE_OPTIONS = {
    "control": (str, "%s", "watermark", False),
    "max_delta": (float, "%.4f", 2.0, True),
    "reverse": (bool, "%s", False, True),
}
# (type, placeholder, default, can_be_none)
PID_PROFILE_OPTIONS = {
    "control": (str, "%s", "pid", False),
    "smooth_time": (float, "%.3f", None, True),
    "smoothing_elements": (int, "%d", None, True),
    "pid_kp": (float, "%.3f", None, False),
    "pid_ki": (float, "%.3f", None, False),
    "pid_kd": (float, "%.3f", None, False),
    "reverse": (bool, "%s", False, True),
}
MANUAL_PROFILE_OPTIONS = {
    "control": (str, "%s", "manual", False),
}
TEMPLATE_PROFILE_OPTIONS = {
    "control": (str, "%s", "template", False),
}


class NevermoreServo:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        name_parts = config.get_name().split()
        self.base_name = name_parts[0]
        self.name = name_parts[-1]
        self.gcode = self.printer.lookup_object("gcode")
        self.configfile = self.printer.lookup_object("configfile")
        self.last_temp = 0.0
        self.last_percent = 0.0
        self.measured_min = 99999999.0
        self.measured_max = -99999999.0
        self.reactor = self.printer.get_reactor()
        self.lock = threading.Lock()

        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in WATERMARK_PROFILE_OPTIONS.items():
            config.get(key, None)
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in PID_PROFILE_OPTIONS.items():
            config.get(key, None)
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in MANUAL_PROFILE_OPTIONS.items():
            config.get(key, None)
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in TEMPLATE_PROFILE_OPTIONS.items():
            config.get(key, None)

        self.nevermore = None
        self.nevermore_name = config.get("nevermore", None)
        if self.nevermore_name is None:
            self.nevermore = self.printer.load_object(config, "nevermore")
        else:
            self.nevermore = self.printer.load_object(config, self.nevermore_name)

        self.hold_time = self.config.getfloat("hold_time", 0.5, above=0.0)
        self.update_tolerance = self.config.getfloat("update_tolerance", 0.01, minval=0.0, maxval=1.0)

        self.min_temp = config.getfloat("min_temp", minval=KELVIN_TO_CELSIUS)
        self.max_temp = config.getfloat("max_temp", above=self.min_temp)
        self.config_smooth_time = config.getfloat("smooth_time", 1.0, above=0.0)
        self.smooth_time = self.config_smooth_time
        self.temperature_sensor = None
        self.temp_sample_timer = None
        self.report_time = None
        self.temp_sensor_name = self.config.get("temperature_sensor", None)
        if self.temp_sensor_name is not None:
            self.report_time = self.config.getfloat(
                "sensor_report_time", 0.25, above=0.0
            )
            self.temp_sample_timer = self.reactor.register_timer(
                self._temp_callback_timer
            )
            self.printer.register_event_handler("klippy:connect", self._handle_connect)
            self.printer.register_event_handler("klippy:ready", self._handle_ready)
        else:
            pheaters = self.printer.load_object(config, "heaters")
            self.sensor = pheaters.setup_sensor(config)
            self.sensor.setup_minmax(self.min_temp, self.max_temp)
            self.sensor.setup_callback(self.temperature_callback)
            pheaters.register_sensor(config, self)
        self.target_temp_conf = config.getfloat(
            "target_temp",
            40.0 if self.max_temp > 40.0 else self.max_temp,
            minval=self.min_temp,
            maxval=self.max_temp,
        )
        self.target_temp = self.target_temp_conf

        self.control_types = collections.OrderedDict(
            {
                "watermark": ControlBangBang,
                "pid": ControlPID,
                #                "manual": ControlManual,
                #                "template": ControlTemplate,
            }
        )
        self.pmgr = ProfileManager(self, self.control_types)
        self.control = self.lookup_control(self.pmgr.init_default_profile())
        self.pmgr.cached_control = self.control
        if self.control is None:
            raise self.config.error(
                "Default Nevermore Servo-Profile could not be loaded."
            )

        self.gcode.register_mux_command(
            "NEVERMORE_SERVO_PROFILE",
            "NEVERMORE_SERVO",
            self.name,
            self.pmgr.cmd_NEVERMORE_SERVO_PROFILE,
            desc=self.pmgr.cmd_NEVERMORE_SERVO_PROFILE_help,
        )
        self.gcode.register_mux_command(
            "SET_NEVERMORE_SERVO_TEMPERATURE",
            "NEVERMORE_SERVO",
            self.name,
            self.cmd_SET_NEVERMORE_SERVO_TEMPERATURE,
            desc=self.cmd_SET_NEVERMORE_SERVO_TEMPERATURE_help,
        )

    def _handle_connect(self):
        self.temperature_sensor = self.printer.lookup_object(self.temp_sensor_name)
        # check if sensor has get_status function and
        # get_status has a 'temperature' value
        if hasattr(
            self.temperature_sensor, "get_status"
        ) and "temperature" in self.temperature_sensor.get_status(
            self.reactor.monotonic()
        ):
            return
        raise self.printer.config_error(
            "'%s' does not report a temperature." % (self.temp_sensor_name,)
        )

    def _handle_ready(self):
        # Start temperature update timer
        self.reactor.update_timer(self.temp_sample_timer, self.reactor.NOW)

    cmd_SET_NEVERMORE_SERVO_TEMPERATURE_help = (
        "Sets a nevermore_servo target temperature"
    )

    def cmd_SET_NEVERMORE_SERVO_TEMPERATURE(self, gcmd):
        degrees = gcmd.get_float("TARGET", 0.0)
        if degrees and (degrees < self.min_temp or degrees > self.max_temp):
            raise self.printer.command_error(
                "Requested temperature (%.1f) out of range (%.1f:%.1f)"
                % (degrees, self.min_temp, self.max_temp)
            )
        self.target_temp = degrees

    def _temp_callback_timer(self, eventtime):
        measured_time = self.reactor.monotonic()
        self.temperature_callback(
            measured_time,
            self.temperature_sensor.get_status(eventtime)["temperature"],
        )

        return measured_time + self.report_time

    def temperature_callback(self, read_time, temp):
        self.last_temp = temp
        if temp:
            self.measured_min = min(self.measured_min, temp)
            self.measured_max = max(self.measured_max, temp)
        if self.control is None:
            return
        percent = self.control.angle_update(read_time, temp, self.target_temp)
        if abs(percent - self.last_percent) > self.update_tolerance:
            self.last_percent = percent
            self.nevermore.set_vent_servo(percent, self.hold_time)

    def get_temp(self, eventtime):
        return self.last_temp, self.target_temp

    def get_smooth_time(self):
        return self.smooth_time

    def is_adc_faulty(self):
        if self.last_temp > self.max_temp or self.last_temp < self.min_temp:
            return True
        return False

    def lookup_control(self, profile):
        return self.control_types[profile["control"]](profile, self)

    def set_control(self, control):
        with self.lock:
            old_control = self.control
            self.control = control
        return old_control

    def get_control(self):
        return self.control

    def get_status(self, eventtime):
        return {
            "temperature": round(self.last_temp, 2),
            "measured_min_temp": round(self.measured_min, 2),
            "measured_max_temp": round(self.measured_max, 2),
            "target": self.target_temp,
            "control": self.control.get_type(),
        }


class ControlBangBang:
    @staticmethod
    def init_profile(config_section, name, pmgr=None):
        temp_profile = {}
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in WATERMARK_PROFILE_OPTIONS.items():
            if key == "max_delta":
                above = 0.0
            else:
                above = None
            temp_profile[key] = pmgr._check_value_config(
                key,
                config_section,
                type,
                can_be_none,
                default=default,
                above=above,
            )
        if name != "default":
            profile_version = config_section.getint("profile_version", None)
            if SERVO_PROFILE_VERSION != profile_version:
                logging.info(
                    "nevermore_servo_profile: Profile [%s] not compatible with this version\n"
                    "of nevermore_servo_profile. Profile Version: %d Current Version: %d "
                    % (name, profile_version, SERVO_PROFILE_VERSION)
                )
                return None
        return temp_profile

    @staticmethod
    def set_values(pmgr, gcmd, control, profile_name):
        current_profile = pmgr.servo.get_control().get_profile()
        max_delta = pmgr._check_value_gcmd(
            "MAX_DELTA",
            current_profile["max_delta"],
            gcmd,
            float,
            False,
        )
        reverse = pmgr._check_value_gcmd(
            "REVERSE",
            current_profile["reverse"],
            gcmd,
            bool,
            False,
        )
        temp_profile = {
            "name": profile_name,
            "control": control,
            "max_delta": max_delta,
            "reverse": reverse,
        }
        temp_control = pmgr.servo.lookup_control(temp_profile)
        pmgr.servo.set_control(temp_control)
        msg = (
            "Watermark Parameters:\n"
            "Control: %s\n"
            "Max Delta: %.4f\n"
            "Reverse: %s\n"
            "have been set as current profile." % (control, max_delta, reverse)
        )
        pmgr.servo.gcode.respond_info(msg)

    @staticmethod
    def save_profile(pmgr, temp_profile, profile_name=None, verbose=True):
        if profile_name is None:
            profile_name = temp_profile["name"]
        section_name = pmgr._compute_section_name(profile_name)
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in WATERMARK_PROFILE_OPTIONS.items():
            value = temp_profile[key]
            if value is not None:
                pmgr.servo.configfile.set(section_name, key, placeholder % value)
        temp_profile["name"] = profile_name
        pmgr.profiles[profile_name] = temp_profile
        if verbose:
            pmgr.servo.gcode.respond_info(
                "Current Servo profile for servo [%s] "
                "has been saved to profile [%s] "
                "for the current session. The SAVE_CONFIG command will\n"
                "update the printer config file and restart the printer."
                % (pmgr.servo.name, profile_name)
            )

    @staticmethod
    def load_console_message(profile, servo):
        max_delta = profile["max_delta"]
        reverse = profile["reverse"]
        msg = "Control: %s\n" % (profile["control"],)
        if max_delta is not None:
            msg += "Max Delta: %.3f\n" % max_delta
            msg += "Reverse: %s\n" % reverse
        return msg

    def __init__(self, profile, servo):
        self.profile = profile
        self.servo = servo
        self.max_delta = profile["max_delta"]
        self.reverse = profile["reverse"]
        self.heating = False

    def angle_update(self, read_time, temp, target_temp):
        if self.heating != self.reverse and temp >= target_temp + self.max_delta:
            self.heating = self.reverse
        elif self.heating == self.reverse and temp <= target_temp - self.max_delta:
            self.heating = not self.reverse
        if self.heating:
            logging.info(f"nevermore_servo: {0.0}")
            return 0.0
        else:
            logging.info(f"nevermore_servo: {1.0}")
            return 1.0

    def check_busy(self, eventtime, smoothed_temp, target_temp):
        return smoothed_temp < target_temp - self.max_delta

    def update_smooth_time(self):
        self.smooth_time = self.servo.get_smooth_time()  # smoothing window

    def set_name(self, name):
        self.profile["name"] = name

    def _load_console_message(self):
        return ControlBangBang.load_console_message(self.profile, self.servo)

    def get_profile(self):
        return self.profile

    def get_type(self):
        return "watermark"


PID_SETTLE_DELTA = 1.0
PID_SETTLE_SLOPE = 0.1


class ControlPID:
    @staticmethod
    def init_profile(config_section, name, pmgr):
        temp_profile = {}
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in PID_PROFILE_OPTIONS.items():
            if (
                key == "smooth_time"
                or key == "smoothing_elements"
                or key == "pid_tolerance"
            ):
                above = 0.0
            else:
                above = None
            temp_profile[key] = pmgr._check_value_config(
                key,
                config_section,
                type,
                can_be_none,
                default=default,
                above=above,
            )
        if name == "default":
            temp_profile["smooth_time"] = None
            temp_profile["smoothing_elements"] = None
        else:
            profile_version = config_section.getint("profile_version", 0)
            if SERVO_PROFILE_VERSION != profile_version:
                logging.info(
                    "servo_profile: Profile [%s] not compatible with this version\n"
                    "of servo_profile. Profile Version: %d Current Version: %d "
                    % (name, profile_version, SERVO_PROFILE_VERSION)
                )
                return None
        return temp_profile

    @staticmethod
    def set_values(pmgr, gcmd, control, profile_name):
        current_profile = pmgr.servo.get_control().get_profile()
        target = pmgr._check_value_gcmd("TARGET", None, gcmd, float, True)
        tolerance = pmgr._check_value_gcmd(
            "TOLERANCE",
            None,
            gcmd,
            float,
            True,
        )
        kp = pmgr._check_value_gcmd("KP", None, gcmd, float, False)
        ki = pmgr._check_value_gcmd("KI", None, gcmd, float, False)
        kd = pmgr._check_value_gcmd("KD", None, gcmd, float, False)
        smooth_time = pmgr._check_value_gcmd("SMOOTH_TIME", None, gcmd, float, True)
        smoothing_elements = pmgr._check_value_gcmd(
            "SMOOTHING_ELEMENTS", None, gcmd, int, True
        )
        reverse = pmgr._check_value_gcmd("REVERSE", None, gcmd, bool, True)
        temp_profile = {
            "name": profile_name,
            "control": control,
            "smooth_time": smooth_time,
            "smoothing_elements": smoothing_elements,
            "pid_kp": kp,
            "pid_ki": ki,
            "pid_kd": kd,
            "reverse": reverse,
        }
        temp_control = pmgr.servo.lookup_control(temp_profile)
        pmgr.servo.set_control(temp_control)
        msg = "PID Parameters:\n"
        if target is not None:
            msg += "Target: %.2f,\n" % target
        if tolerance is not None:
            msg += "Tolerance: %.4f\n" % tolerance
        msg += "Control: %s\n" % control
        if smooth_time is not None:
            msg += "Smooth Time: %.3f\n" % smooth_time
        if smoothing_elements is not None:
            msg += "Smoothing Elements: %d\n" % smoothing_elements
        if reverse is not None:
            msg += "Reverse: %d\n" % reverse
        msg += (
            "pid_Kp=%.3f pid_Ki=%.3f pid_Kd=%.3f\n"
            "have been set as current profile." % (kp, ki, kd)
        )
        pmgr.servo.gcode.respond_info(msg)

    @staticmethod
    def save_profile(pmgr, temp_profile, profile_name=None, verbose=True):
        if profile_name is None:
            profile_name = temp_profile["name"]
        section_name = pmgr._compute_section_name(profile_name)
        pmgr.servo.configfile.set(
            section_name, "profile_version", SERVO_PROFILE_VERSION
        )
        for key, (
            type,
            placeholder,
            default,
            can_be_none,
        ) in PID_PROFILE_OPTIONS.items():
            value = temp_profile[key]
            if value is not None:
                pmgr.servo.configfile.set(section_name, key, placeholder % value)
        temp_profile["name"] = profile_name
        pmgr.profiles[profile_name] = temp_profile
        if verbose:
            pmgr.servo.gcode.respond_info(
                "Current Servo profile for servo [%s] "
                "has been saved to profile [%s] "
                "for the current session. The SAVE_CONFIG command will\n"
                "update the printer config file and restart the printer."
                % (pmgr.servo.name, profile_name)
            )

    @staticmethod
    def load_console_message(profile, servo):
        smooth_time = (
            servo.get_smooth_time()
            if profile["smooth_time"] is None
            else profile["smooth_time"]
        )
        smoothing_elements = (
            servo.get_smoothing_elements()
            if profile["smoothing_elements"] is None
            else profile["smoothing_elements"]
        )
        msg = "Control: %s\n" % (profile["control"],)
        if smooth_time is not None:
            msg += "Smooth Time: %.3f\n" % smooth_time
        if smoothing_elements is not None:
            msg += "Smoothing Elements: %d\n" % smoothing_elements
        msg += "PID Parameters: pid_Kp=%.3f pid_Ki=%.3f pid_Kd=%.3f\n" % (
            profile["pid_kp"],
            profile["pid_ki"],
            profile["pid_kd"],
        )
        msg += "Reverse: %s" % profile["reverse"]
        return msg

    def __init__(self, profile, servo):
        self.profile = profile
        self.servo = servo
        self.max_percent = 1
        self.Kp = profile["pid_kp"] / PID_PARAM_BASE
        self.Ki = profile["pid_ki"] / PID_PARAM_BASE
        self.Kd = profile["pid_kd"] / PID_PARAM_BASE
        self.reverse = profile["reverse"]
        self.min_deriv_time = (
            self.servo.get_smooth_time()
            if profile["smooth_time"] is None
            else profile["smooth_time"]
        )
        self.temp_integ_max = 0.0
        if self.Ki:
            self.temp_integ_max = self.max_percent / self.Ki
        self.prev_temp = self.servo.get_temp(self.servo.reactor.monotonic())[0]
        self.prev_temp_time = 0.0
        self.prev_temp_deriv = 0.0
        self.prev_temp_integ = 0.0

    def angle_update(self, read_time, temp, target_temp):
        time_diff = read_time - self.prev_temp_time
        # Calculate change of temperature
        temp_diff = temp - self.prev_temp
        if time_diff >= self.min_deriv_time:
            temp_deriv = temp_diff / time_diff
        else:
            temp_deriv = (
                self.prev_temp_deriv * (self.min_deriv_time - time_diff) + temp_diff
            ) / self.min_deriv_time
        # Calculate accumulated temperature "error"
        temp_err = target_temp - temp
        temp_integ = self.prev_temp_integ + temp_err * time_diff
        temp_integ = max(0.0, min(self.temp_integ_max, temp_integ))
        # Calculate output
        co = self.Kp * temp_err + self.Ki * temp_integ - self.Kd * temp_deriv
        # logging.debug("pid: %f@%.3f -> diff=%f deriv=%f err=%f integ=%f co=%d",
        #    temp, read_time, temp_diff, temp_deriv, temp_err, temp_integ, co)
        bounded_co = max(0.0, min(self.max_percent, co))
        try:
            if not self.reverse:
                logging.info(f"nevermore_servo: {max(0.0, bounded_co)}")
                return max(0.0, bounded_co)
            else:
                logging.info(f"nevermore_servo: {max(0.0, 1.0 - bounded_co)}")
                return max(0.0, 1.0 - bounded_co)
        finally:
            # Store state for next measurement
            self.prev_temp = temp
            self.prev_temp_time = read_time
            self.prev_temp_deriv = temp_deriv
            if co == bounded_co:
                self.prev_temp_integ = temp_integ

    def check_busy(self, eventtime, smoothed_temp, target_temp):
        temp_diff = target_temp - smoothed_temp
        return (
            abs(temp_diff) > PID_SETTLE_DELTA
            or abs(self.prev_temp_deriv) > PID_SETTLE_SLOPE
        )

    def update_smooth_time(self):
        self.min_deriv_time = self.servo.get_smooth_time()  # smoothing window

    def set_pid_kp(self, kp):
        self.Kp = kp / PID_PARAM_BASE

    def set_pid_ki(self, ki):
        self.Ki = ki / PID_PARAM_BASE
        if self.Ki:
            self.temp_integ_max = 1.0 / self.Ki
        else:
            self.temp_integ_max = 0.0

    def set_pid_kd(self, kd):
        self.Kd = kd / PID_PARAM_BASE

    def set_name(self, name):
        self.profile["name"] = name

    def _load_console_message(self):
        return ControlPID.load_console_message(self.profile, self.servo)

    def get_profile(self):
        return self.profile

    def get_type(self):
        return "pid"


def load_config_prefix(config):
    return NevermoreServo(config)
