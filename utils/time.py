from datetime import datetime
import re

def normalize_gtfs_time(s: str) -> str:
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})", s)
    if not m:
        raise ValueError("invalid time format, expected HH:MM:SS")

    hours = int(m.group(1))
    mins  = int(m.group(2))
    secs  = int(m.group(3))

    if secs >= 60:
        mins += secs // 60
        secs %= 60

    if mins >= 60:
        hours += mins // 60
        mins %= 60

    return f"{hours:02d}:{mins:02d}:{secs:02d}"

def get_gtfs_time_from_utc_millis(utc_millis: int) -> str:
    dt = datetime.fromtimestamp(utc_millis / 1000)
    return dt.strftime("%H:%M:%S")