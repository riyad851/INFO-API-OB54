import asyncio
import time
import httpx
import json
import base64
import random
from collections import defaultdict
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from cachetools import TTLCache
from typing import Tuple
from proto import FreeFire_pb2, main_pb2, AccountPersonalShow_pb2, GetWishListItems_pb2
from google.protobuf import json_format, message
from google.protobuf.message import Message
from Crypto.Cipher import AES
from datetime import datetime, timezone, timedelta

# === Settings ===

API_KEY = "RAH"

# ✅ AES Keys (both formats — same values)
AES_KEY  = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV   = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')
MAIN_IV  = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')

RELEASE_VERSION = "OB55"
USERAGENT       = "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"

# ✅✅✅ FIXED: Garena OFFICIAL URLs
LOGIN_URL      = "https://loginbp.ppmainecoonghj.com"
CLIENT_URL_BD  = "https://clientbp.ppmainecoonghj.com"
CLIENT_URL_IND = "https://client.ind.freefiremobile.com"
CLIENT_URL_BR  = "https://client.us.freefiremobile.com"

OAUTH_URL      = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"

SUPPORTED_REGIONS = {"IND", "BR", "US", "SAC", "NA", "SG", "RU", "ID", "TW", "VN", "TH", "ME", "PK", "CIS", "BD", "EUROPE"}

# === Flask App Setup ===

app = Flask(__name__)
CORS(app)
cache = TTLCache(maxsize=100, ttl=300)
cached_tokens = defaultdict(dict)
uid_region_cache = {}

# === Helper Functions ===

def pad(text: bytes) -> bytes:
    padding_length = AES.block_size - (len(text) % AES.block_size)
    return text + bytes([padding_length] * padding_length)

def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    aes = AES.new(key, AES.MODE_CBC, iv)
    return aes.encrypt(pad(plaintext))

def decode_protobuf(encoded_data: bytes, message_type: message.Message) -> message.Message:
    instance = message_type()
    instance.ParseFromString(encoded_data)
    return instance

async def json_to_proto(json_data: str, proto_message: Message) -> bytes:
    json_format.ParseDict(json.loads(json_data), proto_message)
    return proto_message.SerializeToString()

# === Region Credentials ===

def get_account_credentials(region: str) -> str:
    r = region.upper()
    if r == "IND":
        return "uid=4146441772&password=208355A6928ED22EC89AA18A9593B484FA2B7B061E28E718E89ABE0FF8DBD3E6"
    elif r == "ME":
        return "uid=4626846042&password=B9EA9EC09AA6710E46CDB428BEA89EA0157F0B07FE788A207A26D2654866C8BB"
    elif r in {"BR", "US", "SAC", "NA"}:
        return "uid=4626846042&password=B9EA9EC09AA6710E46CDB428BEA89EA0157F0B07FE788A207A26D2654866C8BB"
    else:
        return "uid=4626846042&password=B9EA9EC09AA6710E46CDB428BEA89EA0157F0B07FE788A207A26D2654866C8BB"

# === Token Generation ===

async def get_access_token(account: str):
    url = OAUTH_URL
    payload = account + "&response_type=token&client_type=2&client_secret=2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3&client_id=100067"
    headers = {
        'User-Agent': USERAGENT,
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/x-www-form-urlencoded"
    }
    try:
        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            resp = await client.post(url, data=payload, headers=headers)
            data = resp.json()
            return data.get("access_token", "0"), data.get("open_id", "0")
    except Exception as e:
        print(f"[ERROR] OAuth failed: {e}")
        return "0", "0"

async def create_jwt(region: str):
    """
    ✅ FIXED: Uses working logic from triple.py
    """
    try:
        account = get_account_credentials(region)
        token_val, open_id = await get_access_token(account)
        
        if token_val == "0" or open_id == "0":
            print(f"[ERROR] {region}: OAuth returned no token")
            return
        
        body = json.dumps({
            "open_id": open_id,
            "open_id_type": "4",
            "login_token": token_val,
            "orign_platform_type": "4"
        })
        
        proto_bytes = await json_to_proto(body, FreeFire_pb2.LoginReq())
        payload = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, proto_bytes)
        
        # ✅✅✅ FIXED: Garena OFFICIAL login URL
        url = f"{LOGIN_URL}/MajorLogin"
        
        # ✅ Random headers (like triple.py)
        user_agents = [
            "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "UnityPlayer/2019.4.24f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "UnityPlayer/2020.3.21f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        ]
        unity_versions = ["2018.4.12f1", "2019.4.24f1", "2020.3.21f1"]
        
        headers = {
            'User-Agent':       random.choice(user_agents),
            'Accept':           "*/*",
            'Accept-Encoding':  "deflate, gzip",
            'X-Ga-Sv':          str(random.randint(1789534050, 1789534100)),
            'Authorization':    "Bearer",
            'X-Ga':             "v1 1",
            'Releaseversion':   RELEASE_VERSION,
            'Content-Type':     "application/x-www-form-urlencoded",
            'X-Unity-Version':  random.choice(unity_versions),
            'PlAy_VeR':         "1.132.1",
            'Ob_VeR':           RELEASE_VERSION,
        }
        
        async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
            resp = await client.post(url, data=payload, headers=headers)
            
            print(f"[DEBUG] {region}: MajorLogin HTTP {resp.status_code}, len={len(resp.content)}")
            
            if resp.status_code != 200:
                print(f"[ERROR] {region}: MajorLogin HTTP {resp.status_code}")
                return
            
            # ✅ Multi-candidate parsing (from triple.py)
            token = None
            
            # Method 1: Direct parse
            try:
                msg = json.loads(json_format.MessageToJson(
                    decode_protobuf(resp.content, FreeFire_pb2.LoginRes)
                ))
                if msg.get('token'):
                    token = msg['token']
                    server_url = msg.get('serverUrl', '')
                    lock_region = msg.get('lockRegion', '')
            except Exception:
                pass
            
            # Method 2: Find protobuf start byte
            if not token:
                def find_protobuf_start(data):
                    if not data or len(data) < 10:
                        return -1
                    region_markers = [
                        b'\x12\x03IND', b'\x12\x03BD', b'\x12\x03BR',
                        b'\x12\x03US',  b'\x12\x03SAC', b'\x12\x03NA',
                    ]
                    for marker in region_markers:
                        idx = data.find(marker)
                        if idx != -1:
                            for i in range(idx - 1, max(idx - 100, -1), -1):
                                if data[i] == 0x08 and i + 2 < len(data) and data[i+1] < 0x80:
                                    return i
                            return idx
                    jwt_marker = data.find(b'eyJ')
                    if jwt_marker != -1:
                        for i in range(jwt_marker - 1, max(jwt_marker - 300, -1), -1):
                            if data[i] == 0x08:
                                return i
                    for i in range(min(50, len(data) - 10)):
                        if data[i] == 0x08 and data[i+1] < 0x80:
                            next_bytes = data[i+5:i+10]
                            if any(b in [0x08, 0x10, 0x12, 0x18, 0x20, 0x22, 0x28, 0x32] for b in next_bytes):
                                return i
                    return 0
                
                start_candidates = []
                primary = find_protobuf_start(resp.content)
                if primary >= 0:
                    start_candidates.append(primary)
                for i in range(min(50, len(resp.content) - 5)):
                    if resp.content[i] == 0x08 and i not in start_candidates:
                        start_candidates.append(i)
                
                for start_idx in start_candidates:
                    try:
                        proto_data = resp.content[start_idx:]
                        decoded = decode_protobuf(proto_data, FreeFire_pb2.LoginRes)
                        msg = json.loads(json_format.MessageToJson(decoded))
                        if msg.get('token'):
                            token = msg['token']
                            server_url = msg.get('serverUrl', '')
                            lock_region = msg.get('lockRegion', '')
                            print(f"[DEBUG] {region}: Parsed from offset {start_idx}")
                            break
                    except Exception:
                        continue
            
            # Method 3: Regex for JWT
            if not token:
                text = resp.content.decode('utf-8', errors='ignore')
                idx = text.find('eyJ')
                if idx != -1:
                    end = idx
                    while end < len(text) and text[end] not in ['"', ' ', '\n', '\r', '\t', '\x00', ',', '}']:
                        end += 1
                    jwt = text[idx:end]
                    if jwt.count('.') >= 2:
                        token = jwt
                        server_url = ""
                        lock_region = ""
            
            if not token:
                print(f"[ERROR] {region}: No token in response")
                return
            
            if not server_url:
                print(f"[WARN] {region}: serverUrl empty, using fallback")
                # Fallback server URLs
                if region == "IND":
                    server_url = CLIENT_URL_IND
                elif region in {"BR", "US", "SAC", "NA"}:
                    server_url = CLIENT_URL_BR
                else:
                    server_url = CLIENT_URL_BD
            
            cached_tokens[region] = {
                'token': f"Bearer {token}",
                'region': lock_region or region,
                'server_url': server_url,
                'expires_at': time.time() + 25200
            }
            
            print(f"[SUCCESS] {region}: Token cached | server={server_url}")
            
    except Exception as e:
        print(f"[ERROR] Failed token creation for {region}: {e}")
        import traceback
        traceback.print_exc()

async def initialize_tokens():
    tasks = [create_jwt(r) for r in SUPPORTED_REGIONS]
    await asyncio.gather(*tasks)

async def refresh_tokens_periodically():
    while True:
        await asyncio.sleep(25200)
        await initialize_tokens()

async def get_token_info(region: str) -> Tuple[str, str, str]:
    info = cached_tokens.get(region)
    if info and time.time() < info['expires_at']:
        return info['token'], info['region'], info['server_url']
    await create_jwt(region)
    info = cached_tokens.get(region, {})
    return info.get('token', ''), info.get('region', ''), info.get('server_url', '')

# === Core Account Fetcher ===

async def GetAccountInformation(uid, unk, region, endpoint, allow_reroute=True):
    payload = await json_to_proto(json.dumps({'a': uid, 'b': unk}), main_pb2.GetPlayerPersonalShow())
    data_enc = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, payload)
    token, lock, server = await get_token_info(region)

    if not server:
        raise Exception(f"Server URL not available for region {region}")

    headers = {
        'User-Agent': USERAGENT,
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/octet-stream",
        'Expect': "100-continue",
        'Authorization': token,
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': "v1 1",
        'ReleaseVersion': RELEASE_VERSION
    }

    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        resp = await client.post(server + endpoint, data=data_enc, headers=headers)
        res_data = json.loads(json_format.MessageToJson(decode_protobuf(resp.content, AccountPersonalShow_pb2.AccountPersonalShowInfo)))

        detected_region = res_data.get('basicInfo', {}).get('region', '').upper()

        if (detected_region == "IND" or lock == "IND") and region != "IND" and allow_reroute:
            uid_region_cache[uid] = "IND"
            return await GetAccountInformation(uid, unk, "IND", endpoint, allow_reroute=False)

        return res_data

# === Wishlist Function ===

async def GetWishList(uid, region):
    try:
        req = GetWishListItems_pb2.CSGetWishListItemsReq()
        req.account_id = int(uid)

        req_json = json_format.MessageToJson(req)
        payload = await json_to_proto(req_json, GetWishListItems_pb2.CSGetWishListItemsReq())
        data_enc = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, payload)

        token, lock, server = await get_token_info(region)
        headers = {
            'User-Agent': USERAGENT,
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/octet-stream",
            'Expect': "100-continue",
            'Authorization': token,
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': RELEASE_VERSION
        }

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            resp = await client.post(server + "/GetWishListItems", data=data_enc, headers=headers)
            res = GetWishListItems_pb2.CSGetWishListItemsRes()
            res.ParseFromString(resp.content)
            return json.loads(json_format.MessageToJson(res))
    except Exception as e:
        raise Exception(f"Wishlist API error: {str(e)}")

# === Rank Helpers ===

def get_br_rank_name(rp):
    try:
        rp = int(rp)
    except:
        return "N/A"
    if rp < 100: return "Bronze I"
    if rp < 200: return "Bronze II"
    if rp < 300: return "Bronze III"
    if rp < 400: return "Silver I"
    if rp < 500: return "Silver II"
    if rp < 600: return "Silver III"
    if rp < 700: return "Gold I"
    if rp < 800: return "Gold II"
    if rp < 900: return "Gold III"
    if rp < 1000: return "Gold IV"
    if rp < 1100: return "Platinum I"
    if rp < 1200: return "Platinum II"
    if rp < 1300: return "Platinum III"
    if rp < 1400: return "Platinum IV"
    if rp < 1500: return "Platinum V"
    if rp < 1600: return "Diamond I"
    if rp < 1700: return "Diamond II"
    if rp < 1800: return "Diamond III"
    if rp < 1900: return "Diamond IV"
    if rp < 2000: return "Diamond V"
    if rp < 2500: return "Heroic"
    if rp < 3000: return "Elite Heroic"
    if rp < 3500: return "Master"
    return "Elite Master"

def get_br_rank_with_score(rp):
    try:
        rp = int(rp)
        return f"{get_br_rank_name(rp)} ({rp})"
    except:
        return "N/A"

def get_cs_rank_name(rp):
    try:
        rp = int(rp)
    except:
        return "N/A"
    if rp < 100: return "Bronze I"
    if rp < 200: return "Bronze II"
    if rp < 300: return "Bronze III"
    if rp < 400: return "Silver I"
    if rp < 500: return "Silver II"
    if rp < 600: return "Silver III"
    if rp < 700: return "Gold I"
    if rp < 800: return "Gold II"
    if rp < 900: return "Gold III"
    if rp < 1000: return "Gold IV"
    if rp < 1100: return "Platinum I"
    if rp < 1200: return "Platinum II"
    if rp < 1300: return "Platinum III"
    if rp < 1400: return "Platinum IV"
    if rp < 1500: return "Platinum V"
    if rp < 1600: return "Diamond I"
    if rp < 1700: return "Diamond II"
    if rp < 1800: return "Diamond III"
    if rp < 1900: return "Diamond IV"
    if rp < 2000: return "Diamond V"
    if rp < 2500: return "Heroic"
    if rp < 3000: return "Elite Heroic"
    if rp < 3500: return "Master"
    return "Elite Master"

def get_cs_rank_with_score(rp):
    try:
        rp = int(rp)
        return f"{get_cs_rank_name(rp)} ({rp})"
    except:
        return "N/A"

def add_rank_info(data):
    try:
        basic = data.get('basicInfo', {})
        if basic:
            br_rp = basic.get('rankingPoints', 0)
            cs_rp = basic.get('csRankingPoints', 0)
            basic['rank_name'] = get_br_rank_with_score(br_rp)
            basic['cs_rank_name'] = get_cs_rank_with_score(cs_rp)

        captain = data.get('captainBasicInfo', {})
        if captain:
            br_rp = captain.get('rankingPoints', 0)
            cs_rp = captain.get('csRankingPoints', 0)
            captain['rank_name'] = get_br_rank_with_score(br_rp)
            captain['cs_rank_name'] = get_cs_rank_with_score(cs_rp)
    except:
        pass
    return data

def format_timestamp_bst(timestamp):
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        bst = timezone(timedelta(hours=6))
        dt_bst = dt.astimezone(bst)
        return dt_bst.strftime("%d %B %Y at %I:%M:%S %p") + " (BST)"
    except:
        return "Unknown"

def find_best_region(uid):
    if uid in uid_region_cache:
        return uid_region_cache[uid]

    check_order = ["IND", "BD"] + [r for r in SUPPORTED_REGIONS if r not in {"IND", "BD"}]

    for region in check_order:
        try:
            data = asyncio.run(GetAccountInformation(uid, "7", region, "/GetPlayerPersonalShow", allow_reroute=False))
            basic = data.get('basicInfo', {})
            if basic.get('accountId'):
                real_region = basic.get('region', region).upper()
                uid_region_cache[uid] = real_region
                return real_region
        except:
            continue

    return None

def resolve_region(uid, force_region=None):
    if force_region and force_region.upper() in SUPPORTED_REGIONS:
        region = force_region.upper()
        uid_region_cache[uid] = region
        return region
    return find_best_region(uid)

def add_equipped_items(data):
    try:
        basic = data.get('basicInfo', {})
        if basic:
            basic['equipped_items'] = {
                "weapon_skins": basic.get('weaponSkinShows', []),
                "pin_id": basic.get('pinId', 0),
                "banner_id": basic.get('bannerId', 0),
                "head_pic": basic.get('headPic', 0),
                "title": basic.get('title', 0),
                "badge_id": basic.get('badgeId', 0),
                "equipped_animation_id": basic.get('equippedAnimationId', 0)
            }
        profile = data.get('profileInfo', {})
        if profile:
            profile['equipped_items'] = {
                "avatar_id": profile.get('avatarId', 0),
                "skin_color": profile.get('skinColor', 0),
                "clothes": profile.get('clothes', []),
                "equipped_skills": profile.get('equipedSkills', []),
                "is_selected": profile.get('isSelected', False),
                "is_selected_awaken": profile.get('isSelectedAwaken', False),
                "equipped_animation_id": profile.get('equippedAnimationId', 0)
            }
    except:
        pass
    return data

# === Decorators ===

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key or api_key != API_KEY:
            return jsonify({"error": "Invalid or missing API key."}), 401
        return f(*args, **kwargs)
    return decorated_function

def cached_endpoint(ttl=300):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            key = (request.path, tuple(request.args.items()))
            if key in cache:
                return cache[key]
            res = fn(*a, **k)
            cache[key] = res
            return res
        return wrapper
    return decorator

# === Endpoints ===

@app.route('/info')
@require_api_key
@cached_endpoint()
def get_account_info():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    region = resolve_region(uid, request.args.get('region'))
    if not region:
        return jsonify({"error": "UID not found in any region."}), 404

    try:
        return_data = asyncio.run(GetAccountInformation(uid, "7", region, "/GetPlayerPersonalShow"))
        return_data = add_rank_info(return_data)
        return_data = add_equipped_items(return_data)

        if 'diamondCostRes' in return_data:
            del return_data['diamondCostRes']

        basic = return_data.get('basicInfo', {})
        if basic:
            if basic.get('createAt'):
                basic['createAt_bst'] = format_timestamp_bst(basic.get('createAt', '0'))
            if basic.get('lastLoginAt'):
                basic['lastLoginAt_bst'] = format_timestamp_bst(basic.get('lastLoginAt', '0'))

        formatted_json = json.dumps(return_data, indent=2, ensure_ascii=False)
        return formatted_json, 200, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data for region {region}: {str(e)}"}), 500

@app.route('/level')
@require_api_key
@cached_endpoint(ttl=300)
def get_level_info():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    region = resolve_region(uid, request.args.get('region'))
    if not region:
        return jsonify({"error": "UID not found in any region."}), 404

    try:
        data = asyncio.run(GetAccountInformation(uid, "7", region, "/GetPlayerPersonalShow"))
        basic = data.get('basicInfo', {})
        level = basic.get('level', 0)
        exp = basic.get('exp', 0)

        return jsonify({
            "uid": uid,
            "username": basic.get('nickname', 'Unknown'),
            "region": basic.get('region', region),
            "level": level,
            "exp": exp,
            "likes": basic.get('liked', 0),
            "badge_count": basic.get('badgeCnt', 0)
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500

@app.route('/region')
@require_api_key
@cached_endpoint(ttl=300)
def get_region_info():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    region = resolve_region(uid, request.args.get('region'))
    if not region:
        return jsonify({"error": "UID not found in any region."}), 404

    try:
        data = asyncio.run(GetAccountInformation(uid, "7", region, "/GetPlayerPersonalShow"))
        basic = data.get('basicInfo', {})
        return jsonify({
            "uid": uid,
            "username": basic.get('nickname', 'Unknown'),
            "region": basic.get('region', region),
            "level": basic.get('level', 0),
            "likes": basic.get('liked', 0),
            "created_at": format_timestamp_bst(basic.get('createAt', '0')),
            "last_login": format_timestamp_bst(basic.get('lastLoginAt', 0))
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500

@app.route('/wishlist')
@require_api_key
@cached_endpoint(ttl=300)
def get_wishlist():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    region = resolve_region(uid, request.args.get('region'))
    if not region:
        return jsonify({"error": "UID not found in any region."}), 404

    try:
        data = asyncio.run(GetWishList(uid, region))
        items = data.get('items', [])
        return jsonify({
            "uid": uid,
            "region": region,
            "total_items": len(items),
            "items": items
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500

@app.route('/refresh', methods=['GET', 'POST'])
@require_api_key
def refresh_tokens_endpoint():
    try:
        asyncio.run(initialize_tokens())
        return jsonify({'message': 'Tokens refreshed for all regions.'}), 200
    except Exception as e:
        return jsonify({'error': f'Refresh failed: {e}'}), 500

@app.route('/clear_cache', methods=['GET', 'POST'])
@require_api_key
def clear_cache():
    uid = request.args.get('uid')
    if uid:
        if uid in uid_region_cache:
            del uid_region_cache[uid]
        return jsonify({"message": f"Cache cleared for UID: {uid}"}), 200
    else:
        uid_region_cache.clear()
        cache.clear()
        return jsonify({"message": "All cache cleared"}), 200

@app.route('/status')
@require_api_key
def status():
    return jsonify({
        "status": "online",
        "release_version": RELEASE_VERSION,
        "login_url": LOGIN_URL,
        "cached_regions": list(cached_tokens.keys()),
        "cached_count": len(cached_tokens)
    }), 200

# === Startup ===

async def startup():
    print("[INIT] Initializing tokens for all regions...")
    await initialize_tokens()
    print("[INIT] Tokens initialized.")
    asyncio.create_task(refresh_tokens_periodically())

if __name__ == '__main__':
    import threading

    # ✅ Run Flask in thread, async loop in main
    def run_flask():
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    print("[START] Server starting...")
    asyncio.run(startup())
