import re
import time

from api.db import LLMType, ParserType
from api.db.services.dialog_service import full_question, message_fit_in
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.llm_service import LLMBundle
from api.settings import chat_logger, retrievaler


def combine_infos(infos_a: dict, infos_b: dict) -> dict:
    #
    infos = {"total": infos_a["total"],
             "chunks": [],
             "doc_aggs": {}}
    chunk_id_set = set()
    doc_id_set = set()
    infos_a["chunks"].extend(infos_b["chunks"])
    for chunk_dict in infos_a["chunks"]:
        if chunk_dict["chunk_id"] not in chunk_id_set:
            chunk_id_set.add(chunk_dict["chunk_id"])
            infos["chunks"].append(chunk_dict)
        else:
            continue
        if chunk_dict["doc_id"] not in doc_id_set:
            infos["doc_aggs"][chunk_dict["docnm_kwd"]] = {"doc_id": chunk_dict["doc_id"], "count": 1}
            doc_id_set.add(chunk_dict["doc_id"])
        else:
            infos["doc_aggs"][chunk_dict["docnm_kwd"]]["count"] += 1

    # doc_aggs
    infos["doc_aggs"] = [{"doc_name": k, "doc_id": v["doc_id"], "count": v["count"]} for k, v in
                         sorted(infos["doc_aggs"].items(), key=lambda x: x[1]["count"] * -1)]
    return infos


def rewrite_query(dialog, query, target="涤纶补片"):
    """
    查询重写
    :param dialog:
    :param query:
    :param messages:
    :param target:
    :return:
    """
    start_time = time.time()
    # HyDE方案：LLM创建一个假设答案来响应查询。查询和生成答案都转换为embedding，在chunk中检索相似结果。
    system_prompt = (f"你是一个医疗产品注册助手，你需要根据用户的问题，给出一个合适的答案。"
                     f"当前问题的答案与注册产品{target}有关。"
                     f"回答使用的专业词汇应该准确无误。回答应该简要，字数限制在300字以内。")
    chat_mdl = LLMBundle(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)
    chat_time = time.time()
    print("2.4.1.1 对话模型初始时长: ", chat_time - start_time, "s")
    gen_conf = {  # hyde 配置参数
        "temperature": 0.1,
        "top_p": 0.2,
        "presence_penalty": 0.4,
        "frequency_penalty": 0.6,
        "max_tokens": 512
    }
    hypo_answer = chat_mdl.chat(system_prompt, query, gen_conf)
    print("2.4.1.2 生成假设答案时长: ", time.time() - chat_time, "s")
    return hypo_answer


def patent_search(dialog, messages, target="涤纶补片", augment=True):
    """
    检索各知识库中的相似数据
    """
    # tims = dict()
    # start_time = time.time()
    # region 检索知识库配置检查
    kbs = KnowledgebaseService.get_by_ids(dialog.kb_ids)
    embd_nms = list(set([kb.embd_id for kb in kbs]))  # 检查数据向量话一致性
    if len(embd_nms) != 1:
        return False, {"answer": "**ERROR**: Knowledge bases use different embedding models.", "reference": []}
    if all([kb.parser_id == ParserType.KG for kb in kbs]):
        return False, {"answer": "**ERROR**: 当前不支持图数据库检索"}
    retr = retrievaler  # if not is_kg else kg_retrievaler  # 判断调用图数据检索工具还是知识检索工具
    # endregion
    # check_time = time.time()
    # tims["2.1 配置检查时长"] = check_time - start_time
    # print("2.1 配置检查时长：", check_time - start_time, 's')

    # todo: 检索增强，调用LLM生成相似问句，扩大搜索范围
    questions = [m["content"] for m in messages if m["role"] == "user"][-3:]  # 最近三条用户问句

    # region 模型初始化: 向量/重排序模型
    embd_mdl = LLMBundle(dialog.tenant_id, LLMType.EMBEDDING, embd_nms[0])  # BAAI/bge-large-zh-v1.5
    rerank_mdl = None
    if dialog.rerank_id:
        rerank_mdl = LLMBundle(dialog.tenant_id, LLMType.RERANK, dialog.rerank_id)  # BAAI/bge-reranker-v2-m3
    # endregion
    # model_time = time.time()
    # tims["2.2 模型初始化时长"] = model_time - check_time
    # print("2.2 模型初始化时长：", model_time - check_time, 's')

    # region 检索与用户问题相关内容
    tenant_ids = list(set([kb.tenant_id for kb in kbs]))
    kb_infos = retr.patent_retrieval(" ".join(questions),
                                     target_product=target,
                                     embd_mdl=embd_mdl,
                                     tenant_ids=tenant_ids,
                                     kb_ids=dialog.kb_ids,
                                     page_size=dialog.top_n,
                                     similarity_threshold=dialog.similarity_threshold,
                                     vector_similarity_weight=dialog.vector_similarity_weight,
                                     doc_ids=None,
                                     top=dialog.top_k, rerank_mdl=rerank_mdl)
    # search_time = time.time()
    # tims["2.3 检索时长"] = search_time - model_time
    # print("2.3 检索时长", search_time - model_time, 's')
    if augment:
        hypo_answer = rewrite_query(dialog, [m for m in messages if m["role"] == "user"][-1:], target=target)
        hypo_time = time.time()
        # tims["2.4.1 生成增强问句"] = hypo_time - search_time
        # print("2.4.1 生成增强问句：", hypo_time - search_time, 's')
        hypo_infos = retr.retrieval(str(hypo_answer),
                                    embd_mdl=embd_mdl,
                                    tenant_ids=tenant_ids,
                                    kb_ids=dialog.kb_ids,
                                    page=1,
                                    page_size=dialog.top_n,
                                    similarity_threshold=dialog.similarity_threshold,
                                    vector_similarity_weight=dialog.vector_similarity_weight,
                                    doc_ids=None,
                                    aggs=False,
                                    top=dialog.top_k,
                                    rerank_mdl=rerank_mdl)
        kb_infos = combine_infos(kb_infos, hypo_infos)
        # tims["2.4.2 增强检索时长"] = time.time() - hypo_time
        # print("2.4.2 增强检索时长：", time.time() - hypo_time, 's')
    # endregion
    # tims["2.4 增强检索时长"] = time.time() - search_time
    # print("2.4 增强检索时长:", time.time() - search_time, 's')
    # return True, kb_infos, tims
    return True, kb_infos


def patent_chat(dialog, target, messages, relative_info, stream, **kwargs):
    """

    :param dialog: 依据dialog_id，获取对话使用的LLM配置参数。 测试参数：95798030489811ef82c20242ac130006
    :param messages:
    :param stream:
    :param kwargs:
    :return:
    """
    # tims = dict()
    # start_time = time.time()
    max_tokens = 32768  # 待参考ollama参数修改max_token
    chat_mdl = LLMBundle(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)
    prompt_config = dialog.prompt_config

    questions = [m["content"] for m in messages if m["role"] == "user"][-3:]  # 最近三条用户问句
    if kwargs.get("refine_multiturn"):  # prompt将多段对话合并为一句
        questions = [full_question(dialog.tenant_id, dialog.llm_id, messages)]
    else:
        questions = questions[-1:]  # 处理当前问句

    # region 检索与用户问题相关内容
    kb_infos = relative_info
    target_infos = [ck["content_with_weight"] for ck in kb_infos["chunks"] if target in ck["important_kwd"]]
    simi_infos = [ck["content_with_weight"] for ck in kb_infos["chunks"] if target not in ck["important_kwd"]]
    chat_logger.info(
        "{}->{}".format(" ".join(questions), "\n->".join(target_infos)))
    # endregion

    # config_time = time.time()
    # tims["3.1 对话配置参数初始化时长"] = config_time - start_time
    # print("3.1 对话配置参数初始化时长：", config_time - start_time, 's')

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
    # print("prompt使用token长度", used_token_count)
    # tims["prompt used tokens"] = used_token_count
    # prompt_time = time.time()
    # tims["3.2 prompt初始化时长"] = prompt_time - prompt_time
    # print("3.2 prompt初始化时长：", prompt_time - prompt_time, 's')

    # region 生成对话
    def decorate_answer(answer, prompt):
        nonlocal kwargs, kb_infos
        refs = []
        retr = retrievaler
        kbs = KnowledgebaseService.get_by_ids(dialog.kb_ids)
        embd_nms = list(set([kb.embd_id for kb in kbs]))
        embd_mdl = LLMBundle(dialog.tenant_id, LLMType.EMBEDDING, embd_nms[0])  # BAAI/bge-large-zh-v1.5
        if kwargs.get("quote", False):  # 依据对话设置来决定是否插入引用
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

            for c in kb_infos["chunks"]:
                if c.get("vector"):
                    del c["vector"]

        return {"answer": answer, "reference": kb_infos, "prompt": prompt}

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
    # chat_time = time.time()
    # tims["3.3 对话生成时长"] = chat_time - prompt_time
    # print("3.3 对话生成时长：", chat_time - prompt_time, 's')
    chat_logger.info("User: {}|Assistant: {}".format(
        msg[-1]["content"], answer))
    res = decorate_answer(answer, prompt)
    # tims["3.4 标注引用时长"] = time.time() - chat_time
    # print("3.4 标注引用时长：", time.time() - chat_time, 's')
    # yield res, tims
    yield res
    # endregion
