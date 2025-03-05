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
min_temp:
max_temp:
#   See the "extruder" section for a description of the above parameters.
sensor_type:
#sensor_pin:
#   The thermistor that should be used to temp control the servo, set it up like
#   and normal sensor for example with a temperature_fan
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
#reverse: False
#   Invert the logic
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

