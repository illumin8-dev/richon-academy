"""Pure calendar-month parsing and arithmetic shared by enrollment domains."""
from datetime import date
import re


def month_start(value: str) -> date:
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',value):
        raise ValueError('invalid_month')
    return date.fromisoformat(value + '-01')


def add_months(start: date, months: int) -> date:
    if type(months) is not int or start.day!=1:
        raise ValueError('month_only_arithmetic')
    year, month = divmod(start.year*12 + start.month-1 + months,12)
    return date(year,month+1,1)
