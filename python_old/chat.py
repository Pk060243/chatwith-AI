import os
import chromadb
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, StorageContext, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

# 1. โหลด API Key
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")


Settings.llm = GoogleGenAI(
        model="models/gemini-flash-latest",    
        api_key=api_key
)

Settings.embed_model = GoogleGenAIEmbedding(
    model_name="models/text-embedding-004", 
    api_key=api_key
)

def start_chat():
    print("⏳ กำลังโหลดฐานความรู้ LandLink...")
    
    # เชื่อมต่อกับฐานข้อมูล
    db = chromadb.PersistentClient(path="./landlink_db")
    chroma_collection = db.get_or_create_collection("landlink_main")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    
    # โหลด Index จาก Vector Store เดิม (ไม่ต้องสร้างใหม่)
    index = VectorStoreIndex.from_vector_store(vector_store)

    # 3. ตั้งค่า Query Engine (ปิด streaming เพื่อความเสถียรของโควตาฟรี)
    query_engine = index.as_query_engine(streaming=False)

    print("\n🤖: สวัสดีครับ ผม LandLink AI (Stable Edition)")
    print("ระบบพร้อมตอบคำถามจากข้อมูล BOI/DBD/กนอ. แล้วครับ")
    
    while True:
        user_query = input("\n❓ ถามคำถาม: ")
        if user_query.lower() in ['exit', 'quit', 'ออก']:
            break
        
        try:
            print("🔍 กำลังวิเคราะห์ข้อมูล...\n")
            response = query_engine.query(user_query)
            print(f"💡 คำตอบ: {response}")
            print("\n" + "-"*40)
        except Exception as e:
            if "429" in str(e):
                print("❌ โควตาเต็มชั่วคราว! กรุณารอ 30-60 วินาทีแล้วลองถามใหม่นะครับ")
            else:
                print(f"❌ เกิดข้อผิดพลาด: {e}")

if __name__ == "__main__":
    start_chat()