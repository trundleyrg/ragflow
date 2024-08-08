from sdk.web_server.utils import remote_chat


def analyze_answer_process(user_question, raw_question, answer, stream=False):
    """根据用户问题和回答，分析回答思路"""
    prompt = "已知用户的问题是{0}".format(user_question)
    prompt += "现有文档中与它相似的问题是{0}".format(raw_question)
    prompt += "文档中对应的回答是{0}".format(answer)
    prompt += "请你根据如上信息，分析应该如何回答当前用户的问题。"

    chat_data = {
        "model": "qwen2:72b-instruct",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": stream
    }
    res = remote_chat(chat_data)
    return res
