from datetime import datetime
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