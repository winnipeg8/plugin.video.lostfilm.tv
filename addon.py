# -*- coding: utf-8 -*-


import os
import sys
import urlparse
import urllib2
import logging

import xbmc
import xbmcaddon
import xbmcplugin

from resources.lib.main_menu import MainMenuOptions
from resources.lib.cookie import MyCookieJar


def parse_queries(query):
    args = urlparse.parse_qs(query[1:])
    return args.get('mode', ['New'])[0], args.get('url', ['0'])[0], args.get('dir', ['.'])[0], \
           args.get('title', [''])[0], args.get('cse', ['(0,0,0)'])[0], args.get('img', [''])[0], \
           args.get('id', ['0'])[0], args.get('link', [''])[0], int(args.get('ind', [0])[0]), args.get('info', [{}])[0]


class Logger:
    def __init__(self, addon_id_=None):
        _log = logging.root
        _log.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(threadName)s - %(levelname)s - [%(name)s] %(message)s')
        handler.setFormatter(formatter)
        _log.addHandler(handler)
        if addon_id_ is not None:
            self.log = logging.getLogger(addon_id_)
        else:
            self.log = logging.getLogger(__name__)


class Paths:
    def __init__(self, addon_):
        self.addon_path = addon_.getAddonInfo('path')
        self.addon_data_path = xbmc.translatePath(addon_.getAddonInfo('profile'))
        self.icon = os.path.join(self.addon_path, 'resources', 'images', 'icon.png')
        self.thumb = os.path.join(self.addon_path, 'resources', 'images', 'icon.png')
        self.default_cover = os.path.join(self.addon_path, 'resources', 'images', 'cover.png')
        self.default_fanart = os.path.join(self.addon_path, 'resources', 'images', 'fanart.jpg')
        self.background = os.path.join(self.addon_path, 'resources', 'images', 'black.png')
        self.cookies_filename = os.path.join(self.addon_data_path, 'cookies')
        self.db_name = os.path.join(self.addon_data_path, 'lostfilm_info.db')


base_url = sys.argv[0]
addon_handle = int(sys.argv[1])
addon_query = sys.argv[2]
plugin_name = xbmcaddon.Addon().getAddonInfo('name')
addon_id = xbmcaddon.Addon().getAddonInfo('id')
addon = xbmcaddon.Addon(id=addon_id)
user_agent = 'Mozilla/5.0 (Windows NT 10.0; WOW64) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko) ' \
             'Chrome/58.0.3004.3 ' \
             'Safari/537.36'
logger = Logger(addon_id)

paths = Paths(addon)
cj = MyCookieJar(addon, paths.cookies_filename, user_agent, logger)
urllib2.install_opener(cj.opener)
playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)

xbmcplugin.setContent(addon_handle, 'tvshows')
# xbmc.executebuiltin('UpdateLibrary("video", "", "false")')
main_menu_options = MainMenuOptions(addon, base_url, addon_handle, user_agent, paths, cj, logger)

mode, url, dir_, title, episode_id, img, id_, link, file_index, info = parse_queries(addon_query)

if mode is None or mode == "New":
    if addon.getSetting("UpdateSeries"):
        main_menu_options.update_tvshows()
    main_menu_options.main_screen()
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    xbmcplugin.endOfDirectory(addon_handle)

elif mode == 'Serials':
    main_menu_options.all_tvshows()
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    if addon.getSetting("Sort") == '0':
        xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(addon_handle)

elif mode == 'LF_favorites':
    main_menu_options.lf_favorites()
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    if addon.getSetting("Sort") == '0':
        xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(addon_handle)

elif mode == 'OpenTorrent':
    main_menu_options.open_torrent(url, id_, episode_id)
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(addon_handle)

elif mode == 'Releases':
    main_menu_options.release_torrents(episode_id)
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(addon_handle)

if mode == "PlayTorrent":
    main_menu_options.play(url, file_index, episode_id)

if mode == 'Getlist':
    main_menu_options.get_tvshow_episodes(link)
    xbmcplugin.setPluginCategory(addon_handle, plugin_name)
    xbmcplugin.endOfDirectory(addon_handle)
    xbmc.sleep(300)
    xbmc.executebuiltin("Container.SetViewMode(%d)" % int(addon.getSetting("ListView")))

if mode == "Autoplay":
    main_menu_options.autoplay(episode_id)

if mode == "SelectQuality":
    main_menu_options.select_quality(episode_id)
