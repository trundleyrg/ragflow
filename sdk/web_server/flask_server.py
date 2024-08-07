"""
医生信息提取
"""

import requests
import json
import re
import logging
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

from GeneralAgent.GeneralAgent import skills

app = Flask(__name__)
# 配置日志
logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)  # 设置日志级别
file_handler = logging.FileHandler("./sdk/logs/flask.log")
output_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
output_handler.setFormatter(formatter)

# 添加处理器到日志器
logger.addHandler(file_handler)
logger.addHandler(output_handler)

# 允许所有来源的跨域请求
CORS(app)


def remove_consecutive_newlines(s):
    return re.sub(r'\n+', '\n', s)


def split_text(text, max_token=3000, separators='\n'):
    """
    Split the text into paragraphs, each paragraph has less than max_token tokens.
    """
    pattern = "[" + re.escape(separators) + "]"
    paragraphs = list(re.split(pattern, text))
    result = []
    current = ''
    for paragraph in paragraphs:
        if len(paragraph) == 0:
            continue
        if skills.string_token_count(current) + skills.string_token_count(paragraph) >= max_token:
            result.append(current)
            current = ''
        current += paragraph + '\n'
    if len(current) > 0:
        result.append(current)
    new_result = []
    for x in result:
        if len(x) > max_token:
            new_result.extend(split_text(x, max_token=max_token, separators="，。,.;；"))
        else:
            new_result.append(x)
    new_result = [x.strip() for x in new_result if len(x.strip()) > 0]
    return new_result


def remote_chat(data):
    url = 'http://10.0.1.41:8589/api/chat'
    headers = {
        'Content-Type': 'application/json'
    }
    res = json.loads(requests.post(url, headers=headers, json=data).text)["message"]["content"]
    return res


def split_string_by_length(s, length=2000):
    return [s[i:i + length] for i in range(0, len(s), length)]


@app.route('/long_text', methods=['POST'])
def long_text():
    txt = request.get_json()
    print(txt)
    # 记录日志
    if "message" not in txt:
        return
    else:
        logger.info(f'long_text Received txt: {txt["message"]} \n')
    if "prompt" not in txt:
        role = "你是一个文件助手，你的任务是阅读理解文本，并从中提取出对应的结果。"
        role += "必须使用中文作答。结果应该完全从文本中得来，不要修改原文内容，不要虚构内容。"
        role += "你需要从用户文字中提取医生的姓名、所属科室、所在单位、擅长领域等信息，不要提取其他人的信息。"
        role += "返回结果使用json表示。例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。"
        prompt = role
    else:
        prompt = txt["prompt"]
    logger.info(f'prompt Received txt: {prompt} \n')
    try:
        temp = remove_consecutive_newlines(txt["message"])
        segments = split_text(temp, 3000)
    except Exception as e:
        segments = split_string_by_length(txt["message"])
        logger.error(e)

    def _process_text(index, content, prompt):
        # role = "你是一个文件助手，你的任务是阅读理解文本，并从中提取出对应的结果。"
        # role += "必须使用中文作答。结果应该完全从文本中得来，不要修改原文内容，不要虚构内容。"
        # role += "你需要从用户文字中提取{0}这名医生的姓名、所属科室、所在单位、擅长领域等信息，不要提取其他人的信息。".format(name)
        # role += "返回结果使用json表示。例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。"
        data = {
            "model": "qwen2:72b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content":
                        "\n".join(content)
                }
            ],
            "stream": False,
            "options": {
                "num_ctx": 32768
            }
        }
        return index, remote_chat(data)

    results = []
    for index, content in enumerate(segments):
        future = _process_text(index, content, prompt)
        results.append(future)

    results.sort(key=lambda x: x[0])
    # abstract_role = "你是一个能理解json的助手。"
    # abstract_role += "请从用户的多段json文本中提取并合并{0}这位医生的姓名、所属科室、所在单位、擅长领域等信息，去掉值为空的结果。".format(doctor_name)
    # abstract_role += "返回结果使用json表示。例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。"

    abstrct_data = {
        "model": "qwen2:72b-instruct",
        "messages": [
            {
                "role": "system",
                "content": prompt
            },
            {
                "role": "user",
                "content":
                    '\n'.join([x[1] for x in results])
            }
        ],
        "stream": False,
        "options": {
            "num_ctx": 32768
        }
    }

    res = remote_chat(abstrct_data)

    start_index = res.find("```json") + len("```json")
    end_index = res.find("```", start_index)
    if start_index != -1:
        res = res[start_index:end_index].strip()
    else:
        res = res
    print(res)
    response = jsonify(content=res)
    response.charset = 'utf-8'
    return response


# @app.route("/chat", methods=['POST'])
# def chat():
#     txt = request.get_json()
#     # 记录日志
#     logger.info(f'chat Received txt: {txt["message"]}')
#     chat_data = {
#         "model": "qwen2:72b-instruct",
#         "messages": [
#             {
#                 "role": "system",
#                 "content": "你是一个json助手，"
#                            "按照这个json格式{'姓名': '', '性别': '', '所在医院': '', '科室': '', '擅长领域': ''}。"
#                            "改正用户json中key错误的问题，不要改变回答"
#             },
#             {
#                 "role": "user",
#                 "content":
#                     txt["message"]
#             }
#         ],
#         "stream": False
#     }
#     res = remote_chat(chat_data)
#     start_index = res.find("```json") + len("```json")
#     end_index = res.find("```", start_index)
#     if start_index != -1:
#         doc_info = res[start_index:end_index].strip()
#     else:
#         doc_info = res
#     print(doc_info)
#     # response = jsonify(content=res)
#     response = jsonify(content=doc_info)
#     response.charset = 'utf-8'
#     return response


if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=8591)
