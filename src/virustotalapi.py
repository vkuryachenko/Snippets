import requests


VIRUSTOTAL_API_URL = 'https://www.virustotal.com/vtapi/v2/url/'


class VirusTotalAPIError(Exception):
    """Raise for VirusTotal API specific kind of exception"""


class VirusTotalAPI(object):
    def __init__(self, api_key):
        self.api_key = api_key

    def request(self, method, domain):
        resource = 'http://{}/'.format(domain)
        data = {'apikey': self.api_key, 'resource': resource, 'url': resource}
        url = '{}{}'.format(VIRUSTOTAL_API_URL, method)
        try:
            response = requests.post(url, data)
        except (
            requests.exceptions.RequestException,
            requests.exceptions.BaseHTTPError
        ) as err:
            raise VirusTotalAPIError(err.message)
        if response.status_code != 200:
            raise VirusTotalAPIError(
                '{} Http Error {}. {}'.format(
                    domain, response.status_code, response.text))

        response = response.json()
        response_code = response.get('response_code', 0)
        if response_code < 1:
            error = response.get('verbose_msg', 'Unknown error')
            raise VirusTotalAPIError('{} {}'.format(domain, error))
        return response
