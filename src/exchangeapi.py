import requests

from django.utils.translation import ugettext_lazy as _

from models import FBExchange

OPEN_EXCHANGE_URL = 'https://openexchangerates.org/api/'


class ExchangeAPIError(Exception):
    """Raise for Open Exchange Rates API specific kind of exception"""


class ExchangeAPI(object):

    def __init__(self, app_id, required_currencies, day):
        self.app_id = app_id
        self.day = day
        self.required_currencies = set(required_currencies)

    @property
    def required_currencies(self):
        return self._required_currencies

    @required_currencies.setter
    def required_currencies(self, required_currencies):
        self._required_currencies = required_currencies
        self.rates = self.get_rates()

    def get_rates(self):
        """"Get required currency rates from DB or API and store in DB.
        If date is unavailable from 'historical' url, get from 'latest' url
        without storing in DB"""

        rates = dict(
            FBExchange.objects
            .filter(added=self.day)
            .values_list('currency', 'rate')
        )

        undefined_currencies = self.required_currencies - set(rates.keys())
        if undefined_currencies:
            url = '{}historical/{}.json?app_id={}'.format(
                OPEN_EXCHANGE_URL, self.day.strftime('%Y-%m-%d'), self.app_id)
            error, rates = self.get_api_rates(url, undefined_currencies)
            if error == 'not_available':
                url = '{}latest.json?app_id={}'.format(
                    OPEN_EXCHANGE_URL, self.app_id)
                error, rates = self.get_api_rates(url, undefined_currencies)
            elif rates:
                FBExchange.objects.bulk_create(
                    [
                        FBExchange(
                            added=self.day,
                            currency=currency,
                            rate=rates[currency]
                        )
                        for currency in undefined_currencies
                    ]
                )

            if error is not None:
                raise ExchangeAPIError(error)

        return rates

    def get_api_rates(self, url, undefined_currencies):
        response = requests.get(url).json()

        if 'error' in response:
            rates = {}
            error = response.get('message')
        else:
            error = None
            rates = response.get('rates', {})
            if self.required_currencies - set(rates.keys()):
                raise ExchangeAPIError(
                    _('Currency "{}" has no exchange rate'.format(
                        '; '.join(undefined_currencies))))

        return error, rates

    def convert(self, currency, amount):
        if amount > 0 and currency != 'USD':
            amount /= self.rates[currency]
        return amount
