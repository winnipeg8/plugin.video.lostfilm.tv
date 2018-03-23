# -*- coding: utf-8 -*-

import xbmc
import urlparse
import urllib
import urllib2
import time
from torrent_handling import TorrentOpener
from storage import SeriesDatabase
from html_document import HtmlDocument


class InfoFetcher(TorrentOpener):

    def __init__(self, addon, base_url, addon_handle, user_agent, paths, cj, logger):
        TorrentOpener.__init__(self, addon, base_url, addon_handle, user_agent, paths, logger)
        site_url = 'www.lostfilm.tv'
        self.connection_type = self.addon.getSetting("ConType")
        if self.connection_type == "0":
            self.httpSiteUrl = 'http://' + site_url
        else:
            self.httpSiteUrl = 'https://' + site_url
        self.response = ''
        self.cj = cj
        self.series_db = SeriesDatabase(paths.db_name, self.logger)

    @staticmethod
    def post_query(query):
        return urllib.urlencode(query)

    @staticmethod
    def show_message(heading, message, times=3000):
        xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s")' % (heading, message, times))

    @staticmethod
    def xbmc_path(x):
        return xbmc.translatePath(x)

    @staticmethod
    def parse_onclick(s):
        import re
        res = re.findall("PlayEpisode\('([^']+)','([^']+)','([^']+)'\)", s)
        if res:
            series_id, season, episode = res[0]
            series_id = int(series_id.lstrip("_"))
            season = int(season.split('.')[0])
            episode = int(episode)
            return "('%s','%s','%s')" % (series_id, season, episode)
        else:
            return "('0','0','0')"

    @staticmethod
    def parse_ru_date(ru_date):
        dd, mm, yyyy = ru_date.split()
        if u'январ' in mm:
            mm = '01'
        elif u'феврал' in mm:
            mm = '02'
        elif u'март' in mm:
            mm = '03'
        elif u'апрел' in mm:
            mm = '04'
        elif u'ма' in mm:
            mm = '05'
        elif u'июн' in mm:
            mm = '06'
        elif u'июл' in mm:
            mm = '07'
        elif u'август' in mm:
            mm = '08'
        elif u'сентяб' in mm:
            mm = '09'
        elif u'октяб' in mm:
            mm = '10'
        elif u'нояб' in mm:
            mm = '11'
        elif u'декаб' in mm:
            mm = '12'
        else:
            return None
        return '%02d.%s.%s' % (int(dd), mm, yyyy)

    def lostfilm_login(self):
        try:
            uptime = float(self.addon.getSetting("uptime"))
        except Exception, err:
            self.logger.log.info('Could not get uptime: %s' % err)
            uptime = 0
        if time.time() - uptime < 24 * 3600:
            # self.logger.log.info(time.time() - uptime)
            return True
        else:
            rec = self.send_get_request('http://www.lostfilm.tv/feedback/')
            if '<a href="/reg"' not in rec:
                return True
        login_url = 'http://www.lostfilm.tv/ajaxik.php'
        login = self.addon.getSetting("login")
        passw = self.addon.getSetting("password")
        if login == "" or passw == '':
            self.show_message('lostfilm.tv', "Проверьте логин и пароль", times=50000)
        values = {
            'mail': login,
            'pass': passw,
            'rem': 1,
            'type': 'login',
            'act': 'users'
        }
        post = urllib.urlencode(values)
        html = self.get_html(login_url, post, self.httpSiteUrl + '/login')
        self.cj.cj.save(ignore_discard=True)
        self.addon.setSetting("uptime", str(time.time()))
        return html

    def get_html(self, url_string, post=None, ref=None, get_redirect=False):
        if url_string.find('http') < 0:
            if self.connection_type == "0":
                url_string = 'http:' + url_string
            else:
                url_string = 'https:' + url_string

        request = urllib2.Request(url_string, post)

        host = urlparse.urlsplit(url_string).hostname
        if ref is None:
            try:
                ref = 'http://' + host
            except Exception, err:
                self.logger.log.info('Could not determine hostname: %s' % err)
                ref = 'localhost'

        request.add_header('User-Agent', self.user_agent)
        request.add_header('Host', host)
        request.add_header('Accept', 'text/html, application/xhtml+xml, */*')
        request.add_header('Accept-Language', 'ru-RU')
        request.add_header('Referer', ref)
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')

        try:
            f = urllib2.urlopen(request)
        except IOError, err:
            if hasattr(err, 'reason'):
                self.logger.log.info('We failed to reach a server')
            elif hasattr(err, 'code'):
                self.logger.log.info('The server couldn\'t fulfill the request')
            return 'We failed to reach a server'

        if get_redirect:
            html = f.geturl()
        else:
            html = f.read()

        return html

    def send_get_request(self, target, referer='http://lostfilm.tv/', post=None, for_info=False):
        try:
            req = urllib2.Request(url=target, data=post)
            req.add_header('User-Agent', self.user_agent)
            resp = urllib2.urlopen(req)
            http = resp.read()
            if for_info:
                http = resp
            resp.close()
            return http
        except Exception, err:
            self.logger.log.info("%s, %s" % (target, err))

    def fetch_plot(self, sid, tvshow_link, episode_url, existed=False):
        hp = self.send_get_request(episode_url)
        desc = hp[
               hp.find('style="height:20px;overflow:hidden">') + 36:hp.find(
                   '<div style="margin-top:-10px;">')].replace(
            '</div>', '').replace('\t', '')
        desc = HtmlDocument.from_string(desc).text
        if "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd" in desc:
            desc = self.get_info(tvshow_link)['plot']
            desc = u'<Сюжет эпизода недоступен>\n' + desc
        else:
            if not existed:
                self.series_db.add_to_db(sid, desc)
            else:
                self.series_db.rem_inf_db(sid)
                self.series_db.add_to_db(sid, desc)
        return desc

    def get_plot_episode(self, tvshow_link, season_number, episode_number, update_plot=False):
        sid = tvshow_link + 's' + season_number + 'e' + episode_number
        if season_number == '999':
            episode_url = self.httpSiteUrl + tvshow_link + '/additional/episode_' + episode_number
        else:
            episode_url = self.httpSiteUrl + tvshow_link + '/season_' + season_number + '/episode_' + episode_number
        try:
            desc = self.xbmc_path(self.series_db.get_inf_db(sid))
            if update_plot:
                desc = self.fetch_plot(sid, tvshow_link, episode_url, existed=True)
            return desc
        except Exception, err:
            self.logger.log.info('Episode description is not in the database, downloading from the Internet: %s' % err)
            return self.fetch_plot(sid, tvshow_link, episode_url)

    def get_cast(self, tvshow_link, names_only=True):
        max_actors = 20
        cast_url = self.httpSiteUrl + tvshow_link + '/cast/type_1'
        hp = self.send_get_request(cast_url)
        tmp = HtmlDocument.from_string(hp).find('div', {'class': 'text-block persons'})
        cast_urls = tmp.find('a')
        cast_result = []
        i = 0
        while i < min(max_actors, len(cast_urls)):
            name = cast_urls[i].find('div', {'class': 'name-en'}).text
            role = cast_urls[i].find('div', {'class': 'role-en'}).text
            image = 'http:' + cast_urls[i].find('img').attr('autoload') \
                if cast_urls[i].find('img').attr('autoload') else ''
            if names_only:
                cast_result.append((name, role))
            else:
                cast_result.append({'actor': name, 'role': role,
                                    'cover': image, 'url': self.httpSiteUrl + cast_urls[i].attr('href')})
            i += 1
        return cast_result

    def get_director(self, tvshow_link, names_only=True):
        max_directors = 20
        director_url = self.httpSiteUrl + tvshow_link + '/cast/type_2'
        hp = self.send_get_request(director_url)
        tmp = HtmlDocument.from_string(hp).find('div', {'class': 'text-block persons'})
        directors_urls = tmp.find('a')
        directors_list = []
        i = 0
        while i < min(max_directors, len(directors_urls)):
            name = directors_urls[i].find('div', {'class': 'name-en'}).text
            image = 'http:' + directors_urls[i].find('img').attr('autoload') \
                if directors_urls[i].find('img').attr('autoload') else ''
            if names_only:
                directors_list.append(name)
            else:
                directors_list.append({'director': name, 'cover': image,
                                       'url': self.httpSiteUrl + directors_urls[i].attr('href')})
            i += 1
        return directors_list

    def get_info(self, link):
        if self.addon.getSetting('UpdateFromScratch') == 'true':
            self.series_db.rem_inf_db(link)
            self.addon.setSetting('UpdateFromScratch', 'false')
        try:
            info = eval(self.xbmc_path(self.series_db.get_inf_db(link)))
        except Exception, err:
            self.logger.log.info('Series info is not in the database, downloading from the Internet: %s' % err)

            info_url = self.httpSiteUrl + link
            info_html = self.send_get_request(info_url)
            info_and_plot = HtmlDocument.from_string(info_html)
            info_and_plot = info_and_plot.find('div', {'class': 'text-block description'}).text
            plot = info_and_plot.split(u'Описание')[-1].strip(' \t\n\r')
            if len(plot.split(u'Сюжет')) == 2:
                if len(plot.split(u'Сюжет')[0]) == 0:
                    plot = plot.strip(' \t\n\r')
                else:
                    plot = plot.split(u'Сюжет')[-1].strip(' \t\n\r')

            ru_title = ''
            en_title = ''
            studio = ''
            year = ''
            genre = ''
            premiered = ''
            tvshow_id = '0'

            info_html = info_html.splitlines()
            for search_line in info_html:
                try:
                    if 'title-ru' in search_line:
                        ru_title = HtmlDocument.from_string(search_line).find('div').text
                    if 'title-en' in search_line:
                        en_title = HtmlDocument.from_string(search_line).find('div').text
                    if 'сериалы телеканала' in search_line:
                        studio = search_line[search_line.find('">') + 2:search_line.find('</a>')] + ", "
                    if 'Перейти к первой серии' in search_line:
                        premiered = HtmlDocument.from_string(search_line).find('a').text
                        premiered = self.parse_ru_date(premiered)
                        year = int(premiered[-4:])
                    if 'сериалы жанра' in search_line:
                        genre += search_line[search_line.find('">') + 2:search_line.find('</a>')] + ", "
                    if 'main_poster' in search_line:
                        tvshow_id = search_line[search_line.find('/Images/') + 8:search_line.find('/Posters/')]
                except Exception, err:
                    self.logger.log.info('Error in info parsing: %s' % err)
                    pass

            if genre != '':
                genre = genre[:-2]
            if studio != '':
                studio = studio[:-2]

            try:
                cast_and_role = self.get_cast(link, names_only=True)
            except Exception, err:
                self.logger.log.info('Could not get cast and roles: %s' % err)
                cast_and_role = []

            try:
                director = self.get_director(link, names_only=True)
            except Exception, err:
                self.logger.log.info('Could not get director: %s' % err)
                director = ''

            info = {"title": ru_title,
                    "tvshowtitle": ru_title,
                    "originaltitle": en_title,
                    "year": year,
                    "premiered": premiered,
                    "genre": genre,
                    "studio": studio,
                    "director": director,
                    "castandrole": cast_and_role,
                    "plot": plot,
                    "id": tvshow_id,
                    "link": link,
                    "mediatype": "tvshow"}

            self.series_db.add_to_db(link, repr(info))

        return info

    def new_episodes_page(self, page_number):
        page_url = self.httpSiteUrl + '/new/page_' + str(page_number)
        response = self.send_get_request(page_url)
        new_episodes = HtmlDocument.from_string(response)
        new_episodes = new_episodes.find('div', {'class': 'row'})
        episodes_result = []
        for episode in new_episodes:
            ep_name_ru = episode.find('div', {'class': 'alpha'}).strings[::2][0]
            tmp = episode.find('div', {'class': 'haveseen-btn'}).attrs('data-code')
            if len(tmp) == 0:
                tmp = episode.find('div', {'class': 'haveseen-btn checked'}).attrs('data-code')
            if len(tmp) > 0:
                tvshow_number, season_number, episode_number = tmp[0].split('-')
                detail = episode.find('a').attr('href')
                link = detail[detail.find('/series/'):detail.find('/season')]
                try:
                    info = self.get_info(link)
                except Exception, err:
                    self.logger.log.info('Could not get info: %s' % err)
                    info = {}
                info['title'] = ep_name_ru
                info['episode'] = episode_number.encode('ascii', 'ignore')
                info['season'] = season_number.encode('ascii', 'ignore')
                info['id'] = tvshow_number.encode('ascii', 'ignore')
                info['aired'] = episode.find('div', {'class': 'beta'}).text.split(':')[-1].strip()
                info['mediatype'] = 'episode'
                if self.addon.getSetting("FetchPlot") == 'true':
                    info['plot'] = self.get_plot_episode(link, season_number, episode_number)
                episodes_result.append(info)

        return episodes_result

    def get_tvshows(self):
        total_number_of_tvshow_pages = 30  # 285 tv shows as of March 12th, 2018
        tvshows_per_page = 10
        overlap = False
        try:
            tvshows = eval(self.xbmc_path(self.series_db.get_inf_db('dblist')))
        except Exception, err:
            self.logger.log.info('Error getting series database: %s' % err)
            tvshows = []

        for n in range(0, total_number_of_tvshow_pages):
            url = self.xbmc_path(self.httpSiteUrl + '/ajaxik.php')
            post = self.post_query({'act': 'serial', 'type': 'search', 'o': n * tvshows_per_page, 's': 3, 't': 0})
            ajax = self.get_html(url, post, 'http://www.lostfilm.tv')

            response_with_tvshows = eval(
                ajax.replace('\\/', '/').replace(':"', ':u"').replace("true", '"true"').replace("false", '"false"').
                replace("null", '"0"').replace("title_orig", 'originaltitle'))

            tvshows_data = response_with_tvshows["data"]
            if not tvshows_data:
                self.series_db.rem_inf_db('dblist')
                self.series_db.add_to_db('dblist', repr(tvshows))
                return tvshows

            if n == 0:
                tvshows_data.reverse()

            for i in tvshows_data:
                link = i["link"]
                if link not in tvshows:
                    if n == 0:
                        tvshows.insert(0, link)
                    else:
                        tvshows.append(link)
                else:
                    overlap = True

            if overlap:
                self.series_db.rem_inf_db('dblist')
                self.series_db.add_to_db('dblist', repr(tvshows))
                return tvshows

        self.series_db.rem_inf_db('dblist')
        self.series_db.add_to_db('dblist', repr(tvshows))
        return tvshows

    def get_episodes(self, tvshow_link):
        seasons_url = self.httpSiteUrl + tvshow_link + '/seasons'
        seasons_page = self.send_get_request(seasons_url)
        seasons_page_ = HtmlDocument.from_string(seasons_page)
        seasons_list = seasons_page_.find('div', {'class': 'serie-block'})
        tvshow_info = self.get_info(tvshow_link)
        episodes_list = []
        counter = 0
        for season in seasons_list:
            info_s = eval(repr(tvshow_info))
            season_title = season.find('h2').text
            info_s['title'] = season_title
            cse = season.find('div', {'class': 'movie-details-block'})
            cse = cse.find('div', {'class': 'external-btn'}).attrs('onClick')
            counter += 1
            if len(cse) > 0:
                cse = self.parse_onclick(cse[0])
                tmp, info_s['season'], info_s['episode'] = eval(cse)
                info_s['mediatype'] = 'season'
                episodes_list.append((info_s, cse))

            episodes = season.find('tr')
            for episode in episodes:
                try:
                    info_ep = eval(repr(tvshow_info))
                    episode_cse = episode.find('div', {'class': 'external-btn'}).attrs('onClick')
                    if len(episode_cse) > 0:
                        cse = self.parse_onclick(episode_cse[0])
                        tvshow_id, season_, episode_ = eval(cse)
                        if season_ == '999':
                            gamma_class = 'gamma additional'
                        else:
                            gamma_class = 'gamma'
                        title = episode.find('td', {'class': gamma_class}).strings[0]
                        title = title.split('\n')[0]
                        premiered = episode.find('td', {'class': 'delta'}).text.split(':')[-1].strip()

                        info_ep['title'] = title
                        info_ep['episode'] = episode_
                        info_ep['season'] = season_
                        info_ep['aired'] = premiered
                        info_ep['mediatype'] = 'episode'

                        if episode_ != "999" and self.addon.getSetting("FetchPlot") == 'true':
                            info_ep['plot'] = self.get_plot_episode(tvshow_link, season_, episode_)
                        episodes_list.append((info_ep, cse))
                except Exception, err:
                    self.logger.log.info('Error in episodes processing: %s' % err)
        return episodes_list

    def update_tvshows(self):
        self.lostfilm_login()
        try:
            all_tvshows = eval(self.xbmc_path(self.series_db.get_inf_db('dblist')))
        except Exception, err:
            self.logger.log.info('Could not get tv shows database: %s' % err)
            all_tvshows = []
        tvshows_per_page = 10
        tvshows = []
        fetch_new_page = True
        n = 0
        while fetch_new_page:
            url = self.xbmc_path(self.httpSiteUrl + '/ajaxik.php')
            post = self.post_query({'act': 'serial', 'type': 'search', 'o': n * tvshows_per_page, 's': 3, 't': 1})
            ajax = self.get_html(url, post, 'http://www.lostfilm.tv')
            d = eval(
                ajax.replace('\\/', '/').replace(':"', ':u"').replace("true", '"true"').replace("false", '"false"').
                replace("null", '"0"').replace("title_orig", 'originaltitle'))

            tvshows_data = d["data"]
            if not tvshows_data:
                fetch_new_page = False

            for thshow_data in tvshows_data:
                tvshow_link = thshow_data["link"]
                if tvshow_link not in tvshows:
                    tvshows.append(tvshow_link)
                else:
                    fetch_new_page = False
            n += 1

        for tvshow in tvshows:
            if tvshow not in all_tvshows:
                all_tvshows_ = self.get_tvshows()
                for tvshow_ in all_tvshows_:
                    self.get_info(tvshow_)
                return True

    def get_favorites(self):
        self.lostfilm_login()
        tvshows_per_page = 10
        tvshows = []
        fetch_new_fav_page = True
        n = 0
        while fetch_new_fav_page:
            url = self.xbmc_path(self.httpSiteUrl + '/ajaxik.php')
            post = self.post_query({'act': 'serial', 'type': 'search', 'o': n * tvshows_per_page, 's': 2, 't': 99})
            ajax = self.get_html(url, post, 'http://www.lostfilm.tv')
            d = eval(
                ajax.replace('\\/', '/').replace(':"', ':u"').replace("true", '"true"').replace("false", '"false"').
                replace("null", '"0"').replace("title_orig", 'originaltitle'))

            tvshows_data = d["data"]
            if not tvshows_data:
                fetch_new_fav_page = False

            for thshow_data in tvshows_data:
                tvshow_link = thshow_data["link"]
                if tvshow_link not in tvshows:
                    tvshows.append(tvshow_link)
                else:
                    fetch_new_fav_page = False
            n += 1

        return tvshows
