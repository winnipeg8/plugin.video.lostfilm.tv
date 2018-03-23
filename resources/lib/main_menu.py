# -*- coding: utf-8 -*-


import xbmcgui
import xbmcplugin
import urllib

from encoding import *
from html_requests import InfoFetcher
from html_document import HtmlDocument


class TorrentLinks:
    def __init__(self, quality, size):
        self.quality = quality
        self.size = size


class MainMenuOptions(InfoFetcher):

    def __init__(self, addon, base_url, addon_handle, user_agent, paths, cj, logger):
        InfoFetcher.__init__(self, addon, base_url, addon_handle, user_agent, paths, cj, logger)
        self.default_cover, self.default_fanart = paths.default_cover, paths.default_fanart
        self.quality = {'SD': (0, 'sd'), 'HD_720': (1, '720', '720p', 'mp4'), 'HD_1080': (2, '1080p', '1080', 'hd')}

    def detect_quality(self, selected_quality, given_qualities):
        for i in range(len(given_qualities)):
            if given_qualities[i] in self.quality[selected_quality]:
                return i
        return 0

    @staticmethod
    def episode_poster_url(s_id, season_number, episode_number):
        return 'http://static.lostfilm.tv/Images/%s/Posters/e_%s_%s.jpg' % (s_id, season_number, episode_number)

    @staticmethod
    def season_poster_url(s_id, season=1):
        return 'http://static.lostfilm.tv/Images/%s/Posters/shmoster_s%s.jpg' % (s_id, season)

    @staticmethod
    def series_icon_url(s_id):
        return 'http://static.lostfilm.tv/Images/%s/Posters/image.jpg' % s_id

    @staticmethod
    def tvshow_image_url(s_id):
        return 'http://static.lostfilm.tv/Images/%s/Posters/poster.jpg' % s_id

    @staticmethod
    def parse_size(size):
        size = size.strip(u" \t\xa0")
        if size.isdigit():
            return long(size)
        else:
            num, qua = size[:-2].rstrip(), size[-2:].lower()
            if qua == u'mb' or qua == u'мб':
                return long(float(num) * 1024 * 1024)
            elif qua == u'gb' or qua == u'гб':
                return long(float(num) * 1024 * 1024 * 1024)
            elif qua == u'tb' or qua == u'тб':
                return long(float(num) * 1024 * 1024 * 1024 * 1024)

    def color_favorites(self, title, tvshow_id, specials):
        specials_info = [self.get_info(tvshow) for tvshow in specials]
        special_ids = [tvshow['id'] for tvshow in specials_info]
        if tvshow_id in special_ids:
            title = '[COLOR ff6efdfd]' + title + '[/COLOR]'
        return title

    def all_tvshows(self):
        xbmcplugin.setContent(self.addon_handle, 'tvshows')
        tvshows = self.get_tvshows()
        tvshows_fav = self.get_favorites()
        for tvshow in tvshows:
            tvshow_info = self.get_info(tvshow)
            tvshow_title = self.color_favorites(tvshow_info["title"], tvshow_info['id'], tvshows_fav)
            self.add_item_on_screen("[B]" + self.xbmc_path(tvshow_title) + "[/B]",
                                    "Getlist", tvshow_info, '', len(tvshows))

    def lf_favorites(self):
        xbmcplugin.setContent(self.addon_handle, 'tvshows')
        tvshows = self.get_favorites()
        for tvshow in tvshows:
            tvshow_info = self.get_info(tvshow)
            self.add_item_on_screen("[B]" + self.xbmc_path(tvshow_info["title"]) + "[/B]",
                                    "Getlist", tvshow_info, '', len(tvshows))

    def main_screen(self):
        # xbmcplugin.setContent(self.addon_handle, 'episodes')
        self.add_item_on_screen("[B]Все сериалы[/B]", "Serials", {}, "")
        self.add_item_on_screen("[B]Избранные сериалы[/B]", "LF_favorites", {}, "")
        tvshows_fav = self.get_favorites()
        n = int(self.addon.getSetting("Pages")) + 1
        for page in range(1, n + 1):
            for episode in self.new_episodes_page(page):
                if isinstance(episode['season'], str) and isinstance(episode['episode'], str):
                    season_episode = episode['season'] + "." + episode['episode']
                    series_title = episode['tvshowtitle']
                    episode_title = episode['title']
                    series_season_episode_id = repr((episode['id'], episode['season'], episode['episode']))
                    series_title = self.color_favorites(series_title, episode['id'], tvshows_fav)
                    self.add_item_on_screen(season_episode + " [B][COLOR FFFFFFFF]" + self.xbmc_path(series_title) +
                                            ":[/COLOR][/B] " + self.xbmc_path(episode_title),
                                            "Releases", episode, '', 10 * n, series_season_episode_id)

    def get_tvshow_episodes(self, tvshow_link):
        xbmcplugin.setContent(self.addon_handle, 'episodes')
        episodes_list = self.get_episodes(tvshow_link)
        total_episodes = len(episodes_list)
        for episode in episodes_list:
            tvshow_id, season_, episode_ = eval(episode[1])
            if episode_ == '999':
                self.add_item_on_screen("  [B][COLOR FF00FF00]" + episode[0]['title'] +
                                        "[/COLOR][/B]", "Releases", episode[0], '', total_episodes, episode[1])
            else:
                se = season_ + "." + episode_
                self.add_item_on_screen(se + " - [B]" + episode[0]['title'] + "[/B]",
                                        "Releases", episode[0], '', total_episodes, episode[1])

    def release_torrents(self, series_season_episode_id):
        self.lostfilm_login()
        tvshow_id, season_n, episode_n = eval(series_season_episode_id)
        query = {'c': tvshow_id, 's': season_n, 'e': episode_n}
        episode_url = 'http://www.lostfilm.tv/v_search.php?' + urllib.urlencode(query)
        response = encode_to_utf8(self.send_get_request(episode_url))
        if 'log in first' in response:
            self.logger.log.info('Auth error')
            self.show_message('lostfilm.tv', 'Ошибка авторизации')
            return
        tracker_url = response[response.find('("http://retre') + 2:response.find('");')]
        tracker_response = self.send_get_request(tracker_url)
        response_html = HtmlDocument.from_string(tracker_response)
        links_list = response_html.find('div', {'class': 'inner-box--list'})
        link_blocks = links_list.find('div', {'class': 'inner-box--item'})
        links = []
        for link_block in link_blocks:
            link_quality = link_block.find('div', {'class': 'inner-box--label'}).text.lower()
            links_list_row = link_block.find('div', {'class': 'inner-box--link sub'})
            links_href = links_list_row.find('a').attr('href')
            link_desc = link_block.find('div', {'class': 'inner-box--desc'}).text
            size = re.search('(\d+\.\d+ ..\.)', link_desc).group(1)[:-1]
            if episode_n != '999':
                cover = self.episode_poster_url(tvshow_id, season_n, episode_n)
            else:
                cover = self.season_poster_url(tvshow_id, season_n)
            # label_info = {'cover': cover, 'title': link_desc, 'episode': episode_n, 'season': season_n}
            links.append([link_desc, links_href, cover, TorrentLinks(link_quality, size)])
        return links

    def open_torrent(self, url_string, tvshow_id='0', cse='(0,0,0)'):
        torrent_data = self.get_torrent(url_string)
        if torrent_data is not None:
            torrent = bdecode(torrent_data)
            cover = self.icon
            try:
                torrent_files = torrent['info']['files']
                ind = 0
                for torrent_file in torrent_files:
                    name = encode_to_utf8_ru(torrent_file['path'][-1])
                    listitem = xbmcgui.ListItem(name, iconImage=cover, thumbnailImage=cover)
                    listitem.setProperty('IsPlayable', 'true')
                    uri = self.build_url({'mode': 'PlayTorrent', 'id': tvshow_id, 'ind': ind, 'url': url_string})
                    xbmcplugin.addDirectoryItem(self.addon_handle, uri, listitem)
                    ind += 1
            except Exception, err:
                self.logger.log.info('Could not obtain files from the torrent: %s' % err)
                name = torrent['info']['name']
                listitem = xbmcgui.ListItem(name, iconImage=cover, thumbnailImage=cover)
                listitem.setProperty('IsPlayable', 'true')
                self.play(url_string, 0, cse)

    def add_item_on_screen(self, title="", mode="", info=None, url='', total=15, cse='(0,0,0)'):

        if info is None:
            info = {}
        tvshow_id = info.get('id', '0')
        tvshow_link = info.get('link', '')
        episode_n = info.get('episode', '0')
        season_n = info.get('season', '1')
        if tvshow_id == '0':
            cover = info.get('cover', self.default_cover)
            fanart = self.default_fanart
        else:
            cover = self.season_poster_url(tvshow_id, season_n)
            if mode == "Releases":
                if episode_n != '999':
                    fanart = self.episode_poster_url(tvshow_id, season_n, episode_n)
                else:
                    fanart = self.tvshow_image_url(tvshow_id)
            else:
                fanart = self.tvshow_image_url(tvshow_id)

        listitem = xbmcgui.ListItem(title)
        listitem.setArt({'poster': cover, 'fanart': fanart})
        try:
            listitem.setInfo(type="Video", infoLabels=info)
        except Exception, err:
            self.logger.log.info('Could not setInfo for item: %s' % err)
        listitem.setProperty('fanart_image', fanart)

        purl = self.build_url({'mode': mode, 'id': tvshow_id, 'cse': cse, 'link': tvshow_link})
        if url != "":
            purl = purl + '&url=' + urllib.quote_plus(url)

        folder = True

        if mode == "OpenTorrent" and episode_n != "999":
            listitem.setProperty('IsPlayable', 'true')
            folder = False

        if self.addon.getSetting("Quality") != '0' and mode == "Releases":
            listitem.addContextMenuItems([('[B]Выбрать качество[/B]', 'Container.Update("%s")' %
                                           self.build_url({'mode': 'SelectQuality', 'cse': cse, 'id': tvshow_id,
                                                           'link': tvshow_link})),
                                          ('[B]Все серии[/B]', 'Container.Update("%s")' %
                                           self.build_url({'mode': 'Getlist', 'id': tvshow_id, 'link': tvshow_link}))])
            listitem.setProperty('IsPlayable', 'true')
            purl = self.build_url({'mode': 'Autoplay', 'id': tvshow_id, 'cse': cse})
            if episode_n != "999":
                folder = False
        elif mode == "Releases":
            listitem.addContextMenuItems([('[B]Все серии[/B]', 'Container.Update("%s")' %
                                           self.build_url({'mode': 'Getlist', 'id': tvshow_id, 'link': tvshow_link}))])
            purl = self.build_url({'mode': 'SelectQuality', 'cse': cse})
            if episode_n != "999":
                listitem.setProperty('IsPlayable', 'true')
                folder = False
        #         listitem.addContextMenuItems([('[B]Добавить в просмотренные на LF[/B]', 'Container.Update("%s")' %
        #                                        self.build_url({'mode': 'MarkWatched', 'cse': cse}))])
        # elif mode == "Getlist":
        #     listitem.addContextMenuItems([('[B]Добавить в просмотренные на LF[/B]', 'Container.Update("%s")' %
        #                                    self.build_url({'mode': 'MarkWatched', 'cse': cse}))])
        xbmcplugin.addDirectoryItem(self.addon_handle, purl, listitem, folder, total)

    def autoplay(self, cse):
        links = self.release_torrents(cse)
        qualities = ['HD_720', 'HD_1080', 'SD']
        quality_option = int(self.addon.getSetting("Quality"))
        desired_quality = qualities[quality_option]
        given_qualities = [q[3].quality for q in links]
        i = self.detect_quality(desired_quality, given_qualities)
        if eval(cse)[2] != "999":
            self.play(links[i][1], 0, cse)
        else:
            self.open_torrent(links[i][1], eval(cse)[0])
            xbmcplugin.setPluginCategory(self.addon_handle, self.addon.getAddonInfo('name'))
            xbmcplugin.addSortMethod(self.addon_handle, xbmcplugin.SORT_METHOD_LABEL)
            xbmcplugin.endOfDirectory(self.addon_handle)

    def select_quality(self, cse):
        links = self.release_torrents(cse)
        # options = ["%s / %s" % (l[3].quality.upper(), l[3].size) for l in links]
        options = [l[0] for l in links]
        res = xbmcgui.Dialog().select('Выберите качество', options)
        if res < 0:
            return
        if eval(cse)[2] != '999':
            self.play(links[res][1], 0, cse)
        else:
            self.open_torrent(links[res][1], eval(cse)[0])
            xbmcplugin.setPluginCategory(self.addon_handle, self.addon.getAddonInfo('name'))
            xbmcplugin.addSortMethod(self.addon_handle, xbmcplugin.SORT_METHOD_LABEL)
            xbmcplugin.endOfDirectory(self.addon_handle)
