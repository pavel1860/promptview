from datetime import datetime, timedelta
import pytz


def get_int_timestamp():
    return int(datetime.now().timestamp() * 1000000)



def get_local_datetime(country_code: str):
    timezone_str = pytz.country_timezones[country_code]
    if not timezone_str:
        raise ValueError(f"Country code {country_code} not found")
    country_timezone = pytz.timezone(timezone_str[0])
    country_time = country_timezone.localize(datetime.now())
    return country_time


def to_local_datetime(dt, country_code="US"):
    timezone_str = pytz.country_timezones[country_code]
    tz = pytz.timezone(timezone_str[0])
    return dt.astimezone(tz)


def to_utc_datetime(dt):
    return dt.astimezone(pytz.utc)


def is_in_time_window(time, from_time=None, hours=0, minutes=0, seconds=0):
    if from_time is None:
        from_time = datetime.now()
    start_time = from_time.astimezone(time.tzinfo)
    time_window = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    end_time = start_time - time_window    
    return end_time <= time <= start_time