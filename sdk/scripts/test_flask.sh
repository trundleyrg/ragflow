#curl http://10.0.1.41:8591/long_text -X POST -H "Content-Type: application/json" -d '
#{
#  "message": "中国的首都在哪里？"
#}
#'

curl http://127.0.0.1:8591/chat -X POST -H "Content-Type: application/json" -d '
{
  "message": "中国的首都在哪里？"
}
'


