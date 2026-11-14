# Source this file (don't execute it):  source env.sh
# Points LeRobot at the calibration files stored in this project folder,
# so the arms work on any computer without recalibrating.
_here="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export HF_LEROBOT_CALIBRATION="$_here/calibration"
unset _here
echo "HF_LEROBOT_CALIBRATION=$HF_LEROBOT_CALIBRATION"
