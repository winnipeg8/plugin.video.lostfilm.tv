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
    def find_inclusions(html_string, search_start, search_end):
        result = []
        while html_string.find(search_end) > 0:
            s = html_string.find(search_start)
            e = html_string.find(search_end)
            i = html_string[s:e]
            result.append(i)
            html_string = html_string[e + 2:]
        return result

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
        # self.logger.log.info(episode_url)
        try:
            desc = self.xbmc_path(self.series_db.get_inf_db(sid))
            if update_plot:
                desc = self.fetch_plot(sid, tvshow_link, episode_url, existed=True)
            return desc
        except Exception, err:
            self.logger.log.info('Episode description is not in the database, downloading from the Internet: %s' % err)
            return self.fetch_plot(sid, tvshow_link, episode_url)

    def get_cast(self, tvshow_link, roles=False):
        cast_url = self.httpSiteUrl + tvshow_link + '/cast/type_1'
        hp = self.send_get_request(cast_url)
        hp = hp[hp.find('<div class="center-block margin-left">'):]
        ss = '<a href="/persons'
        es = '</a>'
        cast_search = self.find_inclusions(hp, ss, es)
        cast_result = []
        n = 0
        for cast_item in cast_search:
            n += 1
            actor = ''
            role = ''
            img = ''
            cast_url = ''
            cast_details = cast_item.splitlines()
            for cast_detail in cast_details:
                if 'name-ru' in cast_detail:
                    actor = cast_detail[cast_detail.find('">') + 2:cast_detail.find('</div>')]
                if 'role-ru' in cast_detail:
                    role = cast_detail[cast_detail.find('">') + 2:cast_detail.find('</div>')]
                if 'autoload' in cast_detail:
                    img = 'http:' + cast_detail[cast_detail.find('//static.'):cast_detail.find('" />')]
                if '/persons' in cast_detail:
                    cast_url = self.httpSiteUrl + cast_detail[cast_detail.find('/persons'):cast_detail.find('" class=')]
            if roles:
                cast_result.append(actor + ' | ' + role)
            else:
                cast_result.append({'actor': actor, 'role': role, 'cover': img, 'url': cast_url})
            if n > 8:
                return cast_result
        return cast_result

    def get_director(self, link):
        director_url = self.httpSiteUrl + link + '/cast/type_2'
        hp = self.send_get_request(director_url)
        hp = hp[hp.find('<div class="center-block margin-left">'):]
        ss = '<a href="/persons'
        es = '</a>'
        director_search = self.find_inclusions(hp, ss, es)
        director = ''
        for director in director_search:
            img = ''
            director_url = ''
            director_details = director.splitlines()
            for detail in director_details:
                if 'name-ru' in detail:
                    director += detail[detail.find('">') + 2:detail.find('</div>')] + ", "
                if 'autoload' in detail:
                    img = 'http:' + detail[detail.find('//static.'):detail.find('" />')]
                if '/persons' in detail:
                    director_url = self.httpSiteUrl + detail[detail.find('/persons'):detail.find('" class=')]
                if len(director) > 30:
                    return director
        return director

    def get_info(self, link):
        if self.addon.getSetting('UpdateFromScratch') == 'true':
            self.series_db.rem_inf_db(link)
            self.addon.setSetting('UpdateFromScratch', 'false')
        try:
            info = eval(self.xbmc_path(self.series_db.get_inf_db(link)))
        except Exception, err:
            self.logger.log.info('Series info is not in the database, downloading from the Internet: %s' % err)
            # try:
            info_url = self.httpSiteUrl + link
            info_html = self.send_get_request(info_url)
            info_search = info_html.splitlines()

            info_and_plot = HtmlDocument.from_string(self.send_get_request(self.httpSiteUrl + link))
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
            id_ = '0'

            for info_search_ in info_search:
                try:
                    if 'title-ru' in info_search_:
                        ru_title = info_search_[info_search_.find('">') + 2:info_search_.find('</div>')]
                    if 'title-en' in info_search_:
                        en_title = info_search_[info_search_.find('">') + 2:info_search_.find('</div>')]
                    if 'сериалы телеканала' in info_search_:
                        studio = info_search_[info_search_.find('">') + 2:info_search_.find('</a>')]
                    if 'Перейти к первой серии' in info_search_:
                        year = info_search_[info_search_.find('</a>') - 4:info_search_.find('</a>')]
                    if 'Перейти к первой серии' in info_search_:
                        premiered = info_search_[info_search_.find('">') + 2:info_search_.find('</a>')]
                    if 'сериалы жанра' in info_search_:
                        genre += info_search_[info_search_.find('">') + 2:info_search_.find('</a>')] + ", "
                    if 'main_poster' in info_search_:
                        id_ = info_search_[info_search_.find('/Images/') + 8:info_search_.find('/Posters/')]
                except Exception, err:
                    self.logger.log.info('Error in info parsing: %s' % err)
                    pass

            try:
                castandrole = self.get_cast(link, True)
            except Exception, err:
                self.logger.log.info('Could not get cast and roles: %s' % err)
                castandrole = []

            try:
                director = self.get_director(link)
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
                    "castandrole": castandrole,
                    "plot": plot,
                    "id": id_,
                    "link": link
                    }

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
                if self.addon.getSetting("FetchPlot") == 'true':
                    info['plot'] = self.get_plot_episode(link, season_number, episode_number)
                # date, cover, fanart
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
                        info_ep['premiered'] = premiered

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
            # self.logger.log.info(ajax)
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
