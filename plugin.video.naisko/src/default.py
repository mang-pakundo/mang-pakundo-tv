import sys
import json
import urllib
import urllib2
import urlparse
import pickle
import os
import time
import traceback
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import uuid
import datetime
import base64
import hashlib
import errno
import io
import zlib

from functools import wraps
from random import randint
import xml.etree.ElementTree as ET
from lib.data import DATA1

this_plugin = int(sys.argv[1])
this_addon = xbmcaddon.Addon()
cache_dir = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), 'cache')
mode_page = 1
mode_genre = 2
mode_show = 3
mode_episode = 4
mode_play = 5
mode_play_live = 6
mode_recent = 7
mode_music = 8
mode_play_music = 9

CONFIG = {}

def is_setting_true(setting_id):
    return this_addon.getSetting(setting_id).lower() == 'true'

def get_enable_beta():
    return is_setting_true('enableBeta')

def get_send_support_id():
    return is_setting_true('sendSupportId')

def get_auto_fix_ip():
    return is_setting_true('autoFixIp')

def get_support_id():
    try:
        uuid.UUID(this_addon.getSetting('supportId'))
    except ValueError:
        this_addon.setSetting('supportId', str(uuid.uuid4()))
    return this_addon.getSetting('supportId')

def send_to_sentry(data):
    headers = {
        "X-Sentry-Auth": "Sentry sentry_version=5, sentry_client=goldfish/0.0.1, sentry_timestamp=%s, sentry_key=%s, sentry_secret=%s" % (int(time.time()), CONFIG['s_key'], CONFIG['s_sec'])
    }
    try:
        get_json_response(CONFIG['s_url'], data, headers, False)
    except:
        ex_tb = traceback.format_exc()
        xbmc.log(ex_tb, level=xbmc.LOGERROR)


def get_sentry_data(level, tags={}, sentry_extra={}):
    tags['kodi_os_version_info'] = xbmc.getInfoLabel('System.OSVersionInfo')
    kodi_friendly_name = xbmc.getInfoLabel('System.FriendlyName')
    tags['kodi_friendly_name'] = kodi_friendly_name
    tags['kodi_friendly_name_encoded'] = base64.b64encode(kodi_friendly_name)
    tags['kodi_build_version'] = xbmc.getInfoLabel('System.BuildVersion')
    tags['kodi_build_date'] = xbmc.getInfoLabel('System.BuildDate')
    tags['kodi_video_encoder_info'] = xbmc.getInfoLabel('System.VideoEncoderInfo')
    tags['user_id'] = hashlib.sha1(this_addon.getSetting('emailAddress')).hexdigest()
    if get_send_support_id():
        tags['support_id'] = get_support_id()

    sentry_extra['inputstream_adaptive_version'] = xbmc.getInfoLabel('System.AddonVersion(inputstream.adaptive)')
    sentry_extra['inputstream_adaptive_enabled'] = xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)')
    sentry_extra['mang_pakundo_repo_version'] = xbmc.getInfoLabel('System.AddonVersion(repository.mang.pakundo.addons)')
    sentry_extra['mang_pakundo_repo_enabled'] = xbmc.getCondVisibility('System.HasAddon(repository.mang.pakundo.addons)')
    sentry_extra['enable_beta'] = get_enable_beta()
    sentry_extra['xff'] = get_xff_ip()
    addon_extra = {}
    if extra:
        addon_extra['extra'] = extra
    if params:
        addon_extra['params'] = params
    if addon_extra:
        sentry_extra['addon_extra'] = addon_extra

    return {
        "event_id": str(uuid.uuid4()),
        "level": level,
        "logger": __name__,
        "platform": "python",
        "release": this_addon.getAddonInfo('version'),
        "transaction": str(mode),
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": {
            "ip_address": "{{auto}}"
        },
        "tags": tags,
        "extra": sentry_extra
    }

def get_sentry_data_exception(exceptions, level="error", tags={}, sentry_extra={}):
    sentry_data = get_sentry_data(level, tags, sentry_extra)
    sentry_data['exception'] = {
        "values": [e for e in exceptions]
    }
    return sentry_data

def get_sentry_data_message(message, level="info", tags={}, sentry_extra={}):
    sentry_data = get_sentry_data(level, tags, sentry_extra)
    sentry_data['message'] = message
    return sentry_data

def send_message_to_sentry(message, tags={}, sentry_extra={}):
    data = get_sentry_data_message(message, tags=tags, sentry_extra=sentry_extra)
    send_to_sentry(data)


def send_exception_to_sentry(ex, tags={}, sentry_extra={}):
    ex_type = type(ex).__name__
    ex_tb = traceback.format_exc()
    sentry_data = get_sentry_data_exception([{'type': ex_type, 'value': ex_tb}], tags=tags, sentry_extra=sentry_extra)
    send_to_sentry(sentry_data)

# cache entries are tuples in the form of (ttl, value)
def get_cache(key):
    file_path = os.path.join(cache_dir, '%s.cache' % key)
    c_val = None
    try:
        with open(file_path, 'rb') as f:
            c_val = pickle.load(f)
    except:
        return None
    if c_val and c_val[0] - time.time() > 0:
        return c_val[1]

def set_cache(key, val, ttl):
    file_path = os.path.join(cache_dir, '%s.cache' % key)
    try:
        with open(file_path, 'wb') as f:
            pickle.dump((time.time() + ttl, val), f)
    except IOError as e:
        if e.errno == errno.ENOENT:
            init_cache()
            with open(file_path, 'wb') as f:
                pickle.dump((time.time() + ttl, val), f)

def init_cache():
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

def cached(key, ttl = 10000):
    def cached_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = get_cache(key)
            if result:
                return result
            else:
                result = f(*args, **kwargs)
                if result:
                    set_cache(key, result, ttl)
                return result
        return wrapper
    return cached_decorator

def build_api_url(path, params={}):
    url = '{base_url}/api/OneCms/cmsapi/OTT{path}'.format(base_url=CONFIG['base_url'], path=path)
    if params:
        url = '{url}?{params}'.format(url=url, params=urllib.urlencode(params))
    return url
    
def http_request(url, params = {}, headers = {}, send_default_headers=True):
    req = urllib2.Request(url)
    if send_default_headers:
        req.add_header('X-Forwarded-For', get_xff_ip())
        req.add_header('User-Agent', CONFIG['app_ua'])
    for k, v in headers.iteritems():
        req.add_header(k, v)
    resp = None
    if params:
        resp = urllib2.urlopen(req, params)
    else:
        resp = urllib2.urlopen(req)
    return resp.read()

def try_get_json(json_str):
    json_res = json_str
    success = False
    try:
        json_res = json.loads(json_str)
        success = True
    except:
        pass
    return json_res, success
    
def get_json_response(url, params = {}, headers = {}, send_default_headers=True):
    json_resp = None
    if params:
        headers['Content-Type'] = 'application/json'
        json_params = json.dumps(params)
        json_resp = http_request(url, json_params, headers, send_default_headers)
    else:
        json_resp = http_request(url, headers=headers, send_default_headers=send_default_headers)
    return json.loads(json_resp)

# the api has a mix of old and new auth and endpoints. we need separate code paths for them
# TODO clean this up once we get things straightened up
def get_json_api_response(url, params = {}, headers = {}, send_default_headers=True, send_auth=True):
    if send_auth:
        headers['Authorization'] = 'Bearer {}'.format(get_auth_token())
    return get_json_response(url, params, headers, send_default_headers)

@cached('config')
def get_config_file():
    try:
        config_raw = http_request('https://bit.ly/2Aa1QtO', headers={'User-Agent': CONFIG['browser_ua']}, send_default_headers=False)
        config_file = zlib.decompress(config_raw, 32 + zlib.MAX_WBITS)
        return json.loads(config_file)
    except urllib2.HTTPError as ex:
        xbmc.log(traceback.format_exc(), level=xbmc.LOGERROR)
        response_body, success = try_get_json(ex.read())
        response_body = response_body if success else {'response_body': response_body}
        send_exception_to_sentry(ex, sentry_extra=response_body)
    except Exception as ex:
        xbmc.log(traceback.format_exc(), level=xbmc.LOGERROR)
        send_exception_to_sentry(ex)

def init_config():
    global CONFIG
    CONFIG = json.loads(base64.b64decode(DATA1))
    config_file = get_config_file()
    if config_file:
        for k, v in config_file.items():
            CONFIG[k] = v


def add_dir(name, id, mode, is_folder = True, **kwargs):
    query_string = {'id': id, 'mode': mode, 'name': name.encode('utf8')}
    url = '{addon_name}?{query_string}'.format(addon_name = sys.argv[0], query_string = urllib.urlencode(query_string))
    liz = xbmcgui.ListItem(name)
    info_labels = {"Title": name}
    if 'info_labels' in kwargs:
        inf_lbl = kwargs['info_labels']
        info_labels = dict(info_labels.items() + inf_lbl.items())
    if 'list_properties' in kwargs:
        list_properties = kwargs['list_properties']
        for list_property_key, list_property_value in list_properties.iteritems():
            liz.setProperty(list_property_key, list_property_value)
    if 'art' in kwargs:
        art = kwargs['art']
        liz.setArt(art)
        url = '{url}&{art_params}'.format(url = url, art_params = urllib.urlencode(art))
    if 'page' in kwargs:
        url = '{url}&page={page}'.format(url = url, page = kwargs['page'])
    if 'extra' in kwargs:
        extra =  base64.urlsafe_b64encode(json.dumps(kwargs['extra']))
        url = '{url}&extra={extra}'.format(url = url, extra = extra)
    liz.setInfo(type = "Video", infoLabels = info_labels)
    return xbmcplugin.addDirectoryItem(handle = this_plugin, url = url, listitem = liz, isFolder = is_folder)

def show_dialog(message, title = ''):
    if not message:
        return
    dialog = xbmcgui.Dialog()
    dialog.ok(title, message)

def show_notification(notification_type, message, display_ms):
    name = this_addon.getAddonInfo('name')
    icon = this_addon.getAddonInfo('icon')
    xbmc.executebuiltin('Notification({name} {notification_type}, {message}, {display_ms}, {icon})'.format(name=name, notification_type=notification_type, message=message, display_ms=display_ms, icon=icon))

def show_messages():
    try:
        # changelog message
        chlog_msg = get_json_response(CONFIG['chlog_url'], headers={'User-Agent': CONFIG['browser_ua']}, send_default_headers=False)
        this_version = this_addon.getAddonInfo('version')
        chlog_msg_ver = this_addon.getSetting('chlog_msg_ver')
        if chlog_msg['version'] == this_version and chlog_msg_ver != this_version and chlog_msg['enabled']:
            show_dialog(chlog_msg['message'], this_addon.getLocalizedString(80701))
            this_addon.setSetting('chlog_msg_ver', chlog_msg['version'])
            # return early so we don't show 2 messages
            return

        # annoucement message
        msg = get_json_response(CONFIG['ver_url'], headers={'User-Agent': CONFIG['browser_ua']}, send_default_headers=False)
        last_msg_id = this_addon.getSetting('message_id')
        if last_msg_id != msg['id'] and msg['enabled']:
            show_dialog(msg['message'], this_addon.getLocalizedString(80701))
            this_addon.setSetting('message_id', msg['id'])
    except:
        xbmc.log(traceback.format_exc(), level=xbmc.LOGWARNING)
        raise

def initialize():
    send_message_to_sentry('Initialized')
    init_cache()
    show_messages()

@cached('init')
def get_init():
    init_url = build_api_url('/getInit')
    return get_json_response(init_url)

@cached('headers')
def get_headers():
    header_url = build_api_url('/getHeader')
    return get_json_response(header_url)

def get_genres_by_type(pageCode, contentType):
    @cached('genres.%s.%s' % (pageCode, contentType))
    def get_genres_by_code(pageCode, contentType):
        header_url = build_api_url('/getGenres', params = {'pageCode': pageCode, 'contentType': contentType})
        return get_json_response(header_url)
    return get_genres_by_code(pageCode, contentType)

def get_recents():
    headers = get_headers()
    sub_recents = [s for h in headers if 'subMenu' in h 
        for m in h['subMenu'] if 'subRecent' in m 
        for s in m['subRecent']]
    sub_genres = [s for h in headers if 'subMenu' in h
        for m in h['subMenu'] if 'subGenre' in m
        for g in m['subGenre'] if 'genreRecent' in g
        for s in g['genreRecent']]
    sub_recents.extend(sub_genres)

    recents = {v['recentId']: v for v in sub_recents}.values()
    recents = sorted(recents, key = lambda k: k['recentTitle'])
    for r in recents:
        add_dir(r['recentTitle'], r['recentId'], mode_play_live if r['recentContentType'] == 'live' else mode_play, is_folder = False, list_properties = {'isPlayable': 'true'})
    xbmcplugin.endOfDirectory(this_plugin)

def get_pages():
    headers = get_headers()
    # add_dir('Latest', CONFIG['recent_id'], mode_recent)
    for h in headers:
        add_dir(h['name'].title(), h['id'], mode_genre)
    xbmcplugin.endOfDirectory(this_plugin)

def get_genres():
    headers = get_headers()
    # get the chunk from the headers list that matches this pageCode/id,
    # e.g. if we are in the 'Tv' page, get the relevant subMenu, etc. for this page
    header = list(filter(lambda x: x['id'] == id, headers))
    sub_menu_id = header[0]['subMenu'][0]['submenuId']
    # sub_menu_id = header[0]['subMenu'][0]['submenuId']
    sub_menu_name = header[0]['name'].lower()
    genres = header[0]['subMenu'][0]['subGenre']
    moreGenres = get_genres_by_type(id, sub_menu_name)
    if moreGenres and moreGenres != 'null':
        genres.extend(moreGenres)
    # make the list unique by genreId
    genres = {g['genreId'] if 'genreId' in g else g['genreID']: g for g in genres}.values()
    genres = sorted(genres, key = lambda g: g['genreName'])
    for g in genres:
        # set the page that we're at (tv, originals, movies, etc.) so we can tell if we're in movies because movies don't have episodes
        extra = {'pageCode': id, 'submenuID': sub_menu_id}
        genreId = g['genreId'] if 'genreId' in g else g['genreID']
        add_dir(g['genreName'], genreId, mode_show, extra = extra)
    xbmcplugin.endOfDirectory(this_plugin)

def get_shows():
    params = extra.copy()
    params['genreID'] = id
    params['sorting'] = 'desc'
    params['offset'] = page
    url = build_api_url('/getList', params = params)
    data = get_json_response(url)
    if data and data != 'null':
        mode_lookup = {
            'movies': mode_play,
            'live': mode_play,
            'music': mode_music
        }
        is_folder_lookup = {
            'movies': False,
            'live': False
        }
        liz_prop_lk = {
            'movies': {'isPlayable': 'true'},
            'live': {'isPlayable': 'true'}
        }
        for d in data:
            content_type = d['contentType']
            dir_mode = mode_lookup[content_type] if content_type in mode_lookup else mode_episode
            is_folder = is_folder_lookup[content_type] if content_type in is_folder_lookup else True
            list_properties = liz_prop_lk[content_type] if content_type in liz_prop_lk else {}
            fanart = d['thumbnail'].encode('utf8')
            add_dir(d['textHead'], d['ID'], dir_mode, is_folder = is_folder, art = {'thumb': fanart, 'fanart': fanart}, extra = {'contentType': d['contentType']}, list_properties = list_properties)
        add_dir('Next >>', id, mode_show, page = page + 1, extra = extra)
    xbmcplugin.endOfDirectory(this_plugin)

def get_episodes():
    params = {'showID': id, 'offset': page, 'sorting': 'desc'}
    url = build_api_url('/getEpisodes', params = params)
    data = get_json_response(url)
    if data:
        for d in data:
            fanart = d['Large'] and d['Large'].encode('utf8')
            thumb_art = d['Thumbnail'] and d['Thumbnail'].encode('utf8')
            art = {'thumb': thumb_art, 'fanart': fanart}
            add_dir(d['title'], d['id'], mode_play, is_folder = False, art = art, list_properties = {'isPlayable': 'true'})
        add_dir('Next >>', id, mode_episode, page = page + 1)
    xbmcplugin.endOfDirectory(this_plugin)

def get_album_info():
    params = {'albumID': id, 'access_token': get_access_token()}
    url = build_api_url('/getAlbumInfo', params = params)
    data = get_json_response(url)
    if data:
        thumb = data['albumImageThumbnail'].encode('utf8')
        fanart = data['albumImageLarge'].encode('utf8')
        for d in data['albumSongs']:
            art = {'thumb': thumb, 'fanart': fanart}
            extra = {'url': d['songAsset'], 'thumb': thumb, 'fanart': fanart}
            add_dir(d['songName'], d['songID'], mode_play_music, is_folder = False, art = art, list_properties = {'isPlayable': 'true'}, extra=extra)
    xbmcplugin.endOfDirectory(this_plugin)


def get_url_headers():
    return 'X-Forwarded-For={x_forwarded_for}&User-Agent={user_agent}'.format(x_forwarded_for = get_xff_ip(), user_agent = CONFIG['player_user_agent'])


def play_music():
    url = '%s|%s' % (extra['url'], get_url_headers())
    liz = xbmcgui.ListItem(name)
    liz.setInfo(type="music", infoLabels={"Title": name})
    liz.setArt({'thumb': extra['thumb'], 'fanart': extra['fanart']})
    liz.setPath(url)
    return xbmcplugin.setResolvedUrl(this_plugin, True, liz)

def get_player(contentType):
    path_lk = {
        'movies': '/getMoviePlayer',
        'live': '/getLivePlayer',
        'default': 'tv'
    }
    param_key_lk = {
        'movies': 'movieID',
        'live': 'channelID',
        'default': 'episodeID'
    }
    path = path_lk[contentType] if contentType in path_lk else path_lk['default']
    param_key = param_key_lk[contentType] if contentType in param_key_lk else param_key_lk['default']

    player = {}
    if path == 'tv':
        url = '{base_url}/content/v1/player/{path}?siteCode=OTT&episodeID={id}&ipAddress={ip}&countryCode=PH'.format(base_url='https://api.iwant.ph', path=path, ip=http_request(CONFIG['wai_url'], send_default_headers=False), id=id)
        headers = {
            'ocp-apim-subscription-key': CONFIG['p_apim_k'],
            'User-Agent': CONFIG['app_ua']
            }
        res =  get_json_api_response(url, headers=headers, send_default_headers=False)
        player = res['data']
    else:
        params = {'access_token': get_access_token(), param_key: id}
        url = build_api_url(path, params=params)
        player = get_json_response(url)
    return player


def get_video_url_and_key(play_info, content_type):
    default_video_keys = ['stbVideo', 'stbVideo', 'mpegDash', 'hls', 'videoHDS', 'movieVideo', 'smoothStreaming', 'episodeVideo', 'liveVideo']
    video_keys = {
        'movies': ['stbVideo', 'mpegDash'],
        'live': ['liveVideo']
    }
    key_lookup_order = video_keys[content_type] if content_type in video_keys else default_video_keys

    # lookup video url based on the order specified in key_lookup_order + default_video_keys
    # and determine the video key that found the video
    key_used = None
    video_url = None
    for k in key_lookup_order:
        if k not in play_info:
            continue
        video_url = play_info[k]
        if video_url:
            key_used = k
            break
    if not video_url:
        for k in default_video_keys:
            if k not in play_info:
                continue
            video_url = play_info[k]
            if video_url:
                key_used = k
                break

    return {'key': key_used, 'url': video_url}


def create_listitem(name, item_type, path, **kwargs):
    liz = xbmcgui.ListItem(name)
    liz.setPath(path)
    
    info_labels = {'Title': name}
    if 'info_labels' in kwargs:
        info_labels = info_labels.update(kwargs['info_labels'])
    liz.setInfo(type=item_type, infoLabels=info_labels)

    if 'art' in kwargs:
        liz.setArt(kwargs['art'])

    if 'properties' in kwargs:
        for k, v in kwargs['properties'].iteritems():
            liz.setProperty(k, v)

    if 'content_lookup' in kwargs:
        liz.setContentLookup(kwargs['content_lookup'])

    return liz
    

def get_license_url(show_player, video_url):
    lic_url = show_player['widevine'] if 'widevine' in show_player and 'kid' in show_player['widevine'].lower() else ''
    if not lic_url:
        headers = {'User-Agent': CONFIG['player_user_agent']}
        res = http_request(video_url, headers=headers, send_default_headers=True)
        root = ET.fromstring(res)
        elem = root.find('.//ms:laurl', {'ms': 'urn:microsoft'})
        lic_url = elem.attrib['licenseUrl']
    return lic_url

def autofix_forbidden(video_url):
    try:
        if not get_auto_fix_ip() or randint(1, 100) >= CONFIG['ip_fix_pct']:
            return
        headers = {'User-Agent': CONFIG['player_user_agent']}
        res = http_request(video_url, headers=headers, send_default_headers=True)
    except urllib2.HTTPError as ex:
        send_exception_to_sentry(ex)
        if ex.code == 403:
            auto_generate_ip()



def play_episode():
    content_type = extra['contentType'] if 'contentType' in extra else None
    show_player = get_player(content_type)
    video_info = get_video_url_and_key(show_player, content_type)
    video_url = video_info['url']
    video_key = video_info['key']

    autofix_forbidden(video_url)

    info_labels = {
        'plot': show_player['episodeDesc'] if 'episodeDesc' in show_player else ''
        }
    art = {
        'thumb': show_player['episodeImageThumbnail'] if 'episodeImageThumbnail' in show_player else None
    }

    if (video_key in ['mpegDash', 'liveVideo'] and not xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)')):
        show_dialog('Please install and/or enable the InputStream Adaptive addon.', 'Missing Addon')
        return

    liz_properties = {}
    if video_key == 'mpegDash':
        liz_properties['inputstreamaddon'] = 'inputstream.adaptive'
        liz_properties['inputstream.adaptive.manifest_type'] = 'mpd'
        lic_url = get_license_url(show_player, video_url)
        lic_headers = get_url_headers() + '&content-type=application/octet-stream'
        license_tpl = '%s|%s|%s|%s' % (lic_url, lic_headers , 'R{SSM}', '')
        liz_properties['inputstream.adaptive.license_key'] = license_tpl
        liz_properties['inputstream.adaptive.license_type'] = 'com.widevine.alpha'
        liz_properties['inputstream.adaptive.stream_headers'] = get_url_headers()

    if video_key == 'liveVideo':
        liz_properties['inputstreamaddon'] = 'inputstream.adaptive'
        liz_properties['inputstream.adaptive.manifest_type'] = 'hls'
        liz_properties['inputstream.adaptive.license_key'] = '|%s|||' % get_url_headers()
        liz_properties['inputstream.adaptive.stream_headers'] = get_url_headers()

    liz_video_url = '%s|%s' % (video_url, get_url_headers())
    liz = create_listitem(name, 'Video', liz_video_url, info_labels=info_labels, properties=liz_properties, art=art)
    if mode == mode_play_live:
        xbmc.Player().play(item = video_url, listitem = liz)
    else:
        return xbmcplugin.setResolvedUrl(this_plugin, True, liz)

@cached('sso')
def do_sso_login():
    try:
        params = {
            "isMobile": True,
            "loginID": this_addon.getSetting('emailAddress'),
            "password": this_addon.getSetting('password'),
            "sendVerificationEmail": True,
            "url": "https://www.iwant.ph/account-link?mobile_app=true"
        }
        url = '{base_url}/api/sso/sso.login'.format(base_url=CONFIG['base_url'])
        access_data = get_json_response(url, params = params)
        if access_data['statusCode'] != 203200:
            invalid_login_ex = urllib2.HTTPError(url, 401, access_data['message'], {}, io.BytesIO(json.dumps(access_data)))
            raise invalid_login_ex
        return access_data
    except urllib2.HTTPError as ex:
        show_dialog('The username and password combination is incorrect or there was a failure to authenticate the user.', 'Login Error')
        raise

@cached('login')
def do_login():
    try:
        params = {
            "loginID": this_addon.getSetting('emailAddress'),
            "password": this_addon.getSetting('password'),
            "keepMeLogin": True,
            "sendVerificationEmail": True,
            "siteURL": "https://www.iwant.ph"
        }
        url = '{base_url}/userprofile/v1/login/name-email'.format(base_url=CONFIG['api_base_url'])
        headers = {'ocp-apim-subscription-key': CONFIG['l_apim_k']}
        res = get_json_response(url, headers=headers, params=params)
        if res['statusCode'] != 200:
            invalid_login_ex = urllib2.HTTPError(url, 401, res['error']['message'], {}, io.BytesIO(json.dumps(res)))
            raise invalid_login_ex
        return res
    except urllib2.HTTPError as ex:
        show_dialog('The username and password combination is incorrect or there was a failure to authenticate the user.', 'Login Error')
        raise

def get_access_token():
    access_data = do_sso_login()
    return access_data['data']['accessToken']['id']

def get_auth_token():
    res = do_login()
    return res['data']['token']

def try_get_param(params, name, default_value = None):
    return params[name][0] if name in params else default_value

def is_x_forwarded_for_ip_valid():
    x_forwarded_for_ip = this_addon.getSetting('xForwardedForIp').strip()
    if x_forwarded_for_ip == '0.0.0.0' or x_forwarded_for_ip == '':
        return False
    return True

def rand_ip_address():
    ip_range_list = [
        (1848401920, 1848406015),
        (1884172288, 1884176383),
        (1931427840, 1931431935),
        (2000617472, 2000621567),
        (2070704128, 2070708223),
    ]

    start_ip_number, end_ip_number = ip_range_list[randint(0, len(ip_range_list) - 1)]
    ip_number = randint(start_ip_number, end_ip_number)
    w = (ip_number / 16777216) % 256
    x = (ip_number / 65536) % 256
    y = (ip_number / 256) % 256
    z = (ip_number) % 256
    if z == 0: z = 1
    if z == 255: z = 254
    ip_address = '%s.%s.%s.%s' % (w, x, y, z)
    return ip_address

def auto_generate_ip():
    discarded_ips = []
    for i in range(0, 10):
        try:
            ip_to_test = rand_ip_address()
            headers = {
                'User-Agent': CONFIG['app_ua'],
                'X-Forwarded-For': ip_to_test,
                'ocp-apim-subscription-key': CONFIG['apim_k'],
                'authority': 'api.iwant.ph',
                'origin': 'https://www.iwant.ph'
            }
            resp = get_json_response('https://api.iwant.ph/location/v1/location/allowed', headers=headers, send_default_headers=False)
            if resp['data']['isAllowed']:
                this_addon.setSetting('xForwardedForIp', ip_to_test)
                break
            else:
                discarded_ips.append(ip_to_test)
        except Exception as ex:
            discarded_ips.append(ip_to_test)
            send_exception_to_sentry(ex, sentry_extra={'tested_ip': ip_to_test})
    send_message_to_sentry('AutoGenerateIp', sentry_extra={'discarded_ips': discarded_ips})


def get_xff_ip():
    if not is_x_forwarded_for_ip_valid():
        auto_generate_ip()
    return this_addon.getSetting('xForwardedForIp')


def main(mode, id):
    try:
        init_config()
        if mode == mode_page or not id or len(id) == 0:
            initialize()
            get_pages()
        elif mode == mode_recent:
            get_recents()
        elif mode == mode_genre:
            get_genres()
        elif mode == mode_show:
            get_shows()
        elif mode == mode_episode:
            get_episodes()
        elif mode == mode_play or mode == mode_play_live:
            play_episode()
        elif mode == mode_music:
            get_album_info()
        elif mode == mode_play_music:
            play_music()
    except Exception as ex:
        xbmc.log(traceback.format_exc(), level=xbmc.LOGERROR)
        if isinstance(ex, urllib2.HTTPError):
            response_body, success = try_get_json(ex.read())
            response_body = response_body if success else {'response_body': response_body}
            send_exception_to_sentry(ex, sentry_extra=response_body)
            show_notification('Error', 'Network error. Please try again.', 500)
            return
        elif isinstance(ex, urllib2.URLError):
            show_notification('Error', 'Network error. Please try again.', 500)
        else:
            show_notification('Error', 'Check the logs for details.', 500)
        send_exception_to_sentry(ex)
        

mode = mode_page
params = urlparse.parse_qs(sys.argv[2].replace('?',''))
name = try_get_param(params, 'name')
mode = int(try_get_param(params, 'mode', mode))
thumb = try_get_param(params, 'thumb', '')
page = int(try_get_param(params, 'page', 0))
raw_extra = try_get_param(params, 'extra', '')
extra = {}
if raw_extra:
    extra = json.loads(base64.urlsafe_b64decode(raw_extra))
id = try_get_param(params, 'id')

main(mode, id)