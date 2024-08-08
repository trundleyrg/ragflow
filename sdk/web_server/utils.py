import os
import json
import requests


def build_full_url(base_url, api):
    return os.path.join(base_url, api.lstrip("/"))


def execute_http_request_get(base_url, api, headers, params=None):
    try:
        url = build_full_url(base_url, api)
        res = requests.get(url, headers=headers, params=params).text
        res = json.loads(res)
        return res
    except Exception as e:
        print(e)
        return None


def execute_http_request_post(base_url, api, headers, params=None):
    try:
        url = build_full_url(base_url, api)
        res = requests.post(url, headers=headers, json=params).text
        res = json.loads(res)
        return res
    except Exception as e:
        print(e)
        return None

def remote_chat(data):
    url = 'http://10.0.1.41:8589/api/chat'
    headers = {
        'Content-Type': 'application/json'
    }
    res = json.loads(requests.post(url, headers=headers, json=data).text)["message"]["content"]
    return res