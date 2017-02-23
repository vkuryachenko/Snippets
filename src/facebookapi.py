import datetime
import json
import random
import urllib
import urllib2

from urllib2 import URLError
from httplib import HTTPException

from urlparse import parse_qs

from django.utils import timezone

from facebook import (
    auth_url, GraphAPI, GraphAPIError, FACEBOOK_GRAPH_URL, VALID_API_VERSIONS
)

from fburllib import BindableOpenerDirector


class FacebookAPI(GraphAPI):

    # https://developers.facebook.com/docs/marketing-api/currencies
    CURRENCIES_OFFSET = {
        'CLP': 1, 'COP': 1, 'CRC': 1, 'HUF': 1, 'ISK': 1, 'IDR': 1, 'JPY': 1,
        'KRW': 1, 'PYG': 1, 'TWD': 1, 'VND': 1}

    def __init__(
            self,
            fbaccount, proxy_user=None, proxy_password=None, proxy_url=None,
            api_latest_version=None):
        self.account = fbaccount
        super(FacebookAPI, self).__init__(
            access_token=self.account.access_token,
            version=api_latest_version or self.account.version_api)

        if self.account.use_luminati:
            url = ('http://{}-session-{}:{}@{}:22225'.format(
                proxy_user, random.random(), proxy_password, proxy_url))
            self.proxy_handler = urllib2.ProxyHandler(
                {'http': url, 'https': url}
            )

    def auth_url(self, canvas_url, perms=('ads_management', 'ads_read'),
                 **kwargs):
        return auth_url(self.account.app_id, canvas_url, perms, **kwargs)

    def get_spends_and_properties(self):
        """Fetch spend metrics for the last 3 days and
        the requested properties of the working ad account"""

        fields = 'adaccounts{currency,account_status,disable_reason,age,' + \
            'amount_spent,insights.date_preset(last_3_days).' + \
            'level(account).time_increment(1)}'
        path = '{}/me'.format(self.version)
        response = self.request(path, {'fields': fields})
        results = response.get('adaccounts', {}).get('data')
        if not isinstance(results, list) or len(results) == 0:
            raise GraphAPIError(
                'Wrong properties for fbaccount: {}'.format(self.account.name))
        ad_accounts = [acc for acc in results if acc.get('age', 0) > 0]
        if len(ad_accounts) == 0:
            raise GraphAPIError(
                'Wrong properties for fbaccount: {}'.format(self.account.name))
        ad_account = ad_accounts[0]

        currency = ad_account.get('currency')
        if currency is None:
            raise GraphAPIError(
                'Wrong currency for fbaccount: {}'.format(self.account.name))

        amount = ad_account.get('amount_spent')
        if amount is not None:
            offset = self.CURRENCIES_OFFSET.get(currency, 100)
            ad_account['amount_spent'] = float(amount)/offset

        ad_account['insights'] = ad_account.get('insights', {}).get('data', [])
        return ad_account

    def get_account_properties(self, fields):
        try:
            return [
                acc for acc in self.get_ad_accounts_properties(fields)
                if acc.get('account_id') == self.account.ad_fbaccount_id][0]
        except IndexError:
            raise GraphAPIError(
                'Wrong properties for fbaccount: {}'.format(self.account.name))

    def get_ad_accounts_properties(self, fields):
        path = '{}/me'.format(self.version)
        params = {'fields': 'adaccounts{{account_id,{}}}'.format(fields)}
        response = self.request(path, params)
        try:
            result = response['adaccounts']['data']
        except (KeyError, TypeError):
            raise GraphAPIError(
                'Wrong properties for fbaccount: {}'.format(self.account.name))
        if not isinstance(result, list):
            raise GraphAPIError(
                'Wrong properties for fbaccount: {}'.format(self.account.name))
        return result

    def save_account_token(self, response, version):
        token = response['access_token']
        expires = timezone.now() + \
            datetime.timedelta(seconds=float(response['expires']))
        self.account.access_token = token
        self.access_token = token
        self.account.token_expire = expires
        if version:
            self.version = 'v{}'.format(version)
            self.account.version_api = version
        self.account.save(update_fields=('access_token',
                                         'token_expire',
                                         'version_api'))
        return (token, expires)

    def get_short_lived_token(self, code, canvas_url):
        response = self.get_access_token_from_code(code, canvas_url,
                                                   self.account.app_id,
                                                   self.account.app_secret)
        return self.save_account_token(response, None)

    def get_long_lived_token(self):
        response = self.extend_access_token(self.account.app_id,
                                            self.account.app_secret)
        version = self.get_version()
        return self.save_account_token(response, version)

    def get_version(self):
        path = '{}{}/me'.format(FACEBOOK_GRAPH_URL, self.version)
        response = self.open_url(path)
        info = response.info()
        version = info.getheader('facebook-api-version').replace('v', '')
        if version not in VALID_API_VERSIONS:
            raise GraphAPIError('API version "{}" no valid.'.format(version))
        return version

    def open_url(self, path, args=None):
        args = args or {}
        args['access_token'] = self.access_token
        params = urllib.urlencode(args)
        url = '{}{}?{}'.format(FACEBOOK_GRAPH_URL, path, params)
        if self.account.use_luminati:
            opener = urllib2.build_opener(self.proxy_handler)
        else:
            opener = BindableOpenerDirector(self.account.ip_address)
        try:
            return opener.open(url)
        except (URLError, HTTPException) as err:
            raise GraphAPIError(err)

    def request(self, path, args=None):
        """Fetches the given path in the Graph API."""
        response = self.open_url(path, args)
        result_text = response.read()
        if result_text:
            result_parse = parse_qs(result_text)
            if 'error' in result_parse:
                raise GraphAPIError(result_parse['error'])
            elif 'access_token' in result_parse:
                result = {'access_token': result_parse['access_token'][0]}
                if 'expires' in result_parse:
                    result['expires'] = result_parse['expires'][0]
            else:
                try:
                    result = json.loads(result_text)
                except ValueError:
                    result = result_text
        else:
            raise GraphAPIError('Query result has no data')

        return result

    def get_spend_period(self, start, end=None):
        end = end or start
        params = {
            'time_range[since]': start,
            'time_range[until]': end,
        }
        return self.get_spend(params)

    def get_spend_preset(self, date_preset):
        params = {
            'date_preset': date_preset,
        }
        return self.get_spend(params)

    def get_spend(self, params):
        path = '{}/act_{}/insights'.format(
            self.version, self.account.ad_fbaccount_id
        )
        params['fields'] = 'spend'
        params['level'] = 'account'
        insights = self.request(path, params).get('data', None)
        spend = sum([float(ins['spend']) for ins in insights])
        return spend
