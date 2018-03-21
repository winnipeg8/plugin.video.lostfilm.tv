# -*- coding: utf-8 -*-

import os
import sys
import urllib
import urllib2
# import hashlib
import xbmc
import xbmcgui
import xbmcplugin
from encoding import bdecode

XBFONT_LEFT = 0x00000000
XBFONT_RIGHT = 0x00000001
XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004
XBFONT_TRUNCATED = 0x00000008
XBFONT_JUSTIFY = 0x00000010
VIEWPORT_WIDTH = 1920.0
VIEWPORT_HEIGHT = 1088.0
OVERLAY_WIDTH = int(VIEWPORT_WIDTH * 0.7)  # 70% size
OVERLAY_HEIGHT = 150
TORRENT2HTTP_TIMEOUT = 20
TORRENT2HTTP_POLL = 1000
PLAYING_EVENT_INTERVAL = 60

WINDOW_FULLSCREEN_VIDEO = 12005
VIEWPORT_WIDTH = 1920.0
RESOURCES_PATH = os.path.join(os.path.dirname(sys.modules["__main__"].__file__), 'resources')


class OverlayText(object):
    def __init__(self, w, h, background, *args, **kwargs):
        self.window = xbmcgui.Window(WINDOW_FULLSCREEN_VIDEO)
        viewport_w, viewport_h = self._get_skin_resolution()
        # Adjust size based on viewport, we are using 1080p coordinates
        w = int(w * viewport_w / VIEWPORT_WIDTH)
        h = int(h * viewport_h / VIEWPORT_HEIGHT)
        x = (viewport_w - w) / 2
        y = (viewport_h - h) / 2
        self._shown = False
        self._text = ""
        self._label = xbmcgui.ControlLabel(x, y, w, h, self._text, *args, **kwargs)
        self._background = xbmcgui.ControlImage(x, y, w, h, background)
        self._background.setColorDiffuse("0xD0000000")

    def show(self):
        if not self._shown:
            self.window.addControls([self._background, self._label])
            self._shown = True

    def hide(self):
        if self._shown:
            self._shown = False
            self.window.removeControls([self._background, self._label])

    def close(self):
        self.hide()

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text
        if self._shown:
            self._label.setLabel(self._text)

    # This is so hackish it hurts.
    @staticmethod
    def _get_skin_resolution():
        import xml.etree.ElementTree as e_t
        skin_path = xbmc.translatePath("special://skin/")
        tree = e_t.parse(os.path.join(skin_path, "addon.xml"))
        res = tree.findall("./extension/res")[0]
        return int(res.attrib["width"]), int(res.attrib["height"])


class TorrentOpener:

    def __init__(self, addon, base_url, addon_handle, user_agent, paths, logger):
        self.logger = logger
        self.icon = paths.icon
        self.addon = addon
        self.base_url = base_url
        self.addon_handle = addon_handle
        self.user_agent = user_agent
        self.default_download_path = paths.addon_data_path
        self.background = paths.background
        self.t2h_pre_buffer = int(self.addon.getSetting("t2h-pre-buffer-mb")) \
            if self.addon.getSetting("t2h-pre-buffer-mb") else 20
        self.t2h_max_connections = int(self.addon.getSetting("t2h-max-connections")) \
            if self.addon.getSetting("t2h-max-connections") else None
        self.t2h_download_rate = int(self.addon.getSetting("t2h-download-rate")) \
            if self.addon.getSetting("t2h-download-rate") else None
        self.t2h_upload_rate = int(self.addon.getSetting("t2h-upload-rate")) \
            if self.addon.getSetting("t2h-upload-rate") else None

    @staticmethod
    def _human_size(size):
        human, factor = None, None
        for h, f in (('Kb', 1024), ('Mb', 1024 * 1024), ('Gb', 1024 * 1024 * 1024), ('Tb', 1024 * 1024 * 1024 * 1024)):
            if size / f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return ('%.1f%s' % (size, 'b')).replace('.0', '')
        else:
            return '%.2f %s' % (float(size) / float(factor), human)

    @staticmethod
    def _human_rate(rate_kbps):
        human, factor = None, None
        for h, f in (('kB', 1), ('mB', 1024), ('gB', 1024 * 1024)):
            if rate_kbps >= f:
                human = h
                factor = f
            else:
                break
        if factor is None:
            return '0'
        else:
            return '%.2f %s/s' % (float(rate_kbps) / float(factor), human)

    def human_stats(self, download_rate, upload_rate, num_seeds, num_peers):
        return "(D:%s  U:%s  P:%d S:%d)" % (self._human_rate(download_rate),
                                            self._human_rate(upload_rate),
                                            num_peers, num_seeds)

    def get_torrent(self, target_url):
        try:
            req = urllib2.Request(url=target_url)
            req.add_header('User-Agent', self.user_agent)
            resp = urllib2.urlopen(req)
            return resp.read()
        except Exception, e:
            self.logger.log.info('HTTP ERROR ' + str(e))
            return None

    def get_item_name(self, url, ind):
        torrent_data = self.get_torrent(url)
        if torrent_data is not None:
            torrent = bdecode(torrent_data)
            try:
                torrent_filenames = torrent['info']['files']
                name = torrent_filenames[ind]['path'][-1]
            except Exception, err:
                self.logger.log.info("Could not obtain 'files' field: %s" % err)
                name = torrent['info']['name']
            return name
        else:
            return ' '

    def play_ace(self, torr_link, ind=0):
        title = self.get_item_name(torr_link, ind)
        from TSCore import TSengine as ts_engine
        ts_player = ts_engine()
        out = ts_player.load_torrent(torr_link, 'TORRENT')
        if out == 'Ok':
            ts_player.play_url_ind(ind, title, self.icon, self.icon, True)
        ts_player.end()
        return out

    def play_t2h(self, uri, file_id=0, download_folder=""):
        try:
            s = os.path.join(xbmc.translatePath("special://home/"), "addons", "script.module.torrent2http", "lib")
            import sys
            sys.path.append(s)
            from torrent2http import Error, State, Engine, MediaType
        except Exception, error:
            self.logger.log.info(error)
            return []
        try:
            progress_bar = xbmcgui.DialogProgress()
            from contextlib import closing
            if os.path.isdir(download_folder):
                download_folder = self.default_download_path
            progress_bar.create('torrent2http', 'Запуск')
            ready = False
            pre_buffer_bytes = self.t2h_pre_buffer * 1024 * 1024
            engine = Engine(uri, download_path=download_folder,
                            connections_limit=self.t2h_max_connections,
                            download_kbps=self.t2h_download_rate,
                            upload_kbps=self.t2h_download_rate,
                            )
            player = xbmc.Player()
            with closing(engine):
                # resume_file = hashlib.md5(uri).hexdigest() + ".resume"
                # engine.resume_file = os.path.join(engine.download_path, resume_file)
                engine.start(file_id)
                progress_bar.update(0, 'torrent2http', 'Загрузка торрента', "")
                while not xbmc.abortRequested and not ready:
                    xbmc.sleep(500)
                    status = engine.status()
                    engine.check_torrent_error(status)
                    file_status = engine.file_status(file_id)
                    if not file_status:
                        continue
                    if status.state == State.DOWNLOADING:
                        if file_status.download >= pre_buffer_bytes:
                            ready = True
                            break
                        progress_bar.update(100 * file_status.download / pre_buffer_bytes, 'torrent2http',
                                            xbmc.translatePath('Предварительная буферизация: ' +
                                                               str(file_status.download / 1024 / 1024) + " MB"),
                                            self.human_stats(status.download_rate, status.upload_rate,
                                                             status.num_seeds, status.num_peers))

                    elif status.state in [State.FINISHED, State.SEEDING]:
                        ready = True
                        break

                    if progress_bar.iscanceled():
                        progress_bar.update(0)
                        progress_bar.close()
                        break
                progress_bar.update(0)
                progress_bar.close()
                if ready:
                    item = xbmcgui.ListItem(path=file_status.url)
                    xbmcplugin.setResolvedUrl(self.addon_handle, True, item)
                    player.play(file_status.url)
                    xbmc.sleep(3000)
                    with closing(OverlayText(w=OVERLAY_WIDTH, h=OVERLAY_HEIGHT, background=self.background,
                                             alignment=XBFONT_CENTER_X | XBFONT_CENTER_Y)) as overlay:
                        while not xbmc.abortRequested and player.isPlaying():
                            status = engine.status()
                            file_status = engine.file_status(file_id)
                            overlay.text = str(100 * file_status.download / file_status.size) + "% downloaded: " + \
                                           self._human_size(file_status.download) + ' / ' + \
                                           self._human_size(file_status.size) + '\n' + \
                                           self.human_stats(status.download_rate, status.upload_rate,
                                                            status.num_seeds, status.num_peers)
                            if xbmc.getCondVisibility('Player.Paused'):
                                overlay.show()
                            else:
                                overlay.hide()
                            xbmc.sleep(TORRENT2HTTP_POLL)
        except Error as err:
            raise err
        if status and file_status and status.state in [State.FINISHED, State.SEEDING]:
            files = [file_status.save_path]
            return files
        return []

    def play(self, url, ind=0, cse='(0,0,0)'):
        engine = self.addon.getSetting("Engine")
        if engine == "0":
            self.play_ace(url, ind)
        elif engine == "1":
            self.play_t2h(url, ind, self.addon.getSetting("DownloadDirectory"))
        history = self.addon.getSetting("History")
        if history == '':
            history_list = []
        else:
            history_list = eval(history)
        if cse.replace(".00", "") not in history_list and cse != '(0,0,0)':
            history_list.append(cse.replace(".00", ""))
            self.addon.setSetting("History", repr(history_list))
        xbmc.executebuiltin("Container.Refresh")

    def build_url(self, query):
        return self.base_url + '?' + urllib.urlencode(query)
