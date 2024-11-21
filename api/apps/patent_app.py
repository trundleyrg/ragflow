"""
balance patent api
"""
from flask import request

from api.db.db_models import APIToken, Task, File
from api.db.services.api_service import APITokenService, API4ConversationService
from api.db.services.dialog_service import DialogService
from api.db.services.patent_dialog_service import patent_search, patent_chat
from api.settings import RetCode, retrievaler
from api.utils import get_uuid, current_timestamp, datetime_format
from api.utils.api_utils import server_error_response, get_data_error_result, get_json_result, validate_request


def check_authority(token):
    try:
        # 使用 filter 方法替代 query 方法
        objs = APIToken.filter(token=token).first()
        if not objs:
            return False
        else:
            return True
    except Exception as e:
        print(f"权限校验查询出错: {e}")
        return False


def reconstruct_messages(messages: list):
    msg = []
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant" and not msg:
            continue
        msg.append(m)
    if not msg[-1].get("id"):
        msg[-1]["id"] = get_uuid()
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


@manager.route("/patent_search", methods=["POST"])
@validate_request("conversation_id", "messages", "target")
def search():
    """
    通过用户问句，检索文本文档，并返回结果。
    :return:
    """
    # region 1. 权限检查
    if not check_authority(request.headers.get("Authorization").split()[1]):
        return get_json_result(
            data=False, message='Token is not valid!"', code=RetCode.AUTHENTICATION_ERROR)
    # endregion
    req = request.json
    e, msg, dia = get_conversation(req["conversation_id"], req["messages"])
    if not e:
        return get_data_error_result(message=msg)
    state, relative_info = patent_search(dia, msg, target=req["target"], augment=req.get("augment", False))
    return get_json_result(data=relative_info)


@manager.route('/patent_completion', methods=['POST'])
@validate_request("conversation_id", "messages", "target")
def completion():
    """
    不支持workflow/agent跳转的对话
    :return:
    """
    # import time
    # start_time = time.time()
    # region 1. 权限检查
    if not check_authority(request.headers.get("Authorization").split()[1]):
        return get_json_result(
            data=False, message='Token is not valid!"', code=RetCode.AUTHENTICATION_ERROR)
    # endregion
    # check_time = time.time()
    # print("权限校验花费时长: ", check_time - start_time, "s")

    req = request.json
    e, msg, dia = get_conversation(req["conversation_id"], req["messages"])
    if not e:
        return get_data_error_result(message=msg)
    state, relative_info = patent_search(dia, msg, target=req["target"], augment=req.get("augment", False))

    req["messages"] = msg
    if not state:
        return get_data_error_result(message=relative_info)
    # search_time = time.time()
    # print("文档检索时长: ", search_time - check_time, "s")

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

    # def fill_conv(ans, conv, message_id):
    #     conv.reference[-1] = ans["reference"]
    #     conv.message[-1] = {"role": "assistant", "content": ans["answer"], "id": message_id}
    #     ans["id"] = message_id
    #     return conv, message_id

    # region 非流式响应
    answer = None
    for ans in patent_chat(dia, relative_info=relative_info, **req):
        answer = ans
        # conv, message_id = fill_conv(ans, conv, message_id)
        # API4ConversationService.append_message(conv.id, conv.to_dict())  # 数据入库
        break

    rename_field(answer)
    # endregion
    # print("回答生成时长: ", time.time() - search_time, "s")
    # print("共计执行时长: ", time.time() - start_time, "s")
    return get_json_result(data=answer)
