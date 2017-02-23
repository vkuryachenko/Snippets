import httplib
import urllib2


def BindableHTTPConnectionFactory(source_ip):
    def _get(host, port=None, strict=None, timeout=0):
        bhc = httplib.HTTPConnection(
            host, port=port, strict=strict, timeout=timeout,
            source_address=(source_ip, 0))
        return bhc
    return _get


def BindableHTTPHandlerFactory(source_ip):
    class BindableHTTPHandler(urllib2.HTTPHandler):
        def http_open(self, req):
            return self.do_open(
                BindableHTTPConnectionFactory(source_ip), req)
    return BindableHTTPHandler


def BindableHTTPSConnectionFactory(source_ip):
    def _get(host, port=None, strict=None, timeout=0):
        bhc = httplib.HTTPSConnection(
            host, port=port, strict=strict, timeout=timeout,
            source_address=(source_ip, 0))
        return bhc
    return _get


def BindableHTTPSHandlerFactory(source_ip):
    class BindableHTTPSHandler(urllib2.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(BindableHTTPSConnectionFactory(source_ip), req)
    return BindableHTTPSHandler


class BindableOpenerDirector(object):
    def __init__(self, source_ip):
        self.opener = urllib2.build_opener(
            BindableHTTPHandlerFactory(source_ip),
            BindableHTTPSHandlerFactory(source_ip)
        )

    def open(self, url):
        return self.opener.open(url)

    def urlopen(self, request):
        urllib2.install_opener(self.opener)
        return urllib2.urlopen(request)
