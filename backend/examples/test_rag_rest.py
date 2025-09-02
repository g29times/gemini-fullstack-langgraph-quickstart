import requests
import json

url = "http://www-test.raritag.cn/intelligence-platform/bidProject/search"

payload = json.dumps([
  "农田建设项目 招投标"
])
headers = {
  'Accept': '*/*',
  'Content-Type': 'application/json',
  'Authorization': 'Bearer eyJhbGciOiJIUzUxMiJ9.eyJjcmVhdGVfdGltZSI6IjIwMjUtMDktMDEgMTQ6NDc6NTgiLCJ1c2VyX2lkIjoxNTk2MDQxNzE0NDQ0MTg1NjAxLCJ1c2VyX25hbWUiOiLpgpPlrrbmmI4gIDEzNzEzNTUxMzQ0IiwidXNlcl9rZXkiOiJhakM3cjI5Sm50QUdIaGR1MGZnSU0iLCJuZXdfZmxhZyI6Im5ld19mbGFnIn0.sm3yfjGIMJd-EZIAKuBqgczSROpHOfTIuW_ZbIeON_7Dsu_g2AWI9gawWNFxDd6T_S5yqOt-Rix2DG5Lux6vwA'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
