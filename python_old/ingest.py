import os
from dotenv import load_dotenv
import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.gemini import GeminiEmbedding

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key :
    raise ValueError ("NOT FOUND SOMETING")

os.environ["GOOGLE_API_KEY"] = api_key

# 2. กำหนดรุ่นของ Embedding (ตัวแปลงข้อความเป็นตัวเลข)
Settings.embed_model = GeminiEmbedding(model_name="models/text-embedding-004")

def run_ingest():
    print("🎯 กำลังเริ่มอ่านข้อมูลจากโฟลเดอร์ data...")
    
    # อ่านไฟล์ .txt ทุกไฟล์ในโฟลเดอร์ data และโฟลเดอร์ย่อย
    documents = SimpleDirectoryReader("./data", recursive=True).load_data()

    # สร้าง/เชื่อมต่อกับฐานข้อมูล ChromaDB ในโฟลเดอร์ landlink_db
    db = chromadb.PersistentClient(path="./landlink_db")
    chroma_collection = db.get_or_create_collection("landlink_main")

    # ตั้งค่าระบบจัดเก็บ
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # เริ่มขั้นตอน 'ฝังเข็ม' ข้อมูล (Indexing)
    print("⏳ กำลังสร้าง Vector Index (ขั้นตอนนี้ใช้ Gemini ช่วยวิเคราะห์)...")
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context,
        show_progress=True
    )
    
    print("✅ สำเร็จ! สร้างฐานข้อมูลความรู้เสร็จแล้วที่โฟลเดอร์ 'landlink_db'")

if __name__ == "__main__":
    run_ingest()