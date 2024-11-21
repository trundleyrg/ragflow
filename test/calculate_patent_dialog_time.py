import time

from api.db.services.api_service import API4ConversationService
from api.db.services.dialog_service import DialogService
from api.db.services.patent_dialog_service import patent_search, patent_chat
from api.utils.api_utils import get_data_error_result



def reconstruct_messages(messages: list):
    msg = []
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant" and not msg:
            continue
        msg.append(m)
    if not msg[-1].get("id"):
        msg[-1]["id"] = "0000"
    return msg, msg[-1]["id"]


def get_conversation(conversation_id, messages):
    # region 读取历史对话记录
    e, conv = API4ConversationService.get_by_id(conversation_id)
    if not e:
        return e, "Conversation not found!", None
    msg, message_id = reconstruct_messages(messages)
    conv.message.append(msg[-1])
    if not conv.reference:
        conv.reference = []
    conv.message.append({"role": "assistant", "content": "", "id": message_id})
    conv.reference.append({"chunks": [], "doc_aggs": []})
    # endregion
    # region 读取聊天助手配置参数
    e, dia = DialogService.get_by_id(conv.dialog_id)
    if not e:
        return e, "Dialog not found!", None
    # endregion
    return e, msg, dia


def calculate_times():
    times = dict()
    start_time = time.time()

    req = {
        "conversation_id": "689ed008548511ef80670242ac130006",
        "messages": [
            {"role": "user", "content": "请参照涤纶补片的介绍方式，讲解什么是流通道单瓣补片"}
        ],
        "target": "流出道单瓣补片",
        "stream": False,
        "quote": True,
        "augment": True,
        "refine_multiturn": False,
    }
    e, msg, dia = get_conversation(req["conversation_id"], req["messages"])
    if not e:
        return get_data_error_result(message=msg)
    state, relative_info, tims = patent_search(dia, msg, target=req["target"], augment=req.get("augment", False))

    times = {**times, **tims}
    req["messages"] = msg
    if not state:
        return get_data_error_result(message=relative_info)
    search_time = time.time()
    t1 = search_time - start_time
    times["2. 文档检索时长"] = t1
    print("2. 文档检索时长: ", t1, "s")

    # region 重命名ans中的引用字段
    def rename_field(ans):
        reference = ans['reference']
        if not isinstance(reference, dict):
            return
        for chunk_i in reference.get('chunks', []):
            if 'docnm_kwd' in chunk_i:  # docnm_kwd: filename
                chunk_i['doc_name'] = chunk_i['docnm_kwd']
                chunk_i.pop('docnm_kwd')

    # endregion

    answer = None
    for ans, tims in patent_chat(dia, relative_info=relative_info, **req):
        answer = ans
        times = {**times, **tims}
        break
    rename_field(answer)
    times["3. 回答生成时长"] = time.time() - search_time
    times["共计时长"] = time.time() - start_time
    print("回答生成时长: ", time.time() - search_time, "s")
    print("共计执行时长: ", time.time() - start_time, "s")
    return times


if __name__ == '__main__':
    times = dict()
    for i in range(100):
        tims = calculate_times()
        for key, value in tims.items():
            if key not in times:
                times[key] = value
            else:
                times[key] += value
    for key, value in times.items():
        print("平均结果:")
        print(key, value / 100)
