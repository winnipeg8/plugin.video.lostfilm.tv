# -*- coding: utf-8 -*-

import support.titleformat as tf
import xbmc
from lostfilm.common import select_torrent_link, get_scraper, itemify_episodes, itemify_file, play_torrent, \
    itemify_series, BATCH_SERIES_COUNT, BATCH_EPISODES_COUNT, library_items, update_library_menu, \
    library_new_episodes, NEW_LIBRARY_ITEM_COLOR, check_last_episode, check_first_start
from lostfilm.scraper import FULL_SEASON_TORRENT_NUMBER
from support.common import lang, with_fanart, batch, download_torrent, get_torrent
from support.plugin import plugin
from support.torrent import Torrent
from xbmcswift2 import actions
from xbmcswift2.common import abort_requested


@plugin.route('/browse_season/<series>/<season>')
def browse_season(series, season):
    plugin.set_content('episodes')
    select_quality = plugin.request.arg('select_quality')
    series = get_scraper().get_series_cached(series)
    link = select_torrent_link(series.id, season, FULL_SEASON_TORRENT_NUMBER, select_quality)
    if not link:
        return []
    torrent = get_torrent(link.url)
    items = [itemify_file(torrent.file_name, series, season, f) for f in torrent.files]
    return with_fanart(items)


@plugin.route('/play_file/<path>/<file_id>')
def play_file(path, file_id):
    torrent = Torrent(file_name=path)
    play_torrent(torrent, file_id)


@plugin.route('/download/<series>/<season>/<episode>')
def download(series, season, episode):
    link = select_torrent_link(series, season, episode, force=True)
    if not link:
        return
    torrent = get_torrent(link.url)
    download_torrent(torrent)


@plugin.route('/play_episode/<series>/<season>/<episode>')
def play_episode(series, season, episode):
    select_quality = plugin.request.arg('select_quality')
    link = select_torrent_link(series, season, episode, select_quality)
    if not link:
        return
    torrent = get_torrent(link.url)
    library_new_episodes().remove_by(series, season, episode)
    #     scraper = get_scraper()
    #     scraper.toggle_watched(series_id, season, episode)
    play_torrent(torrent)


@plugin.route('/browse_series/<series_id>')
def browse_series(series_id):
    plugin.set_content('episodes')
    scraper = get_scraper()
    episodes = scraper.get_series_episodes(series_id)
    items = itemify_episodes(episodes, same_series=True)
    plugin.finish(items=with_fanart(items), cache_to_disc=False)


@plugin.route('/browse_all_series')
def browse_all_series():
    plugin.set_content('tvshows')
    scraper = get_scraper()
    all_series_ids = scraper.get_all_series_ids()
    total = len(all_series_ids)
    for batch_ids in batch(all_series_ids, BATCH_SERIES_COUNT):
        if abort_requested():
            break
        series = scraper.get_series_bulk(batch_ids)
        items = [itemify_series(series[i]) for i in batch_ids]
        plugin.add_items(with_fanart(items), total)
    plugin.finish()


@plugin.route('/browse_favorite_series')
def browse_favorite_series():
    plugin.set_content('tvshows')
    scraper = get_scraper()
    series_ids = scraper.get_favorite_series()
    library = library_items()
    for s_id in series_ids:
        if s_id not in library:
            add_to_library(s_id)
            scraper.add_series(s_id)
    total = len(series_ids)
    for batch_ids in batch(series_ids, BATCH_SERIES_COUNT):
        if abort_requested():
            break
        series = scraper.get_series_bulk(batch_ids)
        items = [itemify_series(series[i], highlight_library_items=False) for i in batch_ids]
        plugin.add_items(with_fanart(items), total)
    plugin.finish()


@plugin.route('/add_to_library/<series_id>')
def add_to_library(series_id):
    items = library_items()
    if series_id not in items:
        items.append(series_id)
        scraper = get_scraper()
        scraper.add_series(series_id)
    plugin.set_setting('update-library', True)


@plugin.route('/remove_from_library/<series_id>')
def remove_from_library(series_id):
    items = library_items()
    if series_id in items:
        items.remove(series_id)
        scraper = get_scraper()
        scraper.add_series(series_id)
    library_new_episodes().remove_by(series_id=series_id)
    plugin.set_setting('update-library', True)


@plugin.route('/')
def index():
    plugin.set_content('episodes')
    skip = plugin.request.arg('skip')
    per_page = plugin.get_setting('per-page', int)
    scraper = get_scraper()
    episodes = scraper.browse_episodes(skip)
    if episodes and not skip:
        check_last_episode(episodes[0])
    check_first_start()
    new_episodes = library_new_episodes()
    new_str = "(%s) " % tf.color(str(len(new_episodes)), NEW_LIBRARY_ITEM_COLOR) if new_episodes else ""
    total = len(episodes)
    header = [
        {'label': lang(40401), 'path': plugin.url_for('browse_all_series')},
        {'label': lang(40407) % new_str, 'path': plugin.url_for('browse_favorite_series'),
         'context_menu': update_library_menu()},
    ]
    items = []
    if skip:
        skip_prev = max(skip - per_page, 0)
        total += 1
        items.append({
            'label': lang(34003),
            'path': plugin.request.url_with_params(skip=skip_prev)
        })
    elif header:
        items.extend(header)
        total += len(header)
    plugin.add_items(with_fanart(items), total)
    for batch_res in batch(episodes, BATCH_EPISODES_COUNT):
        if abort_requested():
            break
        items = itemify_episodes(batch_res)
        plugin.add_items(with_fanart(items), total)
    items = []
    if scraper.has_more:
        skip_next = (skip or 0) + per_page
        items.append({
            'label': lang(34004),
            'path': plugin.request.url_with_params(skip=skip_next)
        })
    plugin.finish(items=with_fanart(items),
                  cache_to_disc=False,
                  update_listing=skip is not None)


@plugin.route('/create_source')
def create_source():
    from lostfilm.common import create_lostfilm_source
    create_lostfilm_source()


@plugin.route('/update_library')
def update_library_on_demand():
    plugin.set_setting('update-library', True)
    from lostfilm.common import update_library
    update_library()


@plugin.route('/toggle_episode_watched/<series_id>/<season>/<episode>')  # /<watched>')
def toggle_episode_watched(series_id, season, episode):  # , watched):
    # if xbmc.getInfoLabel('ListItem.PlayCount') > 0 and watched:
    #     scraper = get_scraper()
    #     scraper.toggle_watched(series_id, season, episode)
    xbmc.executebuiltin(actions.toggle_watched())
    if series_id in library_items():
        library_new_episodes().remove_by(series_id, season, episode)


@plugin.route('/mark_series_watched/<series_id>')
def mark_series_watched(series_id):
    # scraper = get_scraper()
    # scraper.toggle_watched(series_id)
    xbmc.executebuiltin(actions.toggle_watched())
    if series_id in library_items():
        library_new_episodes().remove_by(series_id)

        #
        # import utilities
        # import kodiUtilities
        # import xbmc
        # media_type = kodiUtilities.getMediaType()
        # if media_type in ['movie', 'show', 'season', 'episode']:
        #     data = {'media_type': media_type}
        #     if utilities.isMovie(media_type):
        #         dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
        #         result = kodiUtilities.getMovieDetailsFromKodi(dbid, ['imdbnumber', 'title', 'year', 'playcount'])
        #         if result:
        #             if result['playcount'] == 0:
        #                 data['id'] = result['imdbnumber']
        #             else:
        #                 logger.debug("Movie alread marked as watched in Kodi.")
        #         else:
        #             logger.debug("Error getting movie details from Kodi.")
        #             return
        #
        #     elif utilities.isEpisode(media_type):
        #         dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
        #         result = kodiUtilities.getEpisodeDetailsFromKodi(dbid, ['showtitle', 'season', 'episode', 'tvshowid', 'playcount'])
        #         if result:
        #             if result['playcount'] == 0:
        #                 data['id'] = result['imdbnumber']
        #                 data['season'] = result['season']
        #                 data['number'] = result['episode']
        #                 data['title'] = result['showtitle']
        #             else:
        #                 logger.debug("Episode already marked as watched in Kodi.")
        #         else:
        #             logger.debug("Error getting episode details from Kodi.")
        #             return
        #
        #     elif utilities.isSeason(media_type):
        #         showID = None
        #         showTitle = xbmc.getInfoLabel('ListItem.TVShowTitle')
        #         result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {'properties': ['title', 'imdbnumber', 'year']}, 'id': 0})
        #         if result and 'tvshows' in result:
        #             for show in result['tvshows']:
        #                 if show['title'] == showTitle:
        #                     showID = show['tvshowid']
        #                     data['id'] = show['imdbnumber']
        #                     data['title'] = show['title']
        #                     break
        #         else:
        #             logger.debug("Error getting TV shows from Kodi.")
        #             return
        #
        #         season = xbmc.getInfoLabel('ListItem.Season')
        #         if season == "":
        #             season = 0
        #         else:
        #             season = int(season)
        #
        #         result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': showID, 'season': season, 'properties': ['season', 'episode', 'playcount']}, 'id': 0})
        #         if result and 'episodes' in result:
        #             episodes = []
        #             for episode in result['episodes']:
        #                 if episode['playcount'] == 0:
        #                     episodes.append(episode['episode'])
        #
        #             if len(episodes) == 0:
        #                 logger.debug("'%s - Season %d' is already marked as watched." % (showTitle, season))
        #                 return
        #
        #             data['season'] = season
        #             data['episodes'] = episodes
        #         else:
        #             logger.debug("Error getting episodes from '%s' for Season %d" % (showTitle, season))
        #             return
        #
        #     elif utilities.isShow(media_type):
        #         dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
        #         result = kodiUtilities.getShowDetailsFromKodi(dbid, ['year', 'imdbnumber'])
        #         if not result:
        #             logger.debug("Error getting show details from Kodi.")
        #             return
        #         showTitle = result['label']
        #         data['id'] = result['imdbnumber']
        #         result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': dbid, 'properties': ['season', 'episode', 'playcount', 'showtitle']}, 'id': 0})
        #         if result and 'episodes' in result:
        #             i = 0
        #             s = {}
        #             for e in result['episodes']:
        #                 data['title'] = e['showtitle']
        #                 season = str(e['season'])
        #                 if not season in s:
        #                     s[season] = []
        #                 if e['playcount'] == 0:
        #                     s[season].append(e['episode'])
        #                     i += 1
        #
        #             if i == 0:
        #                 logger.debug("'%s' is already marked as watched." % showTitle)
        #                 return
        #
        #             data['seasons'] = dict((k, v) for k, v in s.iteritems() if v)
        #         else:
        #             logger.debug("Error getting episode details for '%s' from Kodi." % showTitle)
        #             return
        #
        #     if len(data) > 1:
        #         logger.debug("Marking '%s' with the following data '%s' as watched on Trakt.tv" % (media_type, str(data)))
        #         data['action'] = 'markWatched'
        #
        # # execute toggle watched action
        # xbmc.executebuiltin("Action(ToggleWatched)")
