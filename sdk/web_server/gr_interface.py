import re
import os
import json
import requests
import logging
import gradio as gr
import tempfile
import shutil
from GeneralAgent.GeneralAgent import skills

# 配置日志
logging.basicConfig(filename="./sdk/logs/gr.log", level=logging.INFO)
logger = logging.getLogger(__name__)


def split_text(text, max_token=3000, separators='\n'):
    """
    Split the text into paragraphs, each paragraph has less than max_token tokens.
    """
    pattern = "[" + re.escape(separators) + "]"
    paragraphs = list(re.split(pattern, text))
    result = []
    current = ''
    for paragraph in paragraphs:
        if len(paragraph) < 1:
            continue
        if skills.string_token_count(current) + skills.string_token_count(paragraph) >= max_token:
            result.append(current)
            current = ''
        current += paragraph + '\n'
    if len(current) > 0:
        result.append(current)
    new_result = []
    for x in result:
        if skills.string_token_count(x) > max_token:
            new_result.extend(split_text(x, max_token=max_token, separators="，。,.;；\n"))
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


def llm_chat(input_text):
    # 记录日志
    logger.info(f'chat Received txt: {input_text}')
    chat_data = {
        "model": "qwen2:72b-instruct",
        "messages": [
            {
                "role": "system",
                "content": "你是一个助手，请按照user要求写出思考过程，并完成对应的需求。"
            },
            {
                "role": "user",
                "content": input_text
            }
        ],
        "stream": False
    }
    res = remote_chat(chat_data)
    return res


def long_text(system_prompt, summary_prompt, file_obj):
    global tmpdir
    # # 将文件复制到临时目录中
    shutil.copy(file_obj, tmpdir.name)
    # 获取上传Gradio的文件名称
    FileName = os.path.basename(file_obj)

    # 获取拷贝在临时目录的新的文件地址
    NewfilePath = os.path.join(tmpdir.name, FileName)
    print(NewfilePath)
    # 记录日志
    logger.info(f'user_prompt Received txt: {system_prompt}')
    with open(NewfilePath, 'r', encoding="utf-8") as f:
        txt = f.readlines()
    segments = split_text('\n'.join(txt), 2000)

    def _process_text(index, role, content):
        data = {
            "model": "qwen2:72b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": role
                },
                {
                    "role": "user",
                    "content":
                        "\n".join(content)
                }
            ],
            "stream": False
        }
        return index, remote_chat(data)

    results = []
    for index, content in enumerate(segments):
        future = _process_text(index, system_prompt, content)
        print(future)
        results.append(future)

    results.sort(key=lambda x: x[0])
    abstrct_data = {
        "model": "qwen2:72b-instruct",
        "messages": [
            {
                "role": "system",
                "content": summary_prompt
            },
            {
                "role": "user",
                "content":
                    '\n'.join([x[1] for x in results])
            }
        ],
        "stream": False
    }

    res = remote_chat(abstrct_data)
    print(res)
    # start_index = res.find("```json") + len("```json")
    # end_index = res.find("```", start_index)
    # if start_index != -1:
    #     doc_info = res[start_index:end_index].strip()
    # else:
    #     doc_info = res
    # print(doc_info)
    return res


if __name__ == '__main__':
    # 启动应用，并指定 IP 和端口
    demo = gr.Blocks()

    global tmpdir
    tmpdir = tempfile.TemporaryDirectory(dir="./sdk/web_server/tmpdir")

    with demo:
        gr.Markdown(
            "# 对话界面提供单轮对话测试\n# 长文本对话界面提供长文本对话测试\n * 系统prompt：分段总结长文本切片内容\n * 总结prompt：合并分段文本内容")
        with gr.Tabs():
            with gr.TabItem("对话"):
                text_input = gr.Textbox()
                text_output = gr.Textbox()
                text_button = gr.Button("提交")
            with gr.TabItem("长文本对话"):
                system_input = gr.Textbox(lines=3, placeholder="系统prompt",
                                          value="你是一个文件助手，你的任务是阅读理解文本，并从中提取出对应的结果。必须使用中文作答。"
                                                "结果应该完全从文本中得来，不要修改原文内容，不要虚构内容。"
                                                "你需要从用户文字中提取医生姓名、所属科室、所在单位、擅长领域等信息。"
                                                "返回结果使用json表示。例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。")
                summary_input = gr.Textbox(lines=1, placeholder="总结prompt",
                                           value="你是一个能理解json的助手，请从用户的json文本中提取出医生姓名、所属科室、所在单位、擅长领域等信息，去掉值为空的结果。返回结果使用json表示。"
                                                 "例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。")
                long_file = gr.components.File(label="上传文件")
                long_output = gr.Textbox()
                long_button = gr.Button("提交")

        text_button.click(llm_chat, inputs=text_input, outputs=text_output)
        long_button.click(long_text, inputs=[system_input, summary_input, long_file], outputs=long_output)

    demo.launch(server_name="0.0.0.0", server_port=8591)
