import requests

doctor_name = "周青"
role = "你是一个文件助手，你的任务是阅读理解文本，并从中提取出对应的结果。"
role += "必须使用中文作答。结果应该完全从文本中得来，不要修改原文内容，不要虚构内容。"
role += "你需要从用户文字中提取{0}这名医生的姓名、所属科室、所在单位、擅长领域等信息，不要提取其他人的信息。".format(
    doctor_name)
role += "返回结果使用json表示。例如{'姓名':'', '性别':'', '所在医院':'', '科室':'', '擅长领域':'', '任教大学':''}。"

# 创建一个 POST 请求
response = requests.post('http://10.0.1.41:8591/long_text',
                         json={'prompt': role, 'message': "周青 超声影像科 科主任，基地主任，教授，主任医师，博士生导师"})

# 打印响应内容
print(response.text)
