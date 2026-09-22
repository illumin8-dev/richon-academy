"""Owner-approved Richon tariff. Quotes are not proof of payment."""
from decimal import Decimal, ROUND_HALF_UP

VERSION = 'richon-20260922'
MONTHLY_PLANS = {1: 99000, 2: 176000, 6: 495000}


def quote(months: int) -> dict:
    if type(months) is not int or months not in MONTHLY_PLANS:
        raise ValueError('unsupported_price_plan')
    regular = 99000 * months
    price = MONTHLY_PLANS[months]
    discount = regular - price
    percent = (Decimal(discount) * 100 / Decimal(regular)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return dict(version=VERSION, months=months, regular_krw=regular, discount_krw=discount,
                discount_percent=str(percent), price_krw=price, monthly_average_krw=price // months)


def course_options():
    # duration_kind=monthly is the existing Richon duration selector; fixed is
    # Pre-Richon's two-month cohort. Never select tariffs by a title substring.
    import monthly_store
    data = monthly_store.options()
    for item in data['items']:
        item['price_plans'] = [quote(m) for m in MONTHLY_PLANS] if item['duration_kind']=='monthly' else []
    return data


def apply_to_term(term, kind):
    """The admin may explicitly enter a historical amount. A selected current
    tariff is instead recalculated by the server; recorded paid amounts stay untouched.
    """
    version = term.price_version
    if version is None:
        return term
    if kind != 'monthly' or version != VERSION:
        raise ValueError('price_plan_unavailable')
    price = quote(term.months)['price_krw']
    if term.quoted_amount_krw != price:
        raise ValueError('price_mismatch')
    return term.model_copy(update={'quoted_amount_krw':price})
