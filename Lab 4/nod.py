import pi_servo_hat
import time
import qwiic_proximity

# For most 9g micro servos (like SG90, MS18, SER0048), safe range is 0-120 degrees
SERVO_MIN = 50
SERVO_MAX = 145
SERVO_CH = 0  # Channel 0 by default

servo = pi_servo_hat.PiServoHat()
servo.restart()

print(f"Sweeping servo on channel {SERVO_CH} from {SERVO_MIN} to {SERVO_MAX} degrees...")

sweep_speed = 0.003

prox_sensor = qwiic_proximity.QwiicProximity()
threshold = 9
try:
    while True:
        distance = prox_sensor.get_proximity()
        print(f"Proximity Value: {distance}")

        # if distance < 100: stop sweeping, resume when not
        if distance < threshold:
            print("Proximity detected, stopping sweep.")
            while distance < threshold:
                distance = prox_sensor.get_proximity()
                time.sleep(0.1)
            print("Proximity cleared, resuming sweep.")
        
        # Sweep up
        for angle in range(SERVO_MIN, SERVO_MAX + 1, 1):
            servo.move_servo_position(SERVO_CH, angle)
            # print(f"Angle: {angle}")
            time.sleep(sweep_speed)
        # Sweep down
        for angle in range(SERVO_MAX, SERVO_MIN - 1, -1):
            servo.move_servo_position(SERVO_CH, angle)
            # print(f"Angle: {angle}")
            time.sleep(sweep_speed)
except KeyboardInterrupt:
    print("\nTest stopped.")
    servo.move_servo_position(SERVO_CH, SERVO_MAX)  # Move to center on exit
