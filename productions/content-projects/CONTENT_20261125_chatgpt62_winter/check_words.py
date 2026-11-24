"""Independent closed-script-free listening check for the short numeric and name passages."""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

media=Path(sys.argv[1])
keys=sys.argv[2:]
parts=[{"text":"次の音声をそれぞれ日本語で逐語的に書き起こしてください。ことに数字、モデル名、価格、文末を聞いたまま記し、判断しづらい部分は[不明]としてください。返答はIDをキー、書き起こしを値にしたJSONオブジェクト。数字は算用数字。原稿は与えません。"}]
for key in keys:
    path=media/"voice"/key/"turn-00/voice.wav"
    parts.extend([{"text":"ID "+key},{"inlineData":{"mimeType":"audio/wav","data":base64.b64encode(path.read_bytes()).decode()}}])
body={"contents":[{"parts":parts}],"generationConfig":{"temperature":0,"responseMimeType":"application/json"}}
model="gemini-3.8-flash"
key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
api=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key})
with urllib.request.urlopen(api,timeout=150) as f:data=json.load(f)
result=json.loads("".join(p.get("text","") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought")))
if set(result)!=set(keys): raise ValueError(result.keys())
(media/"qa"/("independent-"+"-".join(keys)+".json")).write_text(json.dumps({"model":model,"transcripts":result},ensure_ascii=False,indent=2),encoding="utf-8")
for k,v in result.items():print(k,v)
