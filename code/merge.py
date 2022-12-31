import sys
import json

with open(sys.argv[1], 'r') as f:
    json_obj = json.load(f)

with open(sys.argv[2], 'r') as f:
    json_obj2 = json.load(f)

for obj in json_obj.get("data"):
    json_obj2.get("data").append(obj)

with open(sys.argv[3], 'w', encoding='utf-8') as f:
    f.write(json.dumps(json_obj2, indent=4, ensure_ascii=False))