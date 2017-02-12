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
from util.htmldocument import HtmlDocument
from util.timer import Timer

FULL_SEASON_TORRENT_NUMBER = 999


class Series(namedtuple('Series', ['id', 'web_id', 'title', 'original_title', 'country', 'year', 'genres',
                                   'image', 'icon', 'poster', 'plot', 'seasons_count', 'episodes_count'])):
    pass


class Episode(namedtuple('Episode', ['series_id', 'web_id', 'series_title', 'season_number', 'episode_number',
                                     'episode_title', 'original_title', 'release_date', 'icon', 'poster', 'image',
                                     'watched'])):

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

    @property
    def is_multi_episode(self):
        return False
        # "-" in self.episode_number
        # need to handle multiple episodes

    @property
    def episode_numbers(self):
        if self.is_multi_episode:
            start, end = self.episode_number.split("-", 2)
            return range(int(start), int(end) + 1)
        else:
            return [int(self.episode_number)]


class Quality(Attribute):
    def get_lang_base(self):
        return 40208

    SD = (0, 'sd')
    HD_720 = (1, '720', '720p', 'mp4', 'hd')
    HD_1080 = (2, '1080p', '1080')

    def __lt__(self, other):
        return self.id < other.id


TorrentLink = namedtuple('TorrentLink', ['quality', 'url', 'size'])


class LostFilmScraper(AbstractScraper):
    BASE_URL = "http://www.lostfilm.tv"
    LOGIN_URL = "http://www.lostfilm.tv/ajaxik.php"
    BLOCKED_MESSAGE = "Контент недоступен на территории Российской Федерации"

    def __init__(self, login, password, cookie_jar=None, series_ids_db=None,
                 xrequests_session=None, series_cache=None, max_workers=10, anonymized_urls=None):
        super(LostFilmScraper, self).__init__(xrequests_session, cookie_jar)
        self.series_cache = series_cache if series_cache is not None else {}
        self.series_ids_db = series_ids_db
        self.series_web_ids_dict, self.series_ids = self.load_series_web_ids_dict()
        self.max_workers = max_workers
        self.response = None
        self.login = login
        self.password = password
        self.has_more = None
        self.anonymized_urls = anonymized_urls if anonymized_urls is not None else []
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; WOW64) ' \
                                             'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                                             'Chrome/58.0.3004.3 ' \
                                             'Safari/537.36'
        self.session.add_proxy_need_check(self._check_content_is_blocked)
        self.session.add_proxy_validator(self._validate_proxy)

    def fetch_series_ids(self):

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
        web_ids = [re.sub('&', 'and', (re.sub(' ', '_', re.sub('[^a-zA-Z0-9-& \n\.]', '', wid)))) for wid in web_ids]
        for i in range(len(web_ids)):
            if web_ids[i] == '11.22.63':
                web_ids[i] = '11-22-63'
        f = open(self.series_ids_db, 'w')
        for i in range(len(ids)):
            f.write("%d: %s\n" % (ids[i], web_ids[i]))
        f.close()

        # return ids

    def check_for_new_series(self):

        r = requests.post(self.LOGIN_URL, params={'type': 'search', 's': '3', 't': '0', 'act': 'serial', 'o': 0})
        ids_incr = [int(r1['img'].split("/")[4]) for r1 in r.json()['data']]
        if not (set(ids_incr).intersection(self.series_ids) == set(ids_incr)):
            self.fetch_series_ids()

    def load_series_web_ids_dict(self):

        if not (os.path.isfile(self.series_ids_db)):
            self.fetch_series_ids()

        f = open(self.series_ids_db, 'r')
        contents = f.readlines()
        web_ids = []
        ids = []
        for l in contents:
            ids.append(int(l.split(': ')[0]))
            web_id = l.split(': ')[1][:-1]
            web_ids.append(web_id)
        f.close()

        return dict(zip(ids, web_ids)), ids

    def get_all_series_ids(self):
        return self.series_ids

    def get_favorite_series(self):
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
        doc = self.fetch(self.BASE_URL + '/v_search.php', {
            'c': series_id, 's': season_number, 'e': episode_number
        })

        doc = self.fetch(doc.find('a').attr('href'))
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

    def fetch(self, url, params=None, data=None, json_req=False, **request_params):
        self.response = super(LostFilmScraper, self).fetch(url, params, data, **request_params)
        encoding = self.response.encoding
        if encoding == 'ISO-8859-1':
            encoding = 'utf-8'
        if json_req:
            return self.response.json()['data']
        else:
            return HtmlDocument.from_string(self.response.content, encoding)

    def _get_series_doc(self, web_id):
        return self.fetch(self.BASE_URL + "/series/%s" % web_id)

    def get_series_info(self, series_id):

        web_id = self.series_web_ids_dict[series_id]
        doc = self._get_series_doc(web_id)
        with Timer(logger=self.log, name='Parsing series info with ID %s' % web_id):
            title = doc.find('h1', {'class': 'header'})
            series_title = title.find('div', {'class': 'title-ru'}).text
            original_title = title.find('div', {'class': 'title-en'}).text
            image = doc.find('div', {'class': 'main_poster'}).attr('style')
            if image is not None:
                image = image.split("'")[1]
                image = 'http:' + image
                icon = image.replace('/Posters/poster', '/Posters/image')
            else:
                icon = image
            info_and_plot = doc.find('div', {'class': 'text-block description'}).text
            info = info_and_plot.split('Описание')[-1].strip(' \t\n\r')
            plot = info.split('Сюжет')[-1].strip(' \t\n\r')

            studio_genre_premiere = doc.find('div', {'class': 'details-pane'}).text
            res = re.search('Страна:([\t\r\n]+)(.+)', studio_genre_premiere)
            country = res.group(0).split()[-1] if res else None
            res = re.search('Премьера:( .+)', studio_genre_premiere)
            year = res.group(0).split()[-1] if res else None
            res = re.search('Жанр: (.+)\r\n', studio_genre_premiere)
            genres = res.group(1).split(', ') if res else None

            counter = self._get_series_doc('%s/seasons' % web_id)
            body = counter.find('div', {'class': 'series-block'})
            episodes_count = len(body.find('td', {'class': 'zeta'}))
            seasons_count = len(body.find('div', {'class': 'movie-details-block'}))

            poster = poster_url(series_id, seasons_count)
            series = Series(series_id, web_id, series_title, original_title, country, year, genres,
                            image, icon, poster, plot, seasons_count, episodes_count)
            self.log.info("Parsed '%s' series info successfully" % series_title)
            self.log.debug(repr(series).decode("utf-8"))

        return series

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

        web_id = self.series_web_ids_dict[series_id]
        doc = self._get_series_doc(web_id + '/seasons')
        watched_episodes = self.parse_watched_response(series_id)
        episodes = []
        with Timer(logger=self.log, name='Parsing episodes of series with ID %d' % series_id):
            title = doc.find('div', {'class': 'title-block'})
            # series_title = title.find('div', {'class': 'title-ru'}).text
            # original_title = title.find('div', {'class': 'title-en'}).text
            series_title = title.find('div', {'class': 'title-en'}).text
            image = None
            icon = None
            series_poster = None
            episodes_data = doc.find('div', {'class': 'series-block'})
            seasons = episodes_data.find('div', {'class': 'serie-block'})
            for s in seasons:
                full_season = s.find('div', {'class': 'movie-details-block'})
                if len(full_season.strings) != 0:
                    release_date = '01.01.2000'
                    if len(release_date) > 10:
                        release_date = str_to_date(release_date, '%d.%m.%Y %H:%M')
                    elif len(release_date) > 1:
                        release_date = str_to_date(release_date, '%d.%m.%Y')
                    else:
                        release_date = None
                    onclick = str(full_season.find('div', {'class': 'external-btn'}).attrs('onClick'))
                    full_season_indicator, season_number, episode_number = parse_onclick(onclick)
                    episode_number = FULL_SEASON_TORRENT_NUMBER
                    episode_title = '%dй Сезон Полностью' % season_number
                    orig_title = 'Full Season %d' % season_number
                    poster = poster_url(series_id, season_number)
                    if not series_poster:
                        series_poster = poster
                    watched = False
                    episode = Episode(series_id, web_id, series_title, season_number, episode_number,
                                      episode_title, orig_title, release_date, poster, poster, image, watched)
                    if full_season_indicator != 0:
                        episodes.append(episode)

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
                if len(onclick) < len(titles):
                    del episode_dates[0], titles[0], orig_titles[0]
                for i in range(len(episode_dates)):
                    release_date = episode_dates[i]
                    if len(release_date) > 10:
                        release_date = str_to_date(release_date, '%d.%m.%Y %H:%M')
                    elif len(release_date) > 1:
                        release_date = str_to_date(release_date, '%d.%m.%Y')
                    else:
                        release_date = None
                    full_season_indicator, season_number, episode_number = parse_onclick(onclick[i])
                    episode_title = titles[i]
                    orig_title = orig_titles[i]

                    poster = 'http://static.lostfilm.tv/Images/%s/Posters/e_%s_%s.jpg' \
                             % (series_id, season_number, episode_number)
                    image = poster_url(series_id, season_number)
                    if not series_poster:
                        series_poster = poster
                    watched = False
                    if (season_number, episode_number) in watched_episodes:
                        watched = True
                    episode = Episode(series_id, web_id, series_title, season_number, episode_number,
                                      episode_title, orig_title, release_date, icon, poster, image, watched)
                    if full_season_indicator != 0:
                        episodes.append(episode)

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
        self.fetch(self.BASE_URL)  # obtain cookies, otherwise throws an error when trying to start first time
        doc = self.fetch(self.BASE_URL + "/new/page_%s" % page)
        with Timer(logger=self.log, name='Parsing episodes list'):
            body = doc.find('div', {'class': 'content history'})
            series_titles = body.find('div', {'class': 'name-ru'}).strings
            web_ids = body.find('div', {'class': 'name-en'}).strings
            web_ids = [re.sub(' ', '_', re.sub('[^a-zA-Z0-9 \n\.]', '', wid)) for wid in web_ids]
            episode_titles = body.find('div', {'class': 'alpha'}).strings[::2]
            original_titles = body.find('div', {'class': 'beta'}).strings[::2]
            release_dates = body.find('div', {'class': 'alpha'}).strings[1::2]
            release_dates = [rd.split(' ')[-1] for rd in release_dates]
            release_dates = [str_to_date(d, '%d.%m.%Y') for d in release_dates]
            paging = doc.find('div', {'class': 'pagging-pane'})
            selected_page = paging.find('a', {'class': 'item active'}).text
            last_page = paging.find('a', {'class': 'item'}).last.text
            self.has_more = int(selected_page) < int(last_page)
            icons = body.find('img', {'class': 'thumb'}).attrs('src')
            series_ids = [int(i.split('/')[4]) for i in icons]
            se = body.find('div', {'class': 'left-part'}).strings
            season_numbers = [int(s.split(' ')[0]) for s in se]
            episode_numbers = [int(s.split(' ')[2]) for s in se]

            icons = ['http:' + url for url in icons]
            posters = [url.replace('/Posters/image', '/Posters/poster') for url in icons]
            images = [url.replace('/Posters/image', '/Posters/poster') for url in icons]
            for i in range(len(release_dates)):
                posters[i] = posters[i].replace('/Posters/poster',
                                                '/Posters/e_%s_%s' % (season_numbers[i], episode_numbers[i]))
            watched = [False] * len(series_ids)
            for i in range(len(series_ids)):
                if (season_numbers[i], episode_numbers[i]) in self.parse_watched_response(series_ids[i]):
                    watched[i] = True
            data = zip(series_ids, web_ids, series_titles, season_numbers, episode_numbers,
                       episode_titles, original_titles, release_dates, icons, posters, images, watched)
            episodes = [Episode(*e) for e in data if e[0]]
            self.log.info("Got %d episode(s) successfully" % (len(episodes)))
            self.log.debug(repr(episodes).decode("utf-8"))
        return episodes

    # def toggle_watched(self, series_id, season=None, episode=None):
    #     self.ensure_authorized()
    #     if season is None:
    #         episodes = self.get_series_episodes(series_id)
    #         for e in episodes:
    #             if not e.is_complete_season:
    #                 params = {'act': 'serial', 'type': 'markepisode',
    #                           'val': '%d-%d-%d' % (series_id, e.season_number, e.episode_number)}
    #                 r = self.fetch(self.LOGIN_URL, data=params)
    #     elif season != FULL_SEASON_TORRENT_NUMBER:
    #         params = {'act': 'serial', 'type': 'markepisode', 'val': '%d-%d-%d' % (series_id, season, episode)}
    #         r = self.fetch(self.LOGIN_URL, data=params)
    #     # else:
    #     #      params = {'act': 'serial', 'type': 'markseason', 'val': '%d-%d' % (series_id, season)}
    #     #     r = self.fetch(self.LOGIN_URL, data=params)

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
            answer = [(int(r.split('-')[-2]), int(r.split('-')[-1])) for r in parsed_response]

        return answer

    def add_series(self, series_id):
        params = {'act': 'serial', 'type': 'follow', 'id': series_id}
        r = self.fetch(self.LOGIN_URL, data=params)


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


def poster_url(id, season=1):
    return 'http://static.lostfilm.tv/Images/%s/Posters/shmoster_s%s.jpg' % (id, season)
