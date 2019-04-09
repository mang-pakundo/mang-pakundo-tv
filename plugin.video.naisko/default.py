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

from functools import wraps
from random import randint

user_agent = 'okhttp/3.11.0'
base_url = 'https://bff-prod.iwant.ph/api/OneCms/cmsapi/OTT'
this_plugin = int(sys.argv[1])
this_addon = xbmcaddon.Addon()
cache_dir = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), 'cache')
mode_page = 1
mode_genre = 2
mode_show = 3
mode_episode = 4
mode_play = 5
mode_play_live = 6
recent_id = '42c22ec3-8501-46ca-8ab9-0450f1a37a1d'
mode_recent = 7

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
    with open(file_path, 'wb') as f:
        pickle.dump((time.time() + ttl, val), f)

def init_cache():
    old_files = ['init', 'header', 'sso', 'headers', 'genres.tv', 'genres.movies', 'genres.music']
    for o in old_files:
        fname = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), '%s.dat' % o)
        if os.path.exists(fname):
            os.remove(fname)
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

def build_url(path, base_url = base_url, params = {}):
    url = '{base_url}{path}'.format(base_url = base_url, path = path)
    if params:
        url = '{url}?{params}'.format(url = url, params = urllib.urlencode(params))
    return url
    
def http_request(url, params = {}, headers = {}):
    req = urllib2.Request(url)
    if not is_x_forwarded_for_ip_valid():
        auto_generate_ip()
    req.add_header('X-Forwarded-For', this_addon.getSetting('xForwardedForIp'))
    req.add_header('User-Agent', user_agent)
    for k, v in headers.iteritems():
        req.add_header(k, v)
    resp = None
    if params:
        resp = urllib2.urlopen(req, params)
    else:
        resp = urllib2.urlopen(req)
    return resp.read()
    
def get_json_response(url, params = {}):
    headers = {}
    json_resp = None
    if params:
        headers['Content-Type'] = 'application/json'
        json_params = json.dumps(params)
        json_resp = http_request(url, json_params, headers)
    else:
        json_resp = http_request(url)
    return json.loads(json_resp)

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
        url = '{url}&extra={extra}'.format(url = url, extra = json.dumps(kwargs['extra']))
    liz.setInfo(type = "Video", infoLabels = info_labels)
    return xbmcplugin.addDirectoryItem(handle = this_plugin, url = url, listitem = liz, isFolder = is_folder)

def show_dialog(message, title = ''):
    if not message:
        return
    dialog = xbmcgui.Dialog()
    dialog.ok(title, message)

def show_messages():
    try:
        # changelog message
        chlog_msg = get_json_response('https://raw.githubusercontent.com/mang-pakundo/mang-pakundo-tv-releases/master/resources/messages/{id}/changelog_message.json'.format(id=this_addon.getAddonInfo('id')))
        this_version = this_addon.getAddonInfo('version')
        chlog_msg_ver = this_addon.getSetting('chlog_msg_ver')
        if chlog_msg['version'] == this_version and chlog_msg_ver != this_version and chlog_msg['enabled']:
            show_dialog(chlog_msg['message'], this_addon.getLocalizedString(80701))
            this_addon.setSetting('chlog_msg_ver', chlog_msg['version'])
            # return early so we don't show 2 messages
            return

        # annoucement message
        msg = get_json_response('https://raw.githubusercontent.com/mang-pakundo/mang-pakundo-tv-releases/master/resources/messages/{id}/message.json'.format(id=this_addon.getAddonInfo('id')))
        last_msg_id = this_addon.getSetting('message_id')
        if last_msg_id != msg['id'] and msg['enabled']:
            show_dialog(msg['message'], this_addon.getLocalizedString(80701))
            this_addon.setSetting('message_id', msg['id'])
    except:
        xbmc.log(traceback.format_exc(), level=xbmc.LOGWARNING)

def initialize():
    init_cache()
    show_messages()

@cached('init')
def get_init():
    init_url = build_url('/getInit')
    return get_json_response(init_url)

@cached('headers')
def get_headers():
    header_url = build_url('/getHeader')
    return get_json_response(header_url)

def get_genres_by_type(pageCode, contentType):
    @cached('genres.%s.%s' % (pageCode, contentType))
    def get_genres_by_code(pageCode, contentType):
        header_url = build_url('/getGenres', params = {'pageCode': pageCode, 'contentType': contentType})
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
    add_dir('Latest', recent_id, mode_recent)
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
    genres = None
    # combine genres for tv and originals because some genres don't show up and it seems that both may share the same genres
    if sub_menu_name in ['tv', 'originals']:
        genres = [
            {'genreID': g['genreId'], 'genreName': g['genreName']} 
            for h in headers 
            for s in h['subMenu'] 
            for g in s['subGenre']
        ]
        genres.extend(get_genres_by_type(id, 'tv'))
        genres.extend(get_genres_by_type(id, 'movies'))
    else:
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
    url = build_url('/getList', params = params)
    data = get_json_response(url)
    if data:
        mode_lookup = {
            'movies': mode_play,
            'live': mode_play
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
    url = build_url('/getEpisodes', params = params)
    data = get_json_response(url)
    if data:
        for d in data:
            art = {'thumb': d['Thumbnail'].encode('utf8'), 'fanart': d['Large'].encode('utf8')}
            add_dir(d['title'], d['id'], mode_play, is_folder = False, art = art, list_properties = {'isPlayable': 'true'})
        add_dir('Next >>', id, mode_episode, page = page + 1)
    xbmcplugin.endOfDirectory(this_plugin)

def get_player(contentType):
    params = {'access_token': get_access_token()}
    path_lk = {
        'movies': '/getMoviePlayer',
        'live': '/getLivePlayer',
        'default': '/getShowPlayer'
    }
    param_key_lk = {
        'movies': 'movieID',
        'live': 'channelID',
        'default': 'episodeID'
    }
    path = path_lk[contentType] if contentType in path_lk else path_lk['default']
    param_key = param_key_lk[contentType] if contentType in param_key_lk else param_key_lk['default']
    params[param_key] = id
    url = build_url(path, params = params)
    return get_json_response(url)


def play_episode():
    content_type = extra['contentType'] if 'contentType' in extra else None
    x_forwarded_for = this_addon.getSetting('xForwardedForIp')
    show_player = get_player(content_type)
    video_key_name_lk = {
        'movies': 'stbVideo',
        'live': 'liveVideo',
        'default': 'episodeVideo'
    }
    video_key = video_key_name_lk[content_type] if content_type in video_key_name_lk else video_key_name_lk['default']
    default_url = show_player[video_key]
    video_url = default_url or show_player['hls'] or show_player['mpegDash'] or show_player['stbVideo'] or show_player['smoothStreaming'] or show_player['videoHDS']
    video_url = '{video_url}|X-Forwarded-For={x_forwarded_for}&User-Agent={user_agent}'.format(video_url = video_url, x_forwarded_for = x_forwarded_for, user_agent = 'Akamai AMP SDK Android (6.109; 6.0.1; hammerhead; armeabi-v7a)')
    liz = xbmcgui.ListItem(name)
    plot = show_player['episodeDesc'] if 'episodeDesc' in show_player else ''
    liz.setInfo(type="Video", infoLabels={"Title": name, 'plot': plot})
    thumb = show_player['episodeImageThumbnail'] if 'episodeImageThumbnail' in show_player else None
    liz.setArt({'thumb': thumb})
    liz.setPath(video_url)
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
        url = 'https://bff-prod.iwant.ph/api/sso/sso.login'
        access_data = get_json_response(url, params = params)
        if access_data['statusCode'] != 203200:
            dialog = xbmcgui.Dialog()
            dialog.ok('Login Failed', access_data['message'])
            return None
        return access_data
    except:
        xbmc.log(traceback.format_exc())

def get_access_token():
    access_data = do_sso_login()
    return access_data['data']['accessToken']['id']

def try_get_param(params, name, default_value = None):
    return params[name][0] if name in params else default_value

def is_x_forwarded_for_ip_valid():
    x_forwarded_for_ip = this_addon.getSetting('xForwardedForIp').strip()
    if x_forwarded_for_ip == '0.0.0.0' or x_forwarded_for_ip == '':
        return False
    return True

def auto_generate_ip():
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
    this_addon.setSetting('xForwardedForIp', ip_address)


mode = mode_page
params = urlparse.parse_qs(sys.argv[2].replace('?',''))
name = try_get_param(params, 'name')
mode = int(try_get_param(params, 'mode', mode))
thumb = try_get_param(params, 'thumb', '')
page = int(try_get_param(params, 'page', 0))
extra = json.loads(try_get_param(params, 'extra', '{}'))
id = try_get_param(params, 'id')

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