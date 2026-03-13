import google.generativeai as genai
import os

genai.configure(api_key="AIzaSyCPtLPqJ2o3mtcxcXeFiNsXYPbPCUz17dQ")

print("รายชื่อโมเดลที่รองรับการทำ Embedding ใน Key ของคุณ:")
for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(f"-> {m.name}")