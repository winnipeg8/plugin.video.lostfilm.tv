# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from collections import namedtuple
import re
import requests
import os
import json

from concurrent.futures import ThreadPoolExecutor, as_completed
from support.common import str_to_date, Attribute
from support.abstract.scraper import AbstractScraper, ScraperError, parse_size
from support.plugin import plugin
from util.htmldocument import HtmlDocument
from util.timer import Timer

FULL_SEASON_TORRENT_NUMBER = 999


class Series(namedtuple('Series', ['id', 'title', 'original_title', 'country', 'year', 'genres',
                                   'image', 'icon', 'poster', 'plot', 'actors', 'directors', 'writers',
                                   'seasons_count', 'episodes_count'])):
    pass


class Episode(namedtuple('Episode', ['series_id', 'series_title', 'season_number', 'episode_number',
                                     'episode_title', 'original_title', 'release_date', 'icon', 'poster', 'image',
                                     'plot', 'watched'])):
    def __eq__(self, other):
        return self.series_id == other.series_id and \
               self.season_number == other.season_number and \
               self.episode_number == other.episode_number

    def __ne__(self, other):
        return not self == other

    def matches(self, series_id=None, season_number=None, episode_number=None):
        def eq(a, b):
            return str(a).lstrip('0') == str(b).lstrip('0')

        return (series_id is None or eq(self.series_id, series_id)) and \
               (season_number is None or eq(self.season_number, season_number)) and \
               (episode_number is None or eq(self.episode_number, episode_number))

    @property
    def is_complete_season(self):
        return (self.episode_number == FULL_SEASON_TORRENT_NUMBER) or (self.season_number == FULL_SEASON_TORRENT_NUMBER)


class Quality(Attribute):
    def get_lang_base(self):
        return 40208

    SD = (0, 'sd')
    HD_720 = (1, '720', '720p', 'mp4')
    HD_1080 = (2, '1080p', '1080', 'hd')

    def __lt__(self, other):
        return self.id < other.id


TorrentLink = namedtuple('TorrentLink', ['quality', 'url', 'size'])


class LostFilmScraper(AbstractScraper):
    BASE_URL = "http://www.lostfilm.tv"
    LOGIN_URL = "http://www.lostfilm.tv/ajaxik.php"
    BLOCKED_MESSAGE = "Контент недоступен на территории Российской Федерации"

    def __init__(self, login, password, cookie_jar=None, series_ids_cache=None,
                 xrequests_session=None, series_cache=None, max_workers=10, anonymized_urls=None):
        super(LostFilmScraper, self).__init__(xrequests_session, cookie_jar)
        self.series_cache = series_cache if series_cache is not None else {}
        self.series_web_ids_dict = series_ids_cache if series_ids_cache is not None else {}
        self.max_workers = max_workers
        self.response = None
        self.login = login
        self.password = password
        self.has_more = None
        self.watched_episodes = self.get_watched_episodes()
        self.anonymized_urls = anonymized_urls if anonymized_urls is not None else []
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; WOW64) ' \
                                             'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                                             'Chrome/58.0.3004.3 ' \
                                             'Safari/537.36'
        self.session.add_proxy_need_check(self._check_content_is_blocked)
        self.session.add_proxy_validator(self._validate_proxy)

    def check_for_new_series(self):

        r = requests.post(self.LOGIN_URL, params={'type': 'search', 's': '3', 't': '0', 'act': 'serial', 'o': 0})
        ids_incr = [str(int(r1['img'].split("/")[4])) for r1 in r.json()['data']]
        if not (set(ids_incr).intersection(self.get_all_series_ids()) == set(ids_incr)):
            skip = 0
            ids = []
            web_ids = []
            prev_ids = []
            condition = True
            while condition:
                r = requests.post(self.LOGIN_URL,
                                  params={'type': 'search', 's': '2', 't': '0', 'act': 'serial', 'o': '%s' % skip})
                ids_incr = [int(r1['img'].split("/")[4]) for r1 in r.json()['data']]
                web_ids_incr = [r1['title_orig'] for r1 in r.json()['data']]
                if prev_ids == ids_incr:
                    condition = False
                else:
                    skip += 10
                prev_ids = ids_incr
                ids += ids_incr
                web_ids += web_ids_incr
            web_ids = [re.sub('&', 'and', (re.sub(' ', '_', re.sub('[^a-zA-Z0-9-& \n\.]', '', wid)))) for wid in
                       web_ids]
            for i in range(len(web_ids)):
                if web_ids[i] == '11.22.63':
                    web_ids[i] = '11-22-63'
                self.series_web_ids_dict[str(ids[i])] = web_ids[i]

    def get_all_series_ids(self):
        return self.series_web_ids_dict.keys()

    def get_favorite_series(self):
        self.ensure_authorized()
        skip = 0
        ids = []
        prev_ids = []
        condition = True
        while condition:
            r = self.fetch(self.LOGIN_URL,
                           params={'type': 'search', 's': '2', 't': '99', 'act': 'serial', 'o': '%s' % skip},
                           json_req=True)
            ids_incr = [int(r1['img'].split("/")[4]) for r1 in r]
            if prev_ids == ids_incr:
                condition = False
            else:
                skip += 10
            prev_ids = ids_incr
            ids += ids_incr

        return ids

    def get_watched_episodes(self):
        self.ensure_authorized()
        doc = self.fetch(self.BASE_URL + '/my/type_0')
        series_list = doc.find('div', {'class': 'serials-list-box'})
        series = series_list.find('div', {'class': 'serial-box'})
        _ids = []
        for s in series:
            _id = int(s.find('img', {'class': 'avatar'}).attrs('src')[0].split('/')[-3])
            _ids.append(_id)
        watched_episodes = {}
        for _id in _ids:
            watched_episodes[_id] = self.parse_watched_response(_id)
        return watched_episodes

    def parse_watched_response(self, series_id):
        self.ensure_authorized()
        data = {'act': 'serial', 'type': 'getmarks', 'id': series_id}
        response = self.fetch(self.LOGIN_URL, data=data)
        parsed_response = json.loads(response.text)
        if 'error' in parsed_response and parsed_response['error'] == 2:
            answer = []
        else:
            if len(parsed_response) != 0:
                parsed_response = parsed_response['data']
            answer = [(int(r[3:6]), int(r[6:9])) for r in parsed_response]
            self.log.info(series_id)

        return answer

    def is_watched(self, series_id, episode_number, season_number):
        answer = False
        if series_id in self.watched_episodes.keys():
            if (episode_number, season_number) in self.watched_episodes[series_id]:
                answer = True
        return answer

    def toggle_watched(self, series_id, season=None, episode=None):
        self.ensure_authorized()
        if season is None:
            episodes = self.get_series_episodes(series_id)
            for e in episodes:
                if not e.is_complete_season and not e.watched:
                    params = {'act': 'serial', 'type': 'markepisode',
                              'val': '%d-%d-%d' % (series_id, e.season_number, e.episode_number)}
                    self.fetch(self.LOGIN_URL, data=params)
        elif season != FULL_SEASON_TORRENT_NUMBER:
            params = {'act': 'serial', 'type': 'markepisode', 'val': '%d-%d-%d' % (series_id, season, episode)}
            self.fetch(self.LOGIN_URL, data=params)
            # else:
            #      params = {'act': 'serial', 'type': 'markseason', 'val': '%d-%d' % (series_id, season)}
            #     r = self.fetch(self.LOGIN_URL, data=params)

    def add_series(self, series_id):
        params = {'act': 'serial', 'type': 'follow', 'id': series_id}
        self.fetch(self.LOGIN_URL, data=params)

    def authorize(self):
        with Timer(logger=self.log, name='Authorization'):
            try:
                self.session.cookies.clear('.lostfilm.tv')
            except KeyError:
                pass
        response = self.fetch(url=self.LOGIN_URL,
                              data={'act': 'users', 'type': 'login', 'mail': self.login, 'pass': self.password,
                                    'rem': 1})
        parsed_response = json.loads(response.text)
        if 'error' in parsed_response and parsed_response['error'] == 2:
            raise ScraperError(32003, "Authorization failed", check_settings=True)

    def ensure_authorized(self):
        if not self.session.cookies.get('lf_session'):
            self.authorize()

    def get_torrent_links(self, series_id, season_number, episode_number):
        doc = self.fetch(self.BASE_URL + '/v_search.php',
                         {'c': series_id, 's': season_number, 'e': episode_number},
                         forced_encoding='utf-8')
        doc = self.fetch(doc.find('a').attr('href'), forced_encoding='utf-8')
        links_list = doc.find('div', {'class': 'inner-box--list'})
        link_blocks = links_list.find('div', {'class': 'inner-box--item'})

        links = []
        for link_block in link_blocks:
            link_quality = link_block.find('div', {'class': 'inner-box--label'}).text.lower()
            links_list_row = link_block.find('div', {'class': 'inner-box--link sub'})
            links_href = links_list_row.find('a').attr('href')
            link_desc = link_block.find('div', {'class': 'inner-box--desc'}).text
            size = re.search('(\d+\.\d+ ..\.)', link_desc).group(1)[:-1]

            links.append(TorrentLink(Quality.find(link_quality), links_href, parse_size(size)))

        return links

    def _validate_proxy(self, proxy, request, response):
        if response.status_code != 200 and response.status_code != 302:
            return "Returned status %d" % response.status_code
        if 'browse.php' in request.url or 'serials.php' in request.url:
            if 'id="MainDiv"' not in response.text:
                return "Response doesn't match original"
            elif self.BLOCKED_MESSAGE in response.text:
                return "Returned blocked content"

    def _check_content_is_blocked(self, request, response):
        if request.url in self.anonymized_urls:
            return True
        elif response and self.BLOCKED_MESSAGE in response.text:
            self.log.info("Content of %s blocked, trying to use anonymous proxy..." % request.url)
            self.anonymized_urls.append(request.url)
            return True
        else:
            return False

    def fetch(self, url, params=None, data=None, json_req=False, forced_encoding=None, **request_params):
        self.response = super(LostFilmScraper, self).fetch(url, params, data, **request_params)
        encoding = self.response.encoding
        if forced_encoding:
            encoding = forced_encoding
        elif encoding == 'ISO-8859-1':
            encoding = 'windows-1251'
        if json_req:
            return self.response.json()['data']
        else:
            return HtmlDocument.from_string(self.response.content, encoding)

    def fetch_crew(self, series_id, crew_type):
        doc = self.fetch(self.BASE_URL + "/series/%s/cast/type_%s" %
                         (self.series_web_ids_dict[str(series_id)], crew_type))
        info = doc.find('div', {'class': 'text-block persons'}).text
        return info.replace('\t', '').replace('\r', '').split('\n\n\n\n')[1:] or None

    def fetch_plot(self, series_id, season_number, episode_number):
        doc = self._get_episode_doc(series_id, season_number, episode_number)
        info_and_plot = doc.find('div', {'class': 'text-block description'}).text
        if len(info_and_plot) != 0:
            plot = info_and_plot.split('Описание')[-1].strip(' \t\n\r')
            return plot.split('\u2026')[0].strip()
        else:
            return None

    def _get_series_doc(self, series_id):
        return self.fetch(self.BASE_URL + "/series/%s" % self.series_web_ids_dict[str(series_id)])

    def _get_episode_doc(self, series_id, season_number, episode_number):
        return self.fetch(self.BASE_URL + '/series/%s/season_%s/episode_%s/'
                          % (self.series_web_ids_dict[str(series_id)], season_number, episode_number))

    def _get_episodes_doc(self, series_id):
        return self.fetch(self.BASE_URL + '/series/%s/seasons/' % self.series_web_ids_dict[str(series_id)])

    def _get_new_episodes_doc(self, page):
        return self.fetch(self.BASE_URL + "/new/page_%s" % page)

    def get_series_info(self, series_id):

        doc = self._get_series_doc(series_id)
        with Timer(logger=self.log, name='Parsing series info with ID %s' % series_id):
            title = doc.find('h1', {'class': 'header'})
            series_title = title.find('div', {'class': 'title-ru'}).text
            original_title = title.find('div', {'class': 'title-en'}).text
            image = series_image_url(series_id)
            icon = series_icon_url(series_id)
            plot = self.get_series_plot(series_id, doc)
            studio_genre_premiere = doc.find('div', {'class': 'details-pane'}).text
            res = re.search('Страна:([\t\r\n]+)(.+)', studio_genre_premiere)
            country = res.group(0).split()[-1] if res else None
            res = re.search('Премьера:( .+)', studio_genre_premiere)
            year = res.group(0).split()[-1] if res else None
            res = re.search('Жанр: (\r\n)+((.+)[, ]?\r\n)+', studio_genre_premiere)
            genres = re.split('; |, |\*|\n', res.group(0)) if res else None
            if genres is not None:
                genres = [g.strip() for g in genres if (len(g) > 3 and ':' not in g)]
            actors = self.fetch_crew(series_id, 1)
            if actors is not None:
                actors = [(actor.strip().split('\n')[2], actor.strip().split('\n')[-1])
                          for actor in actors if len(actor.strip()) > 3]
            directors = self.fetch_crew(series_id, 2)
            if directors is not None:
                directors = [director.strip().split('\n')[2] for director in directors]
            writers = self.fetch_crew(series_id, 4)
            if writers is not None:
                writers = [writer.strip().split('\n')[2] for writer in writers]
            counter = self._get_episodes_doc(series_id)
            body = counter.find('div', {'class': 'series-block'})
            episodes_count = len(body.find('td', {'class': 'zeta'}))
            seasons_count = len(body.find('div', {'class': 'movie-details-block'}))
            poster = season_poster_url(series_id, seasons_count)

            series = Series(series_id, series_title, original_title, country, year, genres,
                            image, icon, poster, plot, actors, directors, writers, seasons_count, episodes_count)
            self.log.info("Parsed '%s' series info successfully" % series_title)
            self.log.debug(repr(series).decode("utf-8"))

        return series

    def get_series_plot(self, series_id, doc=None):
        if doc is None:
            doc = self._get_series_doc(series_id)
        info_and_plot = doc.find('div', {'class': 'text-block description'}).text
        info = info_and_plot.split('Описание')[-1].strip(' \t\n\r')
        if len(info.split('Сюжет')) == 2:
            if len(info.split('Сюжет')[0]) == 0:
                info = info.strip(' \t\n\r')
            else:
                info = info.split('Сюжет')[-1].strip(' \t\n\r')
        return info

    def get_series_bulk(self, series_ids):
        """
        :rtype : dict[int, Series]
        """
        if not series_ids:
            return {}
        cached_details = self.series_cache.keys()
        not_cached_ids = [_id for _id in series_ids if _id not in cached_details]
        results = dict((_id, self.series_cache[_id]) for _id in series_ids if _id in cached_details)
        if not_cached_ids:
            with Timer(logger=self.log,
                       name="Bulk fetching series with IDs " + ", ".join(str(i) for i in not_cached_ids)):
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = [executor.submit(self.get_series_info, _id) for _id in not_cached_ids]
                    for future in as_completed(futures):
                        result = future.result()
                        self.series_cache[result.id] = results[result.id] = result
        return results

    def get_series_cached(self, series_id):
        return self.get_series_bulk([series_id])[series_id]

    def get_series_episodes(self, series_id):

        doc = self._get_episodes_doc(series_id)
        series_info = self.get_series_plot(series_id)
        if series_id in self.watched_episodes.keys():
            watched_episodes = self.watched_episodes[series_id]
        else:
            watched_episodes = []
        episodes = []
        need_plots = plugin.get_setting('fetch-info', bool)
        season_idx_counter = None
        with Timer(logger=self.log, name='Parsing episodes of series with ID %d' % series_id):
            title = doc.find('div', {'class': 'title-block'})
            series_title = title.find('div', {'class': 'title-en'}).text
            episodes_data = doc.find('div', {'class': 'series-block'})
            seasons = episodes_data.find('div', {'class': 'serie-block'})
            for s in seasons:
                image = series_image_url(series_id)
                icon = series_icon_url(series_id)
                full_season = s.find('div', {'class': 'movie-details-block'})
                if len(full_season.strings) != 0:
                    onclick = str(full_season.find('div', {'class': 'external-btn'}).attrs('onClick'))
                    full_season_indicator, season_number, episode_number = parse_onclick(onclick)
                    episode_number = FULL_SEASON_TORRENT_NUMBER
                    episode_title = '%dй Сезон Полностью' % season_number
                    orig_title = 'Full Season %d' % season_number
                    poster = season_poster_url(series_id, season_number)
                    season = Episode(series_id, series_title, season_number, episode_number,
                                     episode_title, orig_title, None, icon, poster, image,
                                     series_info, False)
                    if full_season_indicator != 0:
                        episodes.append(season)
                        season_idx_counter = len(episodes) - 1

                episodes_table = s.find('table', {'class': 'movie-parts-list'})
                if episodes_table.attrs('id')[0] == u'season_series_999':
                    gamma_class = 'gamma additional'
                else:
                    gamma_class = 'gamma'
                episode_dates = [str(d.split(':')[-1])[1:] for d in
                                 episodes_table.find('td', {'class': 'delta'}).strings]
                onclick = episodes_table.find('div', {'class': 'external-btn'}).attrs('onClick')
                titles = episodes_table.find('td', {'class': gamma_class})
                orig_titles = [str(t) for t in titles.find('span')]
                titles = [t.split('\n')[0] for t in titles.strings]
                if len(onclick)/2 < len(titles):
                    del episode_dates[0], titles[0], orig_titles[0]
                all_episodes_are_watched = False
                for i in range(len(episode_dates)):
                    release_date = parse_release_date(episode_dates[i])
                    full_season_indicator, season_number, episode_number = parse_onclick(onclick[i*2])
                    episode_title = titles[i]
                    orig_title = orig_titles[i]

                    if need_plots:
                        plot = self.fetch_plot(series_id, season_number, episode_number)
                        if plot is None:
                            plot = series_info
                    else:
                        plot = series_info

                    poster = episode_poster_url(series_id, season_number, episode_number)
                    watched = False
                    if (season_number, episode_number) in watched_episodes:
                        watched = True
                    else:
                        all_episodes_are_watched = False
                    episode = Episode(series_id, series_title, season_number, episode_number,
                                      episode_title, orig_title, release_date, icon, poster, image,
                                      plot, watched)
                    if full_season_indicator != 0:
                        episodes.append(episode)
                if season_idx_counter is not None:
                    season = episodes[season_idx_counter]
                    season = season._replace(release_date=episodes[len(episodes) - 1].release_date)
                    if all_episodes_are_watched:
                        season = season._replace(watched=True)
                    episodes[season_idx_counter] = season
                    season_idx_counter = None

            self.log.info("Got %d episode(s) successfully" % (len(episodes)))
            self.log.debug(repr(episodes).decode("utf-8"))
        return episodes

    def get_series_episodes_bulk(self, series_ids):
        """
        :rtype : dict[int, list[Episode]]
        """
        if not series_ids:
            return {}
        results = {}
        with Timer(logger=self.log,
                   name="Bulk fetching series episodes with IDs " + ", ".join(str(i) for i in series_ids)):
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = dict((executor.submit(self.get_series_episodes, _id), _id) for _id in series_ids)
                for future in as_completed(futures):
                    _id = futures[future]
                    results[_id] = future.result()
        return results

    def browse_episodes(self, skip=0):

        self.check_for_new_series()
        self.ensure_authorized()
        page = (skip or 0) / 10 + 1
        doc = self._get_new_episodes_doc(page)
        need_plots = plugin.get_setting('fetch-info', bool)
        with Timer(logger=self.log, name='Parsing episodes list'):
            body = doc.find('div', {'class': 'content history'})
            series_titles = body.find('div', {'class': 'name-ru'}).strings
            episode_titles = body.find('div', {'class': 'alpha'}).strings[::2]
            original_titles = body.find('div', {'class': 'beta'}).strings[::2]
            original_titles = [o_t.encode('utf-8') for o_t in original_titles]
            release_dates = body.find('div', {'class': 'alpha'}).strings[1::2]
            release_dates = [r_d.split(' ')[-1] for r_d in release_dates]
            release_dates = [parse_release_date(r_d) for r_d in release_dates]
            paging = doc.find('div', {'class': 'pagging-pane'})
            selected_page = paging.find('a', {'class': 'item active'}).text
            last_page = paging.find('a', {'class': 'item'}).last.text
            self.has_more = int(selected_page) < int(last_page)
            icons = body.find('img', {'class': 'thumb'}).attrs('src')
            series_ids = [int(i.split('/')[4]) for i in icons]
            se = body.find('div', {'class': 'left-part'}).strings
            season_numbers = []
            episode_numbers = []
            for s in se:
                try:  # Special episodes treatment
                    e_n = int(s.split(' ')[2])
                except:
                    e_n = FULL_SEASON_TORRENT_NUMBER
                try:
                    s_n = int(s.split(' ')[0])
                except:
                    s_n = FULL_SEASON_TORRENT_NUMBER
                    e_n = int(s.split(' ')[1])
                season_numbers.append(s_n)
                episode_numbers.append(e_n)
            plots = []
            posters = []
            watched = []
            icons = ['http:' + url for url in icons]
            images = [url.replace('/Posters/image', '/Posters/poster') for url in icons]
            for i in range(len(series_ids)):
                posters.append(episode_poster_url(series_ids[i], season_numbers[i], episode_numbers[i]))
                watched.append(self.is_watched(series_ids[i], season_numbers[i], episode_numbers[i]))
            if need_plots:
                for i in range(len(series_ids)):
                    plot = self.fetch_plot(series_ids[i], season_numbers[i], episode_numbers[i])
                    if plot is None:
                        plot = self.get_series_plot(series_ids[i])
                    plots.append(plot)
            else:
                plots = [' '] * len(series_ids)

            data = zip(series_ids, series_titles, season_numbers, episode_numbers,
                       episode_titles, original_titles, release_dates, icons, posters, images,
                       plots, watched)
            episodes = [Episode(*e) for e in data if e[0]]
            self.log.info("Got %d episode(s) successfully" % (len(episodes)))
            self.log.debug(repr(episodes).decode("utf-8"))
        return episodes


def parse_onclick(s):
    res = re.findall("PlayEpisode\('([^']+)','([^']+)','([^']+)'\)", s)
    if res:
        series_id, season, episode = res[0]
        series_id = int(series_id.lstrip("_"))
        season = int(season.split('.')[0])
        episode = int(episode)
        return series_id, season, episode
    else:
        return 0, 0, ""


def episode_poster_url(s_id, season_number, episode_number):
    return 'http://static.lostfilm.tv/Images/%s/Posters/e_%s_%s.jpg' % (s_id, season_number, episode_number)


def season_poster_url(s_id, season=1):
    return 'http://static.lostfilm.tv/Images/%s/Posters/shmoster_s%s.jpg' % (s_id, season)


def series_icon_url(s_id):
    return 'http://static.lostfilm.tv/Images/%s/Posters/image.jpg' % s_id


def series_image_url(s_id):
    return 'http://static.lostfilm.tv/Images/%s/Posters/poster.jpg' % s_id


def parse_release_date(release_date):
    if len(release_date) > 10:
        return str_to_date(release_date, '%d.%m.%Y %H:%M')
    elif len(release_date) > 1:
        return str_to_date(release_date, '%d.%m.%Y')
    else:
        return None
