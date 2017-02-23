import requests


UPTIMEROBOT_API_URL = 'https://api.uptimerobot.com/getMonitors?' + \
                    'apiKey={}&noJsonCallback=1&format=json'


class UptimeRobotAPIError(Exception):
    """Raise for Uptimerobot API specific kind of exception"""


class UptimeRobotAPI(object):

    STATES = {
        '0': 'PAUSED',
        '1': 'NOT CHECK',
        '2': 'UP',
        '8': 'SEEMS DOWN',
        '9': 'DOWN'
    }

    def __init__(self, api_key):
        self.api_key = api_key

    def get_monitors_states(self):
        url = UPTIMEROBOT_API_URL.format(self.api_key)
        try:
            response = requests.get(url)
        except (
                    requests.exceptions.RequestException,
                    requests.exceptions.BaseHTTPError
                ) as err:
            raise UptimeRobotAPIError(err.message)

        if response.status_code != 200:
            raise UptimeRobotAPIError(
                'Http Error {}. {}'.format(
                    response.status_code, response.text))

        response = response.json()
        stat = response.get('stat')
        if stat != 'ok':
            error = response.get('message', 'UptimerobotAPI unknown error')
            raise UptimeRobotAPIError(error)
        result = [
            (mon['friendlyname'], self.STATES.get(mon['status'], 'UNKNOWN'))
            for mon in response['monitors']['monitor']
        ]
        return result
