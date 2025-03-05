import collections


STR_TO_BOOL = ["true", "1"]


class ProfileManager:
    def __init__(self, servo, control_types):
        self.servo = servo
        self.control_types = control_types
        self.profiles = {}
        self.incompatible_profiles = []
        self.cached_control = None
        # Fetch stored profiles from Config
        stored_profs = self.servo.config.get_prefix_sections(
            "nevermore_servo_profile %s" % self.servo.name
        )
        for profile in stored_profs:
            if len(self.servo.name.split(" ")) > 1:
                name = profile.get_name().split(" ", 3)[-1]
            else:
                name = profile.get_name().split(" ", 2)[-1]
            self._init_profile(profile, name)

    def _init_profile(self, config_section, name, force_control=None):
        if force_control is None:
            control = self._check_value_config(
                "control", config_section, str, False, default=None
            )
        else:
            control = force_control
        if control in self.control_types.keys():
            temp_profile = self.control_types[control].init_profile(
                config_section, name, self
            )
            if temp_profile is not None:
                temp_profile["name"] = name
                temp_profile["control"] = control
                self.profiles[name] = temp_profile
            return temp_profile
        else:
            raise self.servo.printer.config_error(
                "Unknown control type '%s' "
                "in [nevermore_servo_profile %s %s]." % (control, self.servo.name, name)
            )

    def _check_value_config(
        self,
        key,
        config_section,
        type,
        can_be_none,
        default=None,
        above=None,
        minval=None,
    ):
        if type is int:
            value = config_section.getint(key, default=default, minval=minval)
        elif type is float:
            value = config_section.getfloat(
                key, default=default, minval=minval, above=above
            )
        elif type == "floatlist":
            value = config_section.getfloatlist(key, default=default)
        elif isinstance(type, tuple) and len(type) == 4 and type[0] == "lists":
            value = config_section.getlists(
                key,
                seps=type[1],
                parser=type[2],
                count=type[3],
                default=default,
            )
        else:
            value = config_section.get(key, default=default)
        if not can_be_none and value is None:
            raise self.servo.gcode.error(
                "nevermore_servo_profile: '%s' has to be "
                "specified in [nevermore_servo_profile %s %s]."
                % (
                    key,
                    self.servo.name,
                    config_section.get_name(),
                )
            )
        return value

    def _check_value_gcmd(
        self,
        name,
        default,
        gcmd,
        type,
        can_be_none,
        minval=None,
        maxval=None,
    ):
        if type is int:
            value = gcmd.get_int(name, default, minval=minval, maxval=maxval)
        elif type is float:
            value = gcmd.get_float(name, default, minval=minval, maxval=maxval)
        elif type is bool:
            value = gcmd.get(name, default)
            if value is not None:
                value = value.lower() in STR_TO_BOOL
            else:
                value = False
        else:
            value = gcmd.get(name, default)
        if not can_be_none and value is None:
            raise gcmd.error(
                "nevermore_servo_profile: '%s' has to be specified." % name
            )
        return value.lower() if type == "lower" else value

    def _compute_section_name(self, profile_name):
        return (
            self.servo.name
            if profile_name == "default"
            else ("nevermore_servo_profile " + self.servo.name + " " + profile_name)
        )

    def init_default_profile(self):
        return self._init_profile(self.servo.config, "default")

    def set_values(self, profile_name, gcmd, verbose=True):
        current_profile = self.servo.get_control().get_profile()
        control = self._check_value_gcmd(
            "CONTROL", current_profile["control"], gcmd, "lower", True
        )
        save_profile = self._check_value_gcmd(
            "SAVE_PROFILE", True, gcmd, int, True, minval=0, maxval=1
        )
        self.control_types[control].set_values(
            pmgr=self, gcmd=gcmd, control=control, profile_name=profile_name
        )
        if save_profile:
            self.save_profile(profile_name=profile_name, verbose=verbose)

    def save_profile(self, profile_name=None, gcmd=None, verbose=True):
        temp_profile = self.servo.get_control().get_profile()
        self.control_types[temp_profile["control"]].save_profile(
            pmgr=self,
            temp_profile=temp_profile,
            profile_name=profile_name,
            verbose=verbose,
        )
        if profile_name is not None:
            self.servo.get_control().set_name(profile_name)

    def load_profile(self, profile_name, gcmd):
        verbose = self._check_value_gcmd("VERBOSE", "low", gcmd, "lower", True)
        if profile_name == self.servo.get_control().get_profile()["name"]:
            if verbose == "high" or verbose == "low":
                self.servo.gcode.respond_info(
                    "Heater Profile [%s] already loaded for heater [%s]."
                    % (profile_name, self.servo.name)
                )
            return
        profile = self.profiles.get(profile_name, None)
        defaulted = False
        default = gcmd.get("DEFAULT", None)
        if profile is None:
            if default is None:
                raise self.servo.gcode.error(
                    "nevermore_servo_profile: Unknown profile [%s] for heater [%s]."
                    % (profile_name, self.servo.name)
                )
            profile = self.profiles.get(default, None)
            defaulted = True
            if profile is None:
                raise self.servo.gcode.error(
                    "nevermore_servo_profile: Unknown default "
                    "profile [%s] for heater [%s]." % (default, self.servo.name)
                )
        control = self.servo.lookup_control(profile)
        self.servo.set_control(control)

        if verbose != "high" and verbose != "low":
            return
        if defaulted:
            self.servo.gcode.respond_info(
                "Couldn't find profile "
                "[%s] for heater [%s]"
                ", defaulted to [%s]." % (profile_name, self.servo.name, default)
            )
        self.servo.gcode.respond_info(
            "Nevermore Servo Profile [%s] loaded for nevermore_servo [%s].\n"
            % (profile["name"], self.servo.name)
        )
        if verbose == "high":
            self.servo.gcode.respond_info(control.load_console_message())

    def remove_profile(self, profile_name, gcmd=None):
        if profile_name in self.profiles:
            section_name = self._compute_section_name(profile_name)
            self.servo.configfile.remove_section(section_name)
            profiles = dict(self.profiles)
            del profiles[profile_name]
            self.profiles = profiles
            self.servo.gcode.respond_info(
                "Profile [%s] for nevermore_servo [%s] "
                "removed from storage for this session.\n"
                "The SAVE_CONFIG command will update the printer\n"
                "configuration and restart the printer"
                % (profile_name, self.servo.name)
            )
        else:
            self.servo.gcode.respond_info(
                "No profile named [%s] to remove" % profile_name
            )

    def use_manual(self, profile_name, gcmd=None):
        if profile_name == 1:
            self.cached_control = self.servo.set_control(None)
        elif profile_name == 0:
            self.servo.set_control(self.cached_control)
        else:
            raise self.servo.gcode.error(
                "nevermore_servo_profile: manual can be either 0 or 1"
            )


    cmd_NEVERMORE_SERVO_PROFILE_help = (
        "Nevermore Servo Profile Persistent Storage management"
    )

    def cmd_NEVERMORE_SERVO_PROFILE(self, gcmd):
        options = collections.OrderedDict(
            {
                "LOAD": self.load_profile,
                "SAVE": self.save_profile,
                "SET_VALUES": self.set_values,
                "REMOVE": self.remove_profile,
                "MANUAL": self.use_manual,
            }
        )
        for key in options:
            profile_name = gcmd.get(key, None)
            if profile_name is not None:
                if not profile_name.strip():
                    raise self.servo.gcode.error(
                        "nevermore_servo_profile: Profile must be specified"
                    )
                options[key](profile_name, gcmd)
                return
        raise self.servo.gcode.error(
            "nevermore_servo_profile: Invalid syntax '%s'" % (gcmd.get_commandline(),)
        )
