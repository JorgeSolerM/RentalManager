from datetime import date, datetime


def format_date(value):

    if value is None:

        return ""

    if isinstance(value, (date, datetime)):

        return value.strftime("%d-%m-%Y")

    return value
