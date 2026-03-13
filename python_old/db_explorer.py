import streamlit as st
import chromadb
import pandas as pd

st.set_page_config(page_title="LandLink DB Explorer", layout="wide")

st.title("📂 LandLink - Database Explorer")
st.markdown("หน้านี้ใช้สำหรับส่องดูว่า AI จดจำข้อมูลอะไรไว้ในระบบบ้าง")

try:
    # 1. เชื่อมต่อกับฐานข้อมูล
    client = chromadb.PersistentClient(path="./landlink_db")
    
    # 2. ดึงรายชื่อ Collection
    collections = client.list_collections()
    collection_names = [c.name for c in collections]
    
    if not collection_names:
        st.warning("ไม่พบข้อมูลใน Database กรุณารัน ingest.py ก่อน")
    else:
        selected_name = st.selectbox("เลือกฐานข้อมูลที่ต้องการดู:", collection_names)
        
        if selected_name:
            collection = client.get_collection(selected_name)
            
            # ดึงข้อมูลทั้งหมด
            results = collection.get()
            
            # 3. สรุปข้อมูลเบื้องต้น
            count = collection.count()
            st.info(f"📊 พบข้อมูลทั้งหมด {count} ชิ้น (Chunks)")
            
            # 4. แปลงข้อมูลเป็นตาราง (Pandas DataFrame) เพื่อให้ดูง่าย
            df = pd.DataFrame({
                "ID": results.get("ids", []),
                "เนื้อหา (Document)": results.get("documents", []),
                "แหล่งที่มา (Metadata)": [m.get("file_path", "N/A") for m in results.get("metadatas", [])]
            })
            
            # แสดงตาราง
            st.dataframe(df, use_container_width=True)
            
except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}")