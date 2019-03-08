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
init_file = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), 'init.dat')
header_file = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), 'header.dat')
sso_file = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), 'sso.dat')
mode_page = 1
mode_genre = 2
mode_show = 3
mode_episode = 4
mode_play = 5
mode_play_live = 6
recent_id = '42c22ec3-8501-46ca-8ab9-0450f1a37a1d'
mode_recent = 7

# cache key is the file {key}.dat
# cache entries are tuples in the form of (ttl, value)
def get_cache(key):
    file_path = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), '%s.dat' % key)
    c_val = None
    with open(file_path, 'rb') as f:
        c_val = pickle.load(f)
    if c_val and c_val[0] - time.time() > 0:
        return c_val[1]

def set_cache(key, val, ttl):
    file_path = os.path.join(xbmc.translatePath(this_addon.getAddonInfo('profile')), '%s.dat' % key)
    with open(file_path, 'wb') as f:
        pickle.dump((time.time() + ttl, val), f)

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
    liz.setInfo(type = "Video", infoLabels = info_labels)
    return xbmcplugin.addDirectoryItem(handle = this_plugin, url = url, listitem = liz, isFolder = is_folder)

def initialize():
    set_cache('init', {}, -1)
    set_cache('headers', [], -1)
    set_cache('sso', {}, -1)

@cached('init')
def get_init():
    init_url = build_url('/getInit')
    return get_json_response(init_url)

@cached('headers')
def get_headers():
    header_url = build_url('/getHeader')
    return get_json_response(header_url)

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

    for r in sub_recents:
        add_dir(r['recentTitle'], r['recentId'], mode_play_live if r['recentContentType'] == 'live' else mode_play)
    xbmcplugin.endOfDirectory(this_plugin)
    

def get_pages():
    headers = get_headers()
    add_dir('Latest', recent_id, mode_recent)
    for h in headers:
        add_dir(h['name'], h['id'], mode_genre)
    xbmcplugin.endOfDirectory(this_plugin)

def get_genres():
    headers = get_headers()
    header = list(filter(lambda x: x['id'] == id, headers))
    sub_menu_id = header[0]['subMenu'][0]['submenuId']
    genres = header[0]['subMenu'][0]['subGenre']
    for g in genres:
        itemId = json.dumps({'pageCode': id, 'submenuID': sub_menu_id, 'genreID': g['genreId']})
        add_dir(g['genreName'], itemId, mode_show)
    xbmcplugin.endOfDirectory(this_plugin)

def get_shows():
    itemId = json.loads(id)
    params = itemId.copy()
    params['sorting'] = 'desc'
    params['offset'] = page
    url = build_url('/getList', params = params)
    data = get_json_response(url)
    if data:
        for d in data:
            add_dir(d['textHead'], d['ID'], mode_episode, art = {'thumb': d['thumbnail'].encode('utf8')})
        add_dir('Next >>', id, mode_show, page = page + 1)
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

def get_show_player():
    url = build_url('/getShowPlayer', params = {'access_token': get_access_token(), 'episodeID': id})
    return get_json_response(url)


def play_episode():
    x_forwarded_for = this_addon.getSetting('xForwardedForIp')
    show_player = get_show_player()
    video_url = show_player['episodeVideo']
    video_url = '{video_url}|X-Forwarded-For={x_forwarded_for}&User-Agent={user_agent}'.format(video_url = video_url, x_forwarded_for = x_forwarded_for, user_agent = user_agent)
    liz = xbmcgui.ListItem(name)
    liz.setInfo(type="Video", infoLabels={"Title": name})
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
    x_forwarded_for_ip = xbmcaddon.Addon().getSetting('xForwardedForIp').strip()
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
    xbmcaddon.Addon().setSetting('xForwardedForIp', ip_address)


mode = mode_page
params = urlparse.parse_qs(sys.argv[2].replace('?',''))
name = try_get_param(params, 'name')
mode = int(try_get_param(params, 'mode', mode))
thumb = try_get_param(params, 'thumb', '')
page = int(try_get_param(params, 'page', 0))
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
elif mode == mode_play:
    play_episode()