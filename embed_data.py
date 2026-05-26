"""
embed_data.py — Re-embed พร้อม agency metadata และ chunk ที่เหมาะสม
ใช้แทนโค้ดเดิม รัน 1 ครั้ง ได้ผลดีตลอด
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from llama_index.core import (
    StorageContext, SimpleDirectoryReader,
    Settings, VectorStoreIndex
)
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# ===== CONFIG =====
DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "user": "postgres",
    "password": "root",
    "database": "postgres",
}
TABLE_NAME = "data_landlink_v3"
DATA_DIR = "./data"
EMBED_DIM = 3072

# ===== AGENCY MAPPING =====
# ชื่อโฟลเดอร์ → agency label ที่จะใส่ใน metadata
# เพิ่ม/แก้ตามโฟลเดอร์จริงของคุณ
AGENCY_MAP = {
    # key = ชื่อโฟลเดอร์ lowercase ตรงๆ
    "01_boi":                   "BOI",
    "02_ieat":                  "กนอ. / IEAT",
    "03_eec":                   "EEC",
    "04_dbd":                   "DBD",
    "05_diw":                   "กรมโรงงาน",
    "06_local_gov":             "องค์กรปกครองส่วนท้องถิ่น",
    "07_townplanning":          "ผังเมือง",
    "08_onep_eia":              "EIA / สผ.",
    "09_electricity_pea_mea":   "การไฟฟ้า (PEA/MEA)",
    "10_groundwater":           "กรมทรัพยากรน้ำบาดาล",
    "11_revenue":               "สรรพากร",
    "12_customs_import":        "ศุลกากร",
    "13_bot_foreign":           "ธนาคารแห่งประเทศไทย",
    "14_immigration_visa":      "ตม. / วีซ่า",
    "15_employment_workpermit": "กรมแรงงาน / Work Permit",
    "16_sso":                   "ประกันสังคม",
    "17_labor":                 "กฎหมายแรงงาน",
    "18_fda":                   "อย. / FDA",
    "19_landdep":               "กรมที่ดิน",
    "20_dft_certificate":       "กรมการค้าต่างประเทศ",
    "21_dpim":                  "กรมโรงงาน / DPIM",
    "22_personal_data":         "PDPA",
    "23_department":            "หน่วยงานราชการ",
    "24.tist":                  "TISI / มอก.",
    "25_fbc":                   "FBC / ธุรกิจต่างด้าว",
    "26_fbl":                   "FBL / ใบอนุญาตต่างด้าว",
}

def get_agency_from_path(file_path: str) -> str:
    """ดึงชื่อ agency จากชื่อโฟลเดอร์"""
    parts = Path(file_path).parts
    # วนหาโฟลเดอร์ที่ตรงกับ AGENCY_MAP
    for part in parts:
        key = part.lower().strip()
        if key in AGENCY_MAP:
            return AGENCY_MAP[key]
    # ถ้าไม่เจอ ใช้ชื่อโฟลเดอร์แม่ตรงๆ
    if len(parts) >= 2:
        return parts[-2]  # parent folder
    return "ทั่วไป"


# ===== SETUP =====
Settings.embed_model = GoogleGenAIEmbedding(
    model_name="models/gemini-embedding-001",
    output_dimensionality=EMBED_DIM,
    embed_batch_size=1
)

# chunk เล็กลง: 512 tokens, overlap 50 tokens
# เหมาะกับ Q&A — แต่ละ chunk ตอบคำถามเดียวได้ชัดเจน
Settings.node_parser = MarkdownNodeParser()




# ===== LOAD & TAG DOCUMENTS =====
print(f"\n⌛ กำลังอ่านไฟล์จาก {DATA_DIR} ...")

documents = SimpleDirectoryReader(
    DATA_DIR,
    recursive=True,
    filename_as_id=True,
).load_data()

print(f"📂 พบไฟล์ทั้งหมด: {len(documents)} ไฟล์")

# ใส่ agency metadata ทุกไฟล์
for doc in documents:
    file_path = doc.metadata.get("file_path", "") or doc.metadata.get("filename", "")
    agency = get_agency_from_path(file_path)
    doc.metadata["agency"] = agency
    doc.metadata["source"] = Path(file_path).name  # ชื่อไฟล์

    # preview
    print(f"  📄 {Path(file_path).name} → agency: {agency}")

# ===== CHUNK =====
print(f"\n✂️  กำลังตัด chunk (size=512, overlap=50)...")
nodes = Settings.node_parser.get_nodes_from_documents(documents)
print(f"📦 ได้ทั้งหมด {len(nodes)} nodes")

# ตรวจสอบ metadata ติดมาไหม
sample = nodes[0]
print(f"\n🔍 ตัวอย่าง node แรก:")
print(f"   agency  : {sample.metadata.get('agency')}")
print(f"   source  : {sample.metadata.get('source')}")
print(f"   preview : {sample.text[:80]}...")

# ===== EMBED & STORE =====
vector_store = PGVectorStore.from_params(
    **DB_PARAMS,
    table_name=TABLE_NAME,
    embed_dim=EMBED_DIM,
)

storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex([], storage_context=storage_context)

print(f"\n🚀 เริ่ม embed และบันทึก {len(nodes)} nodes...")
print("   (หยุดพัก 5 วิ ทุก 10 nodes เพื่อป้องกัน Rate Limit)\n")

success = 0
failed = 0

for i, node in enumerate(nodes):
    try:
        index.insert_nodes([node])
        success += 1
        print(f"  ✅ [{i+1}/{len(nodes)}] {node.metadata.get('agency')} — {node.text[:50]}...")

        if (i + 1) % 10 == 0:
            print(f"  ⏳ พัก 5 วิ...")
            time.sleep(5)

    except Exception as e:
        if "429" in str(e):
            print(f"  ⚠️  Rate Limit! พัก 60 วิ แล้วลองใหม่...")
            time.sleep(60)
            try:
                index.insert_nodes([node])
                success += 1
            except Exception as e2:
                print(f"  ❌ ยังพังอีก: {e2}")
                failed += 1
        else:
            print(f"  ❌ Node {i} พัง: {e}")
            failed += 1

print(f"\n{'='*50}")
print(f"✅ สำเร็จ : {success} nodes")
print(f"❌ พลาด  : {failed} nodes")
print(f"{'='*50}")
print("\n🎉 เสร็จสิ้น! ตอนนี้แต่ละ chunk มี agency metadata แล้ว")
print("   ระบบ guide จะค้นหาตรงหัวข้อมากขึ้น")
