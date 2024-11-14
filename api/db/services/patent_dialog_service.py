import binascii
import os
import json
import re
from copy import deepcopy
from timeit import default_timer as timer

from api.db import LLMType, ParserType, StatusEnum
from api.db.db_models import Dialog, Conversation, DB
from api.db.services.common_service import CommonService
from api.db.services.dialog_service import use_sql, full_question, keyword_extraction, message_fit_in
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.llm_service import LLMService, TenantLLMService, LLMBundle
from api.settings import chat_logger, retrievaler, kg_retrievaler
from rag.app.resume import forbidden_select_fields4resume
from rag.nlp.search import index_name
from rag.utils import rmSpace, num_tokens_from_string, encoder
from api.utils.file_utils import get_project_base_directory


def patent_search(dialog, messages, target="涤纶补片"):
    """
    检索各知识库中的相似数据
    """
    # region 检索知识库配置检查
    kbs = KnowledgebaseService.get_by_ids(dialog.kb_ids)
    embd_nms = list(set([kb.embd_id for kb in kbs]))  # 检查数据向量话一致性
    if len(embd_nms) != 1:
        return False, {"answer": "**ERROR**: Knowledge bases use different embedding models.", "reference": []}
    if all([kb.parser_id == ParserType.KG for kb in kbs]):
        return False, {"answer": "**ERROR**: 当前不支持图数据库检索"}
    retr = retrievaler  # if not is_kg else kg_retrievaler  # 判断调用图数据检索工具还是知识检索工具
    # endregion

    # todo: 检索增强，调用LLM生成相似问句，扩大搜索范围
    questions = [m["content"] for m in messages if m["role"] == "user"][-3:]  # 最近三条用户问句

    # region 模型初始化: 向量/重排序模型
    embd_mdl = LLMBundle(dialog.tenant_id, LLMType.EMBEDDING, embd_nms[0])  # BAAI/bge-large-zh-v1.5
    rerank_mdl = None
    if dialog.rerank_id:
        rerank_mdl = LLMBundle(dialog.tenant_id, LLMType.RERANK, dialog.rerank_id)  # BAAI/bge-reranker-v2-m3
    # endregion

    # region 检索与用户问题相关内容
    tenant_ids = list(set([kb.tenant_id for kb in kbs]))
    kbinfos = retr.patent_retrieval(" ".join(questions),
                                    target_product=target,
                                    embd_mdl=embd_mdl,
                                    tenant_ids=tenant_ids,
                                    kb_ids=dialog.kb_ids,
                                    page_size=dialog.top_n,
                                    similarity_threshold=dialog.similarity_threshold,
                                    vector_similarity_weight=dialog.vector_similarity_weight,
                                    doc_ids=None,
                                    top=dialog.top_k, rerank_mdl=rerank_mdl)
    # endregion
    return True, kbinfos


def patent_chat(dialog, target, messages, relative_info, stream, **kwargs):
    """

    :param dialog: 依据dialog_id，获取对话使用的LLM配置参数。 测试参数：95798030489811ef82c20242ac130006
    :param messages:
    :param stream:
    :param kwargs:
    :return:
    """
    max_tokens = 32768  # 待参考ollama参数修改max_token
    chat_mdl = LLMBundle(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)
    prompt_config = dialog.prompt_config

    questions = [m["content"] for m in messages if m["role"] == "user"][-3:]  # 最近三条用户问句
    if len(questions) > 1 and prompt_config.get("refine_multiturn"):  # prompt将多段对话合并为一句
        questions = [full_question(dialog.tenant_id, dialog.llm_id, messages)]
    else:
        questions = questions[-1:]  # 处理当前问句

    # todo: 增强检索，改写当前问句

    # region 检索与用户问题相关内容
    kb_infos = relative_info
    target_infos = [ck["content_with_weight"] for ck in kb_infos["chunks"] if target in ck["important_kwd"]]
    simi_infos = [ck["content_with_weight"] for ck in kb_infos["chunks"] if target not in ck["important_kwd"]]
    chat_logger.info(
        "{}->{}".format(" ".join(questions), "\n->".join(target_infos)))
    # endregion

    # region 空回复处理
    if not target_infos:
        if prompt_config.get("empty_response"):
            empty_res = prompt_config["empty_response"]
        else:
            empty_res = "知识库中未找到您要的答案！"
        yield {"answer": empty_res, "reference": target_infos, "audio_binary": None}
        return
    # endregion

    # region 生成prompt
    target_infos = "\n------\n".join(target_infos)
    simi_infos = "\n------\n".join(simi_infos)
    cpr_prompt = f"""你是佰仁医疗的产品注册助手，用户当前有一个关于注册产品'{target}'的问题需要回答。知识库中检索到属于该注册产品的信息为：\n{target_infos}\n不属于该注册产品信息，但与用户问题接近的信息为：\n{simi_infos}。
        请结合注册产品信息，参考类似产品信息的回答，回答用户提出的Query。"""
    gen_conf = dialog.llm_setting  # Chat config

    # msg = [{"role": "system", "content": prompt_config["system"].format(**kwargs)}]
    msg = [{"role": "system", "content": cpr_prompt}]
    msg.extend([{"role": m["role"], "content": re.sub(r"##\d+\$\$", "", m["content"])}
                for m in messages if m["role"] != "system"])
    used_token_count, msg = message_fit_in(msg, int(max_tokens * 0.97))
    prompt = msg[0]["content"]
    prompt += "\n\n### Query:\n%s" % " ".join(questions)

    if "max_tokens" in gen_conf:
        gen_conf["max_tokens"] = max_tokens - used_token_count
    # endregion

    # region 生成对话
    def decorate_answer(answer, prompt_config):
        nonlocal kwargs, kb_infos, prompt
        refs = []
        retr = retrievaler
        kbs = KnowledgebaseService.get_by_ids(dialog.kb_ids)
        embd_nms = list(set([kb.embd_id for kb in kbs]))
        embd_mdl = LLMBundle(dialog.tenant_id, LLMType.EMBEDDING, embd_nms[0])  # BAAI/bge-large-zh-v1.5
        if prompt_config.get("quote", True):
            # 依据对话设置来决定是否插入引用
            # todo: 修改插入引用
            answer, idx = retr.insert_citations(answer,
                                                [ck["content_ltks"]
                                                 for ck in kb_infos["chunks"]],
                                                [ck["vector"]
                                                 for ck in kb_infos["chunks"]],
                                                embd_mdl,
                                                tkweight=1 - dialog.vector_similarity_weight,
                                                vtweight=dialog.vector_similarity_weight)  # 插入引用位置
            idx = set([kb_infos["chunks"][int(i)]["doc_id"] for i in idx])
            recall_docs = [
                d for d in kb_infos["doc_aggs"] if d["doc_id"] in idx]
            if not recall_docs:
                recall_docs = kb_infos["doc_aggs"]
            kb_infos["doc_aggs"] = recall_docs

            refs = deepcopy(kb_infos)
            for c in refs["chunks"]:
                if c.get("vector"):
                    del c["vector"]

        return {"answer": answer, "reference": refs, "prompt": prompt}

    # if stream:
    #     last_ans = ""
    #     answer = ""
    #     for ans in chat_mdl.chat_streamly(prompt, msg[1:], gen_conf):
    #         answer = ans
    #         delta_ans = ans[len(last_ans):]
    #         if num_tokens_from_string(delta_ans) < 16:
    #             continue
    #         last_ans = answer
    #         yield {"answer": answer, "reference": {}, "audio_binary": tts(tts_mdl, delta_ans)}
    #     delta_ans = answer[len(last_ans):]
    #     if delta_ans:
    #         yield {"answer": answer, "reference": {}, "audio_binary": tts(tts_mdl, delta_ans)}
    #     yield decorate_answer(answer)
    # else:
    answer = chat_mdl.chat(prompt, msg[1:], gen_conf)
    chat_logger.info("User: {}|Assistant: {}".format(
        msg[-1]["content"], answer))
    res = decorate_answer(answer, prompt_config)
    yield res
    # endregion
