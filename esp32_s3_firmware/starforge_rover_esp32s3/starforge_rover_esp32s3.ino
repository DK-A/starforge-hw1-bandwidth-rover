/*
 * STARFORGE HW-1 | ESP32-S3 Motor Controller & Hardware Failsafe Watchdog
 * ----------------------------------------------------------------------
 * Receives compact differential-drive commands from Raspberry Pi over USB-Serial:
 *   Format: "M,<left_pwm>,<right_pwm>\n"  where pwm is in [-255, 255]
 *   E-Stop: "S\n"
 *
 * Safety Feature (HW-1 Requirement):
 *   If no valid command/heartbeat is received within WATCHDOG_TIMEOUT_MS (400 ms),
 *   all 4 motors are immediately stopped (PWM = 0).
 */

#include <Arduino.h>

// --- Pin Definitions (Adjust to match your H-Bridge wiring, e.g., L298N / TB6612 / BTS7960) ---
// Left Side Motors (Front-Left + Rear-Left wired in parallel to Left H-Bridge channel)
constexpr int PIN_LEFT_PWM  = 4;
constexpr int PIN_LEFT_IN1  = 5;
constexpr int PIN_LEFT_IN2  = 6;

// Right Side Motors (Front-Right + Rear-Right wired in parallel to Right H-Bridge channel)
constexpr int PIN_RIGHT_PWM = 7;
constexpr int PIN_RIGHT_IN1 = 15;
constexpr int PIN_RIGHT_IN2 = 16;

// Optional Status LED (built-in RGB/LED on many ESP32-S3 boards)
constexpr int PIN_STATUS_LED = 2;

// --- PWM & Watchdog Configuration ---
constexpr int PWM_FREQ = 20000;       // 20 kHz (quiet, no motor whine)
constexpr int PWM_RES  = 8;           // 8-bit: 0 - 255
constexpr unsigned long WATCHDOG_TIMEOUT_MS = 450;

unsigned long lastCommandMs = 0;
bool failsafeActive = true;
String inputBuffer = "";

void setMotorSide(int pwmPin, int in1Pin, int in2Pin, int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0) {
    digitalWrite(in1Pin, HIGH);
    digitalWrite(in2Pin, LOW);
    ledcWrite(pwmPin, speed);
  } else if (speed < 0) {
    digitalWrite(in1Pin, LOW);
    digitalWrite(in2Pin, HIGH);
    ledcWrite(pwmPin, -speed);
  } else {
    digitalWrite(in1Pin, LOW);
    digitalWrite(in2Pin, LOW);
    ledcWrite(pwmPin, 0);
  }
}

void stopAllMotors() {
  setMotorSide(PIN_LEFT_PWM, PIN_LEFT_IN1, PIN_LEFT_IN2, 0);
  setMotorSide(PIN_RIGHT_PWM, PIN_RIGHT_IN1, PIN_RIGHT_IN2, 0);
}

void processCommand(const String& cmd) {
  if (cmd.startsWith("S")) {
    stopAllMotors();
    failsafeActive = true;
    Serial.println("ACK,STOP");
    return;
  }

  if (cmd.startsWith("M,")) {
    int firstComma = cmd.indexOf(',');
    int secondComma = cmd.indexOf(',', firstComma + 1);
    if (secondComma > firstComma) {
      int leftPwm = cmd.substring(firstComma + 1, secondComma).toInt();
      int rightPwm = cmd.substring(secondComma + 1).toInt();
      setMotorSide(PIN_LEFT_PWM, PIN_LEFT_IN1, PIN_LEFT_IN2, leftPwm);
      setMotorSide(PIN_RIGHT_PWM, PIN_RIGHT_IN1, PIN_RIGHT_IN2, rightPwm);
      lastCommandMs = millis();
      failsafeActive = false;
      digitalWrite(PIN_STATUS_LED, HIGH);
      return;
    }
  }

  if (cmd.startsWith("PING")) {
    lastCommandMs = millis();
    Serial.println("PONG");
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_LEFT_IN1, OUTPUT);
  pinMode(PIN_LEFT_IN2, OUTPUT);
  pinMode(PIN_RIGHT_IN1, OUTPUT);
  pinMode(PIN_RIGHT_IN2, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);

  // ESP32 Arduino Core v3.x LEDC API
  ledcAttach(PIN_LEFT_PWM, PWM_FREQ, PWM_RES);
  ledcAttach(PIN_RIGHT_PWM, PWM_FREQ, PWM_RES);

  stopAllMotors();
  lastCommandMs = millis();
  Serial.println("STARFORGE_ESP32S3_READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      inputBuffer.trim();
      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = "";
      }
    } else if (inputBuffer.length() < 64) {
      inputBuffer += c;
    }
  }

  // Hardware Watchdog: Safe-stop if link/Pi heartbeat drops
  if (!failsafeActive && (millis() - lastCommandMs > WATCHDOG_TIMEOUT_MS)) {
    stopAllMotors();
    failsafeActive = true;
    digitalWrite(PIN_STATUS_LED, LOW);
    Serial.println("WARN,FAILSAFE_STOP");
  }
}
