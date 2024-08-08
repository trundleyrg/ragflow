"""
专利相似问答回答方法总结
"""

import os
import json
import requests
import logging
import gradio as gr
from GeneralAgent.GeneralAgent import skills

from sdk.web_server.utils import execute_http_request_get, execute_http_request_post
from sdk.web_server.analyze_qa import analyze_answer_process

# 配置日志
DEBUG = True
if DEBUG:
    logging.basicConfig(level=logging.INFO)
else:
    logging.basicConfig(filename="./sdk/logs/gr.log", level=logging.INFO)
logger = logging.getLogger(__name__)

base_url = "http://10.0.1.41:8590/v1"
api_key = "Bearer ragflow-VlZjUwMWY4NTQ4NTExZWY4ZWY1MDI0Mm"
headers = {
    'Content-Type': 'application/json',
    'Authorization': api_key
}


def create_new_conversation():
    """新建对话"""
    global base_url, headers
    api = "api/new_conversation"
    # url = os.path.join(base_url, api)
    params = {"user_id": "restful api"}
    res = execute_http_request_get(base_url, api, headers, params)
    # res = requests.get(url, headers=headers, params=params).text
    # res = json.loads(res)
    if res is None:
        return None
    else:
        conversation_id = res["data"]["id"]
        return conversation_id


def get_history(conversation_id, user_id=""):
    """
    依据对话id获取历史对话记录
    :param conversation_id:
    :param user_id:
    :return:
    """
    global base_url, headers
    try:
        api = os.path.join("api/conversation/", conversation_id.lstrip("/"))
        params = {"user_id": user_id}
        res = execute_http_request_get(base_url, api, headers, params)
        res = res["data"]
        chat_history = res["message"]
        reference = res["reference"]
        return chat_history, reference
    except Exception as e:
        print(e)
        return [], None


def search_question(user_question, chat_history=[], conversation_id="0c6bbd9c549311ef9f1a0242ac130006", stream=False):
    global base_url, api_key
    # 查找相似问题
    user_question = "限位可扩张人工生物心脏瓣膜-补充资料内容说明 CH1.11.7 建议符合性声明中明确符合最新法规要求。"
    current_query = {"role": "user", "content": user_question}
    chat_history.append({"role": "user", "content": user_question})
    # 对话
    api = "api/completion/"
    headers = {"Content-Type": "application/json", "Authorization": api_key}
    if stream:
        headers["Cache-control"] = "no-cache"
        headers["Connection"] = "keep-alive"
        headers["X-Accel-Buffering"] = "no"
        headers["Content-Type"] = "text/event-stream; charset=utf-8"
    # url = os.path.join(base_url, )
    params = {"conversation_id": conversation_id,
              "messages": [current_query],
              "stream": stream,
              "doc_id": "afa094884af711ef8fef0242ac130005"
              }
    res = execute_http_request_post(base_url, api, headers=headers, params=params)
    answer = res["data"]["answer"]
    res = analyze_answer_process(user_question, user_question, answer)  # todo: 补充文档中的问题
    print(res)
    return chat_history


def draw_gr(demo):
    # conv_id = create_new_conversation()
    conv_id = "0c6bbd9c549311ef9f1a0242ac130006"
    history, reference = get_history(conv_id)  # todo: 添加reference
    with demo:
        gr.Markdown(
            "# 资料查询\n"
        )
        # with gr.Tabs():
        # with gr.TabItem("QA检索"):
        chatbot = gr.Chatbot(
            history,
            type="messages",
            show_label=False,
            show_copy_button=True
        )
        question_input = gr.Textbox(lines=1,
                                    label="查询问题",
                                    placeholder="请输入问题")
        search_button = gr.Button("提交问题")
        search_button.click(search_question, inputs=[question_input, chatbot], outputs=[chatbot])
    return demo


def main():
    """依据用户query搜索相关"""
    # 对话
    # test_content = "提供所有与人体直接或间接接触的原材料（包括包装系统）的质控标准和入厂检测报告。"
    # conversation_id = create_new_conversation(test_content)

    search_question(None)
    # init web ui
    demo = gr.Blocks()
    demo = draw_gr(demo)
    demo.launch(server_name="0.0.0.0", server_port=8592)


if __name__ == '__main__':
    main()
