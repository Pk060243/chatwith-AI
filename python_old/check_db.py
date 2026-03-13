import chromadb
db = chromadb.PersistentClient(path="./landlink_db")
collection = db.get_collection("landlink_main")

# ดูจำนวนชิ้นส่วนข้อมูลทั้งหมด
print(f"จำนวนชิ้นข้อมูล (Nodes): {collection.count()}")

# ขอดูตัวอย่าง 3 ชิ้นแรก
print(collection.peek(3)['documents'])