"""
功能：
1. 生成一个下拉框，可以选择[流出道单瓣补片，限位可扩张人工生物心脏瓣膜，涤纶补片]
2. 生成一个文本框，输入问题。
3. 生成一个按钮，提交输入问题。
4. 生成多列文本框，展示产品相关的文本信息。
5. 生成一个文本框，返回回答。
"""
import requests
import json
import pandas as pd
import gradio as gr

PATENT_CHOICES = ["流出道单瓣补片", "限位可扩张人工生物心脏瓣膜", "涤纶补片"]


def patent(target_product, question):
    ragflow_url = "http://10.0.1.41:8599/v1/patent/patent_completion"

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer ragflow-VlZjUwMWY4NTQ4NTExZWY4ZWY1MDI0Mm"
    }
    data = {
        "conversation_id": "689ed008548511ef80670242ac130006",
        "stream": False,
        "quote": False,
        "augment": True,
        "target": target_product,
        "messages": [
            {"role": "user", "content": question}
        ]
    }
    response = requests.post(url=ragflow_url, headers=headers, json=data)

    def dict2df(d: dict):
        df = pd.DataFrame({"重要关键词": [], "文本块": []})
        for k, chunks in d.items():
            if len(chunks) == 0:
                continue
            for c in chunks:
                df = pd.concat([df, pd.DataFrame({"重要关键词": [k], "文本块": [c]})], ignore_index=True)
        return df

    chunk_part = dict()
    if response.status_code == 200:
        res_dict = json.loads(response.text)
        answer = res_dict["data"]["answer"]
        for chunk in res_dict["data"]["reference"]["chunks"]:
            if chunk["important_kwd"][0] not in chunk_part:
                chunk_part[chunk["important_kwd"][0]] = [chunk["content_with_weight"]]
            else:
                chunk_part[chunk["important_kwd"][0]].append(chunk["content_with_weight"])
        return answer, dict2df(chunk_part)
    else:
        return "", dict2df(chunk_part)


def patent_gr():
    with gr.Blocks() as demo:
        gr.Markdown("# 专利注册产品检索\n")
        product = gr.Dropdown(PATENT_CHOICES, label="产品")
        question = gr.Textbox(label="问题查询", value="请参照涤纶补片的介绍方式，讲解什么是流通道单瓣补片")
        submit = gr.Button("提交")
        chunk_table = gr.Dataframe(headers=["重要关键词", "文本块"], type="array")
        answer = gr.Textbox(label="回答", interactive=True)

        submit.click(patent, [product, question], [answer, chunk_table])
    return demo


def unit_test():
    product = "流出道单瓣补片"
    question = "请参照涤纶补片的介绍方式，讲解什么是流通道单瓣补片"
    patent(product, question)


def main():
    # unit_test()
    demo = patent_gr()
    demo.launch(server_name="0.0.0.0", server_port=8595)  # REPORT_SERVER_PORT = 8595


if __name__ == '__main__':
    main()
