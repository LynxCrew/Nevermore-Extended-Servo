# LynxCrew Nevermore-Extended-Servo Plugin

## What does it do:
This plugin enables extended control for the Stealthmax V2 servo to control the
exhaust flap.

## Install:
SSH into you pi and run:
```
cd ~
wget -O - https://raw.githubusercontent.com/LynxCrew/Nevermore-Extended-Servo/main/scripts/install.sh | bash
```

then add this to your moonraker.conf:
```
[update_manager nevermore-extended-servo]
type: git_repo
channel: dev
path: ~/nevermore-extended-servo
origin: https://github.com/LynxCrew/Nevermore-Extended-Servo.git
managed_services: klipper
primary_branch: main
install_script: scripts/install.sh
```

## Config reference:
```
[nevermore_servo my_nevermore_servo]
nevermore:
#   The nevermore this extended servo control should be tied to
#   Leave your nevermore configuration as is, this is a plugin that hooks into
#   it.
#   If not defined, it will try to grab the default [nevermore] section
min_temp:
max_temp:
#   See the "extruder" section for a description of the above parameters.
#target_temp: 40.0
#   A temperature (in Celsius) that will be the target temperature.
#   The default is 40 degrees.
#
# You can either define a sensor normally like this:
#sensor_type:
#sensor_pin:
#   The thermistor that should be used to temp control the servo, set it up like
#   any normal sensor for example with a temperature_fan
# Or define the name of an existing sensor:
#temperature_sensor:
#   Name of the temperature_sensor to use
#sensor_report_time: 1.0
#   How many seconds to wait between each callback, lower increases sample rate
#   but also load on the host.
#   The default is 1s
#hold_time: 0.5
#   How long the servo should hold its position before being disengaged, the
#   default is 0.5s
#update_tolerance: 
#   How much the flap would need to move in percent to trigger an update that
#   actually changes its position, the default is 1°.
#
control: watermark
#   Can be either pid or watermark
#
#   For control: watermark
#max_delta: 2.0
#   On 'watermark' controlled servos this is the number of degrees in
#   Celsius above the target temperature before closing the exhaust
#   as well as the number of degrees below the target before
#   re-opening the exhaust. The default is 2 degrees Celsius.
#reverse: False
#   Invert the logic
#
#   For control: pid
#pid_Kp:
#pid_Ki:
#pid_Kd:
#   The proportional (pid_Kp), integral (pid_Ki), and derivative
#   (pid_Kd) settings for the PID feedback control system. Kalico
#   evaluates the PID settings with the following general formula:
#     exhaust_percent = 1 - (Kp*e + Ki*integral(e) - Kd*derivative(e)) / 255
#   Where "e" is "target_temperature - measured_temperature" and
#   "exhaust_percent" is the requested percentage with 0.0 being fully closed and
#   1.0 being fully open. The pid_Kp, pid_Ki, and pid_Kd parameters must
#   be provided when the PID control algorithm is enabled.
#smooth_time: 2.0
#   A time value (in seconds) over which temperature measurements will
#   be smoothed when using the PID control algorithm. This may reduce
#   the impact of measurement noise. The default is 2 seconds.
#reverse: False
#   Invert the logic
```

To create additional profiles that can be loaded with the profile manager:
```
[nevermore_servo_profile <nevermore_servo_name> <profile_name>]
control: watermark
#max_delta: 2.0
#reverse: False
#reverse: False
#pid_Kp:
#pid_Ki:
#pid_Kd:
#smooth_time: 2.0
#   See the "nevermore_servo" section for a description of the above parameters.
```

## Gcode Reference:
#### NEVERMORE_SERVO_PROFILE
`NEVERMORE_SERVO_PROFILE LOAD=<profile_name> NEVERMORE_SERVO=<nevermore_servo_name>
[DEFAULT=<profile_name>] [VERBOSE=<verbosity>]`:
Loads the given NEVERMORE_SERVO_PROFILE for the specified nevermore_servo.
If DEFAULT is specified, the Profile specified in DEFAULT will be loaded when
then given Profile for LOAD can't be found (like a getOrDefault method).
If VERBOSE is set to LOW, minimal info will be written in console.
If set to NONE, no console outputs will be given.

`NEVERMORE_SERVO_PROFILE SAVE=<profile_name> NEVERMORE_SERVO=<nevermore_servo_name>`:
Saves the currently loaded profile of the specified nevermore_servo to the config
under the given name.

`NEVERMORE_SERVO_PROFILE REMOVE=<profile_name> NEVERMORE_SERVO=<nevermore_servo_name>`:
Removes the given profile from the profiles List for the current session and config if SAVE_CONFIG is issued afterwards.

`NEVERMORE_SERVO_PROFILE SET_VALUES=<profile_name> NEVERMORE_SERVO=<nevermore_servo_name>
CONTROL=<control_type> KP=<kp> KI=<ki> KD=<kd> SAVE_PROFILE=1`:
Creates a new profile with the given values.
The possible values are dependant on the control type, you can set everything you can set in config.
SAVE_PROFILE specifies whether the profile should be saved afterwards.

`NEVERMORE_SERVO_PROFILE MANUAL=1 NEVERMORE_SERVO=<nevermore_servo_name>`:
With this, you set the servo into manual mode.
If MANUAL=1, the automatic control will be disabled and it can be controlled normally
via commands.
MANUAL=0 will load the last used control again.

#### SET_NEVERMORE_SERVO_TEMPERATURE
`SET_NEVERMORE_SERVO_TEMPERATURE NEVERMORE_SERVO=<nevermore_servo_name> [TARGET=<target_temperature>]`
Set the target Temperature for the nevermore-servo control algorithm.