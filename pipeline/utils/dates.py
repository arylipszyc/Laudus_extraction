from datetime import datetime, date
import calendar
from dateutil.relativedelta import relativedelta

def get_date_range(date_str):
    """
    Calculates the date range from the day after the given date string up to today.
    """
    last_date = datetime.strptime(date_str, "%Y-%m-%d")
    date_from = (last_date + relativedelta(days=1)).date()
    date_to = datetime.now().date()
    
    return date_from, date_to


def get_end_of_month_dates(start_year, start_month, end_year, end_month):
    """
    Returns a list of date objects representing the last day of each month
    in the range [start_year/start_month, end_year/end_month].
    """
    dates = []
    current = date(start_year, start_month, 1)
    end = date(end_year, end_month, 1)
    
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        dates.append(date(current.year, current.month, last_day))
        current += relativedelta(months=1)
    
    return dates


def get_last_day_of_previous_month():
    """
    Returns the last day of the month before today as a date object.
    """
    today = datetime.now().date()
    first_of_this_month = today.replace(day=1)
    return first_of_this_month - relativedelta(days=1)
