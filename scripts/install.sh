#!/bin/bash

KLIPPER_PATH="${HOME}/klipper"
REPO_PATH="${HOME}/nevermore-extended-servo"
EXTENSIONS="nevermore_servo nevermore_servo_profile_manager"

set -eu
export LC_ALL=C


function preflight_checks {
    if [ "$EUID" -eq 0 ]; then
        echo "[PRE-CHECK] This script must not be run as root!"
        exit -1
    fi

    if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F 'klipper.service')" ]; then
        printf "[PRE-CHECK] Klipper service found! Continuing...\n\n"
    else
        echo "[ERROR] Klipper service not found, please install Klipper first!"
        exit -1
    fi
}

function check_download {
    local nevermoreextendedservodirname nevermoreextendedservobasename
    nevermoreextendedservodirname="$(dirname ${REPO_PATH})"
    nevermoreextendedservobasename="$(basename ${REPO_PATH})"

    if [ ! -d "${REPO_PATH}" ]; then
        echo "[DOWNLOAD] Downloading Nevermore-Extended-Servo repository..."
        if git -C $nevermoreextendedservodirname clone https://github.com/LynxCrew/Nevermore-Extended-Servo.git $nevermoreextendedservobasename; then
            chmod +x ${REPO_PATH}/install.sh
            chmod +x ${REPO_PATH}/update.sh
            chmod +x ${REPO_PATH}/uninstall.sh
            printf "[DOWNLOAD] Download complete!\n\n"
        else
            echo "[ERROR] Download of Nevermore-Extended-Servo git repository failed!"
            exit -1
        fi
    else
        printf "[DOWNLOAD] Nevermore-Extended-Servo repository already found locally. Continuing...\n\n"
    fi
}

function link_extension {
    echo "[INSTALL] Linking extension to Klipper..."

    for extension in ${EXTENSIONS}; do
        if [ ! -f "${KLIPPER_PATH}/klippy/extras/${extension}.py" ]; then
            ln -sf "${REPO_PATH}/source/${extension}.py" "${KLIPPER_PATH}/klippy/extras/${extension}.py"
        fi
    done
}

function restart_klipper {
    echo "[POST-INSTALL] Restarting Klipper..."
    sudo systemctl restart klipper
}


printf "\n======================================\n"
echo "- Nevermore-Extended-Servo install script -"
printf "======================================\n\n"


# Run steps
preflight_checks
check_download
link_extension
restart_klipper
