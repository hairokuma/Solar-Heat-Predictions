import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_LATITUDE, MAX_LATITUDE = -90, 90
MIN_LONGITUDE, MAX_LONGITUDE = -180, 180
MIN_PORT, MAX_PORT = 1, 65535
MIN_REASONABLE_TEMP_C, MAX_REASONABLE_TEMP_C = -50, 60
MIN_DELTA_THRESHOLD_C, MAX_DELTA_THRESHOLD_C = 0.1, 30
MIN_DESIRED_HOME_TEMP_C, MAX_DESIRED_HOME_TEMP_C = 5, 35
MIN_COOLDOWN_MIN, MAX_COOLDOWN_MIN = 1, 1440
MIN_HUMIDITY_PCT, MAX_HUMIDITY_PCT = 0, 100


def is_valid_email(value):
    return bool(value) and bool(EMAIL_RE.match(value))


def is_valid_latitude(value):
    return MIN_LATITUDE <= value <= MAX_LATITUDE


def is_valid_longitude(value):
    return MIN_LONGITUDE <= value <= MAX_LONGITUDE


def is_valid_port(value):
    return MIN_PORT <= value <= MAX_PORT


def is_reasonable_temp(value):
    return MIN_REASONABLE_TEMP_C <= value <= MAX_REASONABLE_TEMP_C


def is_valid_humidity(value):
    return MIN_HUMIDITY_PCT <= value <= MAX_HUMIDITY_PCT
