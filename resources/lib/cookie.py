# -*- coding: utf-8 -*-


import cookielib
import urllib2


class MyCookieJar:

    def __init__(self, addon, cookie_filename, user_agent, logger):
        self.logger = logger
        self.cj = cookielib.LWPCookieJar(cookie_filename)
        try:
            self.cj.load()
        except Exception, error:
            self.logger.log.info('Could not load cookies: %s' % error)

        cookie_processor = urllib2.HTTPCookieProcessor(self.cj)

        if addon.getSetting("immunicity") == "1":
            url = 'https://antizapret.prostovpn.org/proxy.pac'
            try:
                pac = self.get_pac(url, user_agent)
                prx = pac[pac.find('PROXY ') + 6:pac.find('; DIRECT')]
                if prx.find('http') < 0:
                    prx = "http://" + prx
                proxy_support = urllib2.ProxyHandler({"http": prx})
                self.opener = urllib2.build_opener(proxy_support, cookie_processor)
            except Exception, err:
                self.opener = urllib2.build_opener(cookie_processor)
                self.logger.log.info("failed to use proxy: %s" % err)
        elif addon.getSetting("immunicity") == "2":
            prx = addon.getSetting("Proxy")
            if prx.find('http') < 0:
                prx = "http://" + prx
            proxy_support = urllib2.ProxyHandler({"http": prx})
            self.opener = urllib2.build_opener(proxy_support, cookie_processor)
        else:
            self.opener = urllib2.build_opener(cookie_processor)

    def get_pac(self, target, user_agent, referer='http://lostfilm.tv/', post=None):
        try:
            request = urllib2.Request(url=target, data=post)
            request.add_header('User-Agent', user_agent)
            response = urllib2.urlopen(request)
            response_string = response.read()
            response.close()
            return response_string
        except Exception, e:
            self.logger.log.info('HTTP ERROR %s' % e)
