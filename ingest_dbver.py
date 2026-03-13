import os
import time
from dotenv import load_dotenv
from llama_index.core import StorageContext, SimpleDirectoryReader, Settings, VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# 1. ตั้งค่าพื้นฐาน
Settings.embed_model = GoogleGenAIEmbedding(
    model_name="models/gemini-embedding-001",
    output_dimensionality=3072,
    embed_batch_size=1
)

db_params = {
    "host": "localhost", "port": "5432", "user": "postgres", "password": "root", "database": "postgres",
}

vector_store = PGVectorStore.from_params(
    **db_params,
    table_name="data_landlink_data",
    embed_dim=3072
)

# 2. อ่านไฟล์และแปลงเป็น Nodes
print("⌛ กำลังเตรียมข้อมูล...")
documents = SimpleDirectoryReader("./data", recursive=True).load_data()
nodes = Settings.node_parser.get_nodes_from_documents(documents)
print(f"📖 แยกข้อมูลได้ทั้งหมด {len(nodes)} ส่วน (Nodes)")

# 3. ค่อยๆ ส่งเข้า DB ทีละนิดพร้อมหยุดพัก (Manual Loop)
storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex([], storage_context=storage_context) # สร้าง Index เปล่าก่อน

print("🚀 เริ่มนำข้อมูลเข้า (โหมดปลอดภัยพิเศษ)...")

for i, node in enumerate(nodes):
    try:
        # บังคับใส่ทีละ Node
        index.insert_nodes([node])
        print(f"✅ บันทึกแล้ว [{i+1}/{len(nodes)}]")
        
        # ทุกๆ 10 node ให้หยุดพัก 5 วินาที เพื่อ Reset Quota
        if (i + 1) % 10 == 0:
            print("⏳ พักหายใจ 5 วินาที (ป้องกัน Rate Limit)...")
            time.sleep(5)
            
    except Exception as e:
        if "429" in str(e):
            print("⚠️ ติด Rate Limit! ขอหยุดพัก 60 วินาที...")
            time.sleep(60)
            # ลองอีกครั้งสำหรับ Node นี้
            index.insert_nodes([node])
        else:
            print(f"❌ พลาดที่ Node {i}: {e}")

print("\n✅ เสร็จสิ้น! ข้อมูลทั้งหมดถูกบันทึกลง 3072 dimension เรียบร้อย")