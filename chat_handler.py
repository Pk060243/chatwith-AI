from sqlalchemy import text
from config import engine, Settings,get_pro_db_engine
from typing import Optional
import re
import json

async def check_semantic_cache(user_query: str, threshold: float = 0.95):
    query_embedding = await Settings.embed_model.aget_query_embedding(user_query)
    print(f"DEBUG: Cache Embedding Size = {len(query_embedding)}")
    
    async with engine.connect() as conn:
        # ใช้ SQL ค้นหาคำถามที่ใกล้เคียงที่สุด (Vector Similarity Search)
        result = await conn.execute(
            text("""
              SELECT answer_text, (1 - (embedding <=> :vec)) as similarity
                FROM semantic_cache 
                WHERE (1 - (embedding <=> :vec)) >= :threshold
                ORDER BY similarity DESC
                LIMIT 1
            """),
            {"vec": str(query_embedding), "threshold": threshold}
        )
        row = result.fetchone()
        if row:
            return row[0], row[1] # คืนค่าคำตอบ และคะแนนความเหมือน
        return None, 0

# 2. ฟังก์ชันบันทึกประวัติ และสร้าง Cache (บันทึก Embedding)
# async def save_chat_history(session_id: str, user_msg: str, ai_msg: str, user_id=None, user_key=None, user_type="Guest",):
#     user_embedding = await Settings.embed_model.aget_query_embedding(user_msg)

#     async with engine.begin() as conn:
        
#         if user_type == "Guest" or user_id is None:
#             if len(user_msg) > 10:
#                 await conn.execute(
#                     text("""
#                          INSERT INTO semantic_cache (question_text, embedding , answer_text)
#                          VALUES (:q,:vec,:a)
#                          ON CONFLICT (question_text) DO UPDATE SET answer_text = EXCLUDED.answer_text
                                                  
#                          """),
#                     {"q":user_msg,"vec": str(user_embedding),"a":ai_msg}
#                 )        
#             return True
    
        
#         await conn.execute(
#            text("""
#                 INSERT INTO chat_sessions (id, user_id, user_key, user_type)
#                 VALUES (:sid, :uid, :ukey, :utype)
#                 ON CONFLICT (id) DO UPDATE 
#                 SET updated_at = CURRENT_TIMESTAMP, user_id = EXCLUDED.user_id
#             """),
#             {"sid": session_id, "uid": user_id, "ukey": user_key, "utype": user_type}
#         )
        
#         # 3. บันทึกคำถามของ User (พร้อม Vector)
#         await conn.execute(
#             text("""
#                INSERT INTO chat_messages (session_id, role, content) 
#                 VALUES (:sid, 'user', :content), (:sid, 'ai', :ai_content)
#             """),
#             {"sid": session_id, "content": user_msg, "ai_content": ai_msg}
#         )
        
#         if len(user_msg) > 10: # ดักไว้หน่อย คำถามสั้นๆ ไม่ต้องจำก็ได้
#             await conn.execute(
#                 text("""
#                     INSERT INTO semantic_cache (question_text, embedding, answer_text)
#                     VALUES (:q, :vec, :a)
#                     ON CONFLICT (question_text) DO UPDATE SET answer_text = EXCLUDED.answer_text
#                 """),
#                 {"q": user_msg, "vec": str(user_embedding), "a": ai_msg}
#             )
    
#     return True # ส่งค่ากลับว่าบันทึกสำเร็จ
        
async def save_chat_history(
    session_id: str, 
    user_msg: str, 
    ai_msg: str, 
    user_id=None, 
    user_key=None, 
    user_type="Guest",
    search_log_id: Optional[int] = None  # <--- เพิ่มตัวนี้เพื่อรับ ID จากการ search
):
    user_embedding = await Settings.embed_model.aget_query_embedding(user_msg)

    async with engine.begin() as conn:
        
        # 1. กรณี Guest: บันทึกเข้า Semantic Cache อย่างเดียว
        if user_type == "Guest" or user_id is None:
            if len(user_msg) > 10:
                await conn.execute(
                    text("""
                        INSERT INTO semantic_cache (question_text, embedding , answer_text)
                        VALUES (:q,:vec,:a)
                        ON CONFLICT (question_text) DO UPDATE SET answer_text = EXCLUDED.answer_text
                    """),
                    {"q": user_msg, "vec": str(user_embedding), "a": ai_msg}
                )        
            return True
    
        # 2. กรณีสมาชิก: อัปเดต/สร้าง Session
        await conn.execute(
            text("""
                INSERT INTO chat_sessions (id, user_id, user_key, user_type)
                VALUES (:sid, :uid, :ukey, :utype)
                ON CONFLICT (id) DO UPDATE 
                SET updated_at = CURRENT_TIMESTAMP, user_id = EXCLUDED.user_id
            """),
            {"sid": session_id, "uid": user_id, "ukey": user_key, "utype": user_type}
        )
        
        # 3. บันทึกคำถามและคำตอบลง chat_messages
        # หมายเหตุ: เราแยก INSERT 2 รอบเพื่อให้บรรทัด AI ผูกกับ search_log_id ได้
        await conn.execute(
            text("""
                INSERT INTO chat_messages (session_id, role, content, search_log_id) 
                VALUES 
                    (:sid, 'user', :u_content, NULL),
                    (:sid, 'ai', :a_content, :log_id)
            """),
            {
                "sid": session_id, 
                "u_content": user_msg, 
                "a_content": ai_msg, 
                "log_id": search_log_id  # ผูก ID เฉพาะข้อความ AI
            }
        )
        
        # 4. บันทึกลง Semantic Cache สำหรับคำถามที่ยาวพอ
        if len(user_msg) > 10:
            await conn.execute(
                text("""
                    INSERT INTO semantic_cache (question_text, embedding, answer_text)
                    VALUES (:q, :vec, :a)
                    ON CONFLICT (question_text) DO UPDATE SET answer_text = EXCLUDED.answer_text
                """),
                {"q": user_msg, "vec": str(user_embedding), "a": ai_msg}
            )
    
    return True

async def update_session(session_id:str,user_id:int,user_type:str,user_key:str):
     async with engine.begin() as conn:
         await conn.execute(
             text("""                  
                  UPDATE chat_sessions
                  SET user_id = :uid,
                      user_type = :utype,
                      user_key = :ukey,
                      updated_at = CURRENT_TIMESTAMP
                  WHERE id = :sid
                  """
             ),
             {"uid":user_id,
              "utype":user_type,
              "ukey":user_key,
              "sid":session_id             
              
              }
             
         )
         
# async def get_session_history(session_id: str, user_id: Optional[int], user_type: str):
#     async with engine.connect() as conn:
#         params = {"sid": session_id}
        
#         # 1. ดึงข้อความแชททั้งหมดใน Session นี้ (ไม่ JOIN Log แล้วเพื่อความชัวร์)
#         query_messages = """
#             SELECT m.role, m.content, m.created_at, s.user_id as owner_id
#             FROM chat_messages m
#             INNER JOIN chat_sessions s ON m.session_id = s.id
#             WHERE s.id = :sid AND m.is_deleted = false
#             ORDER BY m.created_at ASC
#         """
        
#         # 2. ดึง Log การค้นหาทรัพย์ล่าสุดของ Session นี้ออกมาเตรียมไว้
#         query_log = """
#             SELECT results_data 
#             FROM property_search_logs 
#             WHERE session_id = :sid 
#             ORDER BY created_at DESC LIMIT 1
#         """
        
#         msg_result = await conn.execute(text(query_messages), params)
#         log_result = await conn.execute(text(query_log), params)
        
#         # ดึงข้อมูล Assets จาก Log มาเก็บในตัวแปร (เป็น String หรือ JSON)
#         log_row = log_result.fetchone()
#         raw_assets_data = log_row[0] if log_row else None

#         messages = []
#         for row in msg_result:
#             assets_list = []
            
#             # 3. ตรวจสอบ: ถ้าเป็นข้อความจาก AI ให้เราเอา Assets จาก Log มาแปะใส่เข้าไป
#             if row.role == 'ai' and raw_assets_data:
#                 try:
#                     # ถ้า Postgres ส่งมาเป็น String ต้อง json.loads ก่อน
#                     import json
#                     data = json.loads(raw_assets_data) if isinstance(raw_assets_data, str) else raw_assets_data
                    
#                     if isinstance(data, list):
#                         for a in data:
#                             p_val = a.get('price') or a.get('sale_price') or 0
#                             assets_list.append({
#                                 "id": a.get("id") or a.get("ID"),
#                                 "name": a.get("name") or a.get("name_asset"),
#                                 "province": a.get("province") or "ชลบุรี",
#                                 "price": f"{float(p_val):,.0f}" if str(p_val).replace('.','').isdigit() else p_val,
#                                 "detail_url": f"assetdetail/assetdetail?id={a.get('id') or a.get('ID')}"
#                             })
#                 except Exception as e:
#                     print(f"⚠️ Error formatting assets: {e}")

#             messages.append({
#                 "role": row.role,
#                 "content": row.content,
#                 "time": row.created_at.isoformat() if row.created_at else None,
#                 "assets": assets_list # ข้อมูลจะถูกส่งออกไปตรงนี้
#             })
            
#         return messages       

async def get_session_history(session_id: str, user_id: Optional[int], user_type: str):
    async with engine.connect() as conn:
        params = {"sid": session_id}
        
        # 1. ดึงข้อความพร้อม Assets ที่ผูกไว้ผ่าน search_log_id (แบบรายบรรทัด)
        query = """
            SELECT 
                m.role, 
                m.content, 
                m.created_at, 
                l.results_data 
            FROM chat_messages m
            LEFT JOIN property_search_logs l ON m.search_log_id = l.id
            WHERE m.session_id = :sid AND m.is_deleted = false
            ORDER BY m.created_at ASC, m.ID ASC
        """
        
        result = await conn.execute(text(query), params)

        messages = []
        for row in result:
            assets_list = []
            
            # 2. ตรวจสอบ: ถ้าบรรทัดนี้มีผลลัพธ์จาก Log (results_data) ผูกอยู่
            if row.results_data:
                try:
                    # แปลงข้อมูลทรัพย์สิน
                    import json
                    data = json.loads(row.results_data) if isinstance(row.results_data, str) else row.results_data
                    
                    if isinstance(data, list):
                        for a in data:
                            # 1. ดึงค่าราคาตรงๆ จาก Log
                             p_val = a.get('price')

                             # 2. ถ้าใน Log ไม่มี Key 'price' (กรณีข้อมูลเก่า) ให้พยายามประกอบร่างจาก sale_price/rent_cost
                             if not p_val or p_val == "联系我们":
                                 try:
                                     s = float(a.get('sale_price') or 0)
                                     r = float(a.get('rent_cost') or 0)
                                     parts = []
                                     if s > 0: parts.append(f"销售价格: {s:,.0f} 泰铢")
                                     if r > 0: parts.append(f"租金: {r:,.0f}/月")
                                     p_val = " | ".join(parts) if parts else "联系我们"
                                 except:
                                     p_val = "联系我们"

                             assets_list.append({
                                 "id": a.get("id") or a.get("ID"),
                                 "name": a.get("name") or a.get("name_asset"),
                                 "province": a.get("province") or "",
                                 "price": p_val, # ใช้ค่าที่ดึงมาหรือประกอบร่างใหม่
                                 "detail_url": f"assetdetail/assetdetail?id={a.get('id') or a.get('ID')}"
                             })
                except Exception as e:
                    print(f"⚠️ Error formatting assets for msg: {e}")

            # 3. ส่งข้อมูลออกไป (ถ้าไม่มี assets_list จะเป็น [] ว่างๆ ให้ frontend)
            messages.append({
                "role": row.role,
                "content": row.content,
                "time": row.created_at.isoformat() if row.created_at else None,
                "assets": assets_list
            })
            
        return messages
async def delete_session_chat(session_id: str):
    # ใช้ begin() จะจัดการ commit ให้เราเองโดยอัตโนมัติ
    async with engine.begin() as conn: 
        await conn.execute(
            text("UPDATE chat_sessions SET is_deleted = true WHERE id = :sid"),
            {"sid": session_id}
        )
        
async def get_all_chats_history(user_id:int,user_type:str):
    async with engine.connect()as conn:
        
        result = await conn.execute(
            text("""
                  SELECT 
                    s.id, 
                    s.created_at,
                    (SELECT m.content FROM chat_messages m 
                     WHERE m.session_id = s.id AND m.role = 'user' 
                     ORDER BY m.created_at ASC LIMIT 1) as first_msg
                FROM chat_sessions s
                WHERE s.user_id = :uid 
                  AND s.user_type = :utype 
                  AND s.is_deleted = false
                ORDER BY s.created_at DESC
                """),
                {"uid": user_id, "utype": user_type}
        )
        chats = []
        for row in result:
            # 2. เช็คว่าถ้ามีข้อความแรก ให้ใช้ข้อความนั้นเป็น Title
            # ถ้ายังไม่มี (แชทใหม่ว่างๆ) ให้ใช้คำว่า "New Chat"
            display_title = row.first_msg if row.first_msg else "New Chat"
            
            if len(display_title) > 30:
                display_title = display_title[:30] + "..."

            chats.append({
                "session_id": row.id,
                "title": display_title,  
                "date": row.created_at.strftime("%d/%m/%Y %H:%M") if row.created_at else ""
            })
        return chats
    
def format_query_to_text(q: dict, lang: str = 'th'):
    # Mapping ประเภททรัพย์ 3 ภาษา
    prop_map = {
        'th': {"Land": "ที่ดิน", "Warehouse": "โกดัง", "Factory": "โรงงาน", "Default": "อสังหาริมทรัพย์"},
        'en': {"Land": "Land", "Warehouse": "Warehouse", "Factory": "Factory", "Default": "Property"},
        'cn': {"Land": "土地", "Warehouse": "仓库", "Factory": "工厂", "Default": "房产"}
    }
    
    deal_map = {
        'th': {"Rent": "เช่า", "Buy": "ซื้อ"},
        'en': {"Rent": "Rent", "Buy": "Sale"},
        'cn': {"Rent": "租赁", "Buy": "买卖"}
    }

    l = lang.lower() if lang.lower() in ['th', 'en', 'cn'] else 'th'
    
    p_type = q.get('prop_type')
    d_type = q.get('deal_type')
    
    prop = prop_map[l].get(p_type, prop_map[l]['Default'])
    deal = deal_map[l].get(d_type, "")
    province = q.get('province', '')
    budget = q.get('budget_rent') or q.get('budget_buy') or ""

    if l == 'en':
        msg = f"Looking for {prop} for {deal}"
        if province: msg += f" in {province}"
        if budget: msg += f" with budget {budget}"
    elif l == 'cn':
        msg = f"寻找位于 {province} 的 {prop} {deal}"
        if budget: msg += f" 预算 {budget}"
    else: # Thai
        msg = f"ช่วยหา{prop} สำหรับ{deal} "
        if province: msg += f"ในจังหวัด {province} "
        if budget: msg += f"งบประมาณ {budget}"
        
    return msg
# ของเสิช


MAPPING = {
    "deal_type": {
        "ซื้อ": "1", "Buy": "1", "购买": "1", 
        "เช่า": "2", "Rent": "2", "租赁": "2", 
        "ซื้อและเช่า": "3", "Both": "3", "两者均可": "3"
    },
    "prop_type": {
        "ที่ดิน": "1", "Land": "1", "土地": "1", 
        "โกดัง": "2", "Warehouse": "2", "仓库": "2", 
        "โรงงาน": "3", "Factory": "3", "工厂": "3"
    },
    "ieat": {
        "นอกนิคมฯ": "1", "Outside": "1", "园区外": "1", 
        "ในนิคมฯ": "2", "Inside": "2", "园区内": "2",
        "ได้ทั้งหมด": None, "Both": None, "两者均可": None  
    },
    "color_zone": {
        "ม่วง": "1", "Purple": "1", "紫色": "1", 
        "เหลือง": "2", "Yellow": "2", "黄色": "2", 
        "ส้ม": "5", "Orange": "5", "橙色": "5", 
        "ม่วงลาย": "4", "Purple-Dot": "4", "紫白相间": "4"
    },
    "free_zone": {
        "ไม่ต้องการ": "1", "No": "1", "不需要": "1", 
        "ต้องการ": "2", "Yes": "2", "需要": "2",
        "ได้ทั้งคู่": None, "Either": None, "两者均可": None  
    }
}

def extract_budget(s):
    if not s: return None
    clean = s.lower().replace(',','')
    nums = re.findall(r'\d+',clean)
    if not nums : return None
    val = int(nums[0])
    if 'k' in clean or '万' in clean: val*=1000 if'k' in clean else 10000
    if 'ล้าน' in clean or 'm' in clean:val *=1000000
    return val

# async def search_properties_logic(query_data: dict):
#     engine_pro = get_pro_db_engine()
#     if not engine_pro: return []

#     async with engine_pro.connect() as conn:
#         # SQL Join ตาราง provinces (area_province คือ ID)
#         sql = "SELECT a.name_asset, a.sale_price, a.rent_cost, p.province_name_th FROM assets_table a LEFT JOIN provinces p ON a.area_province = p.id WHERE 1=1"
#         params = {}

#         # Loop ใส่ Filter ตามที่มีข้อมูลส่งมา
#         if query_data.get('deal_type'):
#             sql += " AND a.type_sell = :d"
#             params["d"] = MAPPING['deal_type'].get(query_data['deal_type'])
        
#         if query_data.get('prop_type'):
#             sql += " AND a.type_asset = :t"
#             params["t"] = MAPPING['prop_type'].get(query_data['prop_type'])

#         if query_data.get('province'):
#             sql += " AND a.area_province IN (SELECT id FROM provinces WHERE province_name_th LIKE :prov OR province_name_en LIKE :prov)"
#             params["prov"] = f"%{query_data['province']}%"

#         # งบประมาณ
#         budget = extract_budget(query_data.get('budget_buy') or query_data.get('budget_rent'))
#         if budget:
#             col = "a.sale_price" if "buy" in str(query_data) else "a.rent_cost"
#             sql += f" AND {col} <= :b"
#             params["b"] = budget

#         sql += " LIMIT 3"
#         res = await conn.execute(text(sql), params)
#         return [dict(row._mapping) for row in res]

# async def search_properties_logic(query_data: dict):
#     print("🟢 DEBUG 1: เริ่มทำงาน search_properties_logic")
#     try:
#         engine_pro = get_pro_db_engine()
#         if not engine_pro: 
#             print("❌ DEBUG: ไม่สามารถสร้าง engine_pro ได้ (เช็ค .env)")
#             return []

#         async with engine_pro.connect() as conn:
#             print("🟡 DEBUG 2: เชื่อมต่อ MySQL สำเร็จ")
            
#             # --- 1. เตรียม SQL Base ---
#             sql = "SELECT a.name_asset, a.sale_price, a.rent_cost, p.province_name_th FROM prod_asset a LEFT JOIN provice p ON a.area_province = p.id WHERE 1=1"
#             params = {}

#             # --- 2. Mapping & Filtering ---
#             if query_data.get('deal_type'):
#                 val = MAPPING['deal_type'].get(query_data['deal_type'])
#                 if val:
#                     sql += " AND a.type_sell = :d"
#                     params["d"] = val
            
#             if query_data.get('prop_type'):
#                 val = MAPPING['prop_type'].get(query_data['prop_type'])
#                 if val:
#                     sql += " AND a.type_asset = :t"
#                     params["t"] = val

#             if query_data.get('province'):
#                 sql += " AND (p.province_name_th LIKE :prov OR p.province_name_en LIKE :prov)"
#                 params["prov"] = f"%{query_data['province']}%"

#             # --- 3. Budget Logic ---
#             budget = extract_budget(query_data.get('budget_buy') or query_data.get('budget_rent'))
#             if budget:
#                 # ตรวจสอบว่าเป็นการซื้อหรือเช่าจากข้อมูลใน query_data
#                 col = "a.sale_price" if query_data.get('budget_buy') else "a.rent_cost"
#                 sql += f" AND {col} <= :b"
#                 params["b"] = budget

#             sql += " LIMIT 3"
#             print(f"🔵 DEBUG 3: กำลังรัน SQL: {sql} | Params: {params}")

#             # --- 4. Execute (จุดที่เสี่ยงค้าง) ---
#             result = await conn.execute(text(sql), params)
#             rows = result.fetchall()
            
#             # แปลงเป็น List of Dicts
#             final_data = [dict(row._mapping) for row in rows]
#             print(f"✅ DEBUG 4: ค้นหาเสร็จ พบ {len(final_data)} รายการ")
            
#             return final_data

#     except Exception as e:
#         # ถ้าพังตรงไหน มันจะพ่น Error ออกมาตรงๆ ไม่เงียบหาย
#         print(f"🔴 ERROR in search_properties_logic: {str(e)}")
#         return []

# async def search_properties_logic(query_data: dict):
#     print(f"🟢 DEBUG 1: เริ่มค้นหาด้วยข้อมูล: {query_data}")
#     try:
#         engine_pro = get_pro_db_engine()
#         if not engine_pro: return []

#         async with engine_pro.connect() as conn:
#             sql = "SELECT a.ID, a.name_asset, a.sale_price, a.rent_cost, p.province_name_th FROM prod_asset a LEFT JOIN provice p ON a.area_province = p.id WHERE 1=1"
#             params = {}

#             # --- 1. Basic Filters (Deal, Prop, Province) ---
#             if query_data.get('deal_type'):
#                 val = MAPPING['deal_type'].get(query_data['deal_type'])
#                 if val:
#                     sql += " AND a.type_sell = :d"
#                     params["d"] = val
            
#             if query_data.get('prop_type'):
#                 val = MAPPING['prop_type'].get(query_data['prop_type'])
#                 if val:
#                     sql += " AND a.type_asset = :t"
#                     params["t"] = val

#             if query_data.get('province'):
#                 sql += " AND (p.province_name_th LIKE :prov OR p.province_name LIKE :prov)"
#                 params["prov"] = f"%{query_data['province']}%"

#             # --- 2. Budget Logic (รองรับ <, >, และช่วง -) ---
#             budget_str = str(query_data.get('budget_buy') or query_data.get('budget_rent') or "")
#             col = "a.sale_price" if query_data.get('budget_buy') else "a.rent_cost"

#             if budget_str:
#                 # สกัดตัวเลขทั้งหมดออกมา (เช่น '50k - 150k' -> [50000, 150000])
#                 nums = []
#                 # ค้นหาตัวเลขและหน่วย
#                 raw_nums = re.findall(r'\d+', budget_str.replace(',', ''))
#                 for n in raw_nums:
#                     val = int(n)
#                     if 'k' in budget_str.lower() or 'พัน' in budget_str: val *= 1000
#                     if 'm' in budget_str.lower() or 'ล้าน' in budget_str or '万' in budget_str: val *= 1000000
#                     nums.append(val)

#                 if nums:
#                     if '>' in budget_str or 'มากกว่า' in budget_str or 'ขึ้นไป' in budget_str:
#                         sql += f" AND {col} >= :b_min"
#                         params["b_min"] = nums[0]
#                     elif '<' in budget_str or 'น้อยกว่า' in budget_str or 'ไม่เกิน' in budget_str:
#                         sql += f" AND {col} <= :b_max"
#                         params["b_max"] = nums[0]
#                     elif len(nums) >= 2: # กรณีเลือกช่วง '50k - 150k'
#                         sql += f" AND {col} BETWEEN :b_min AND :b_max"
#                         params["b_min"] = min(nums)
#                         params["b_max"] = max(nums)
#                     else: # กรณีอื่นๆ (ตัวเลขเดี่ยวๆ)
#                         sql += f" AND {col} <= :b_max"
#                         params["b_max"] = nums[0]

#             # --- 3. เพิ่ม Filter ผังเมือง และ ใน/นอกนิคมฯ (ถ้ามีใน Table) ---
#             if query_data.get('color_zone'):
#                 zone_val = MAPPING['color_zone'].get(query_data['color_zone'])
#                 if zone_val:
#                     sql += " AND a.color_land = :cl" 
#                     params["cl"] = zone_val

#             if query_data.get('ieat'):
#                 ieat_val = MAPPING['ieat'].get(query_data['ieat'])
#                 if ieat_val:
#                     sql += " AND a.industrial_zone = :ie" 
#                     params["ie"] = ieat_val

#             sql += " LIMIT 5"
#             print(f"🔵 DEBUG SQL: {sql} | Params: {params}")

#             result = await conn.execute(text(sql), params)
#             final_data = [dict(row._mapping) for row in result.fetchall()]
#             return final_data

#     except Exception as e:
#         print(f"🔴 ERROR: {str(e)}")
#         return []

async def search_properties_logic(query_data: dict):
    print(f"🟢 DEBUG 1: เริ่มค้นหาด้วยข้อมูล: {query_data}")
    try:
        engine_pro = get_pro_db_engine()
        if not engine_pro: return []

        # 🕵️ เลือกคอลัมน์จังหวัดตามภาษาที่ส่งมา (Default เป็นไทย)
        user_lang = query_data.get('lang', 'th').lower()
        prov_col = "p.province_name_th" # Default
        if user_lang in ['en', 'english']:
            prov_col = "p.province_name"
        elif user_lang in ['cn', 'chinese', 'จีน']:
            prov_col = "p.province_name_zh"

        async with engine_pro.connect() as conn:
            # ใช้ Alias 'AS province' เพื่อให้ Key ในผลลัพธ์คงที่เสมอ
            sql = f"""
                SELECT 
                    a.ID, 
                    a.name_asset, 
                    a.sale_price, 
                    a.rent_cost, 
                    a.type_sell,       
                    a.land_size_rai,  
                    {prov_col} AS province 
                FROM prod_asset a 
                LEFT JOIN provice p ON a.area_province = p.id 
                WHERE a.action_stn = '1'
            """
            params = {}

            # --- 1. Basic Filters ---
            if query_data.get('deal_type'):
                val = MAPPING['deal_type'].get(query_data['deal_type'])
                if val:
                    sql += " AND a.type_sell = :d"
                    params["d"] = val
            
            if query_data.get('prop_type'):
                val = MAPPING['prop_type'].get(query_data['prop_type'])
                if val:
                    sql += " AND a.type_asset = :t"
                    params["t"] = val

            if query_data.get('province'):
                prov_val = f"%{query_data['province']}%"
                # แก้ไขบรรทัดนี้ใน SQL ของคุณ
                sql += """ 
                    AND (
                       REPLACE(LOWER(p.province_name_th), ' ', '') LIKE REPLACE(LOWER(:prov), ' ', '') OR 
                       REPLACE(LOWER(p.province_name), ' ', '') LIKE REPLACE(LOWER(:prov), ' ', '') OR 
                       REPLACE(LOWER(p.province_name_zh), ' ', '') LIKE REPLACE(LOWER(:prov), ' ', '')
                    )
                """
                params['prov'] = prov_val

            # --- 2. Budget Logic ---
            budget_str = str(query_data.get('budget_buy') or query_data.get('budget_rent') or "")
            col = "a.sale_price" if query_data.get('budget_buy') else "a.rent_cost"

            if budget_str:
                nums = []
                # ลบ comma และดึงตัวเลข
                raw_nums = re.findall(r'\d+', budget_str.replace(',', ''))
                for n in raw_nums:
                    val = int(n)
                    # แปลงหน่วย k/m/พัน/ล้าน/万 (รองรับ 3 ภาษา)
                    low_str = budget_str.lower()
                    if 'k' in low_str or 'พัน' in budget_str: val *= 1000
                    if 'm' in low_str or 'ล้าน' in budget_str: 
                        val *= 1000000 # หนึ่งล้าน
                    elif '万' in budget_str: 
                        val *= 10000   # หนึ่งหมื่น (ของจีน)
                    nums.append(val)

                if nums:
                    if any(x in budget_str for x in ['>', 'มากกว่า', 'ขึ้นไป', 'More', '以上']):
                        sql += f" AND {col} >= :b_min"
                        params["b_min"] = nums[0]
                    elif any(x in budget_str for x in ['<', 'น้อยกว่า', 'ไม่เกิน', 'Less', '以下']):
                        sql += f" AND {col} <= :b_max"
                        params["b_max"] = nums[0]
                    elif len(nums) >= 2:
                        sql += f" AND {col} BETWEEN :b_min AND :b_max"
                        params["b_min"] = min(nums)
                        params["b_max"] = max(nums)
                    else:
                        sql += f" AND {col} <= :b_max"
                        params["b_max"] = nums[0]

            # --- 3. Additional Filters (Mapping) ---
            if query_data.get('color_zone'):
                val = MAPPING['color_zone'].get(query_data['color_zone'])
                if val:
                    sql += " AND a.color_land = :cl" 
                    params["cl"] = val

            if query_data.get('ieat'):
                val = MAPPING['ieat'].get(query_data['ieat'])
                if val:
                    sql += " AND a.industrial_zone = :ie" 
                    params["ie"] = val
            
            if query_data.get('free_zone'):
                val = MAPPING['free_zone'].get(query_data['free_zone'])
                if val:
                    sql += " AND a.free_zone = :fz" 
                    params["fz"] = val

            sql += " ORDER BY RAND() LIMIT 5"
            print(f"🔵 DEBUG SQL: {sql} | Params: {params}")

            result = await conn.execute(text(sql), params)
            return [dict(row._mapping) for row in result.fetchall()]

    except Exception as e:
        print(f"🔴 ERROR in search_properties_logic: {str(e)}")
        return []
    
# async def save_property_search_log(session_id, query_params, results_data, ai_summary, user_id=None, user_key=None, user_type="Guest"):
#     async with engine.begin() as conn:
#         # 1. 🛡️ กันเหนียว: สร้างหรืออัปเดต Session ก่อน (ก๊อป Logic มาจาก save_chat_history)
#         # จุดนี้จะแก้ error ForeignKeyViolationError ทันที
#         async with engine.begin() as conn:
#             await conn.execute(
#             text("""
#                  INSERT INTO property_search_logs(session_id, query_params, results_data, ai_summary)
#                  VALUES (:sid, :params, :results, :ai)
#             """),
#             {
#                 "sid": session_id,
#                 'params': json.dumps(query_params, ensure_ascii=False),
#                 "results": json.dumps(results_data, ensure_ascii=False),
#                 "ai": ai_summary
#             }
#         )
#     return True
        
    
async def save_property_search_log(session_id, query_params, results_data, ai_summary, user_id=None, user_key=None, user_type="Guest"):
    try:
        async with engine.begin() as conn:
            # 1. จัดการ Session
            await conn.execute(
                text("""
                    INSERT INTO chat_sessions (id, user_id, user_key, user_type)
                    VALUES (:sid, :uid, :ukey, :utype)
                    ON CONFLICT (id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """),
                {"sid": session_id, "uid": user_id, "ukey": user_key, "utype": user_type}
            )

            # 2. เตรียม JSON
            p_json = json.dumps(query_params, ensure_ascii=False)
            r_json = json.dumps(results_data, ensure_ascii=False)

            # 3. บันทึก Log และเอา ID ออกมา
            result = await conn.execute(
                text("""
                     INSERT INTO property_search_logs(session_id, query_params, results_data, ai_summary)
                     VALUES (:sid, :params, :results, :ai)
                     RETURNING id
                """),
                {"sid": session_id, "params": p_json, "results": r_json, "ai": ai_summary}
            )
            
            new_log_id = result.scalar()  # ดึงค่า ID ที่ได้จาก RETURNING id
            print(f"✅ Save Log Success: ID={new_log_id}")
            return new_log_id # คืนค่าเลข ID กลับไป

    except Exception as e:
        print(f"❌ Critical Error in save_property_search_log: {e}")
        return None
    try:
        # พิมพ์เช็คก่อนว่าข้อมูลที่จะเซฟหน้าตาเป็นยังไง
        print(f"DEBUG SAVE: sid={session_id}, results_count={len(results_data)}")
        
        async with engine.begin() as conn:
            # ส่วนสร้าง Session (เอา IF ออกตามที่คุยกัน)
            await conn.execute(
                text("""
                    INSERT INTO chat_sessions (id, user_id, user_key, user_type)
                    VALUES (:sid, :uid, :ukey, :utype)
                    ON CONFLICT (id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """),
                {"sid": session_id, "uid": user_id, "ukey": user_key, "utype": user_type}
            )

            # ส่วนบันทึก Log - ลองใส่ try ตรงนี้เพื่อดูว่า json.dumps พังไหม
            try:
                p_json = json.dumps(query_params, ensure_ascii=False)
                r_json = json.dumps(results_data, ensure_ascii=False)
            except Exception as je:
                print(f"❌ JSON Serialize Error: {je}")
                r_json = "[]" # กันเหนียวส่งค่าว่างถ้าพัง

            await conn.execute(
                text("""
                     INSERT INTO property_search_logs(session_id, query_params, results_data, ai_summary)
                     VALUES (:sid, :params, :results, :ai)
                     RETURNING id
                """),
                {"sid": session_id, "params": p_json, "results": r_json, "ai": ai_summary}
            )
            new_log_id = result.scalar() # ได้ ID ของ Log มาแล้ว
            return new_log_id
        print("✅ Save Log Success")
        return True
    except Exception as e:
        print(f"❌ Critical Error in save_property_search_log: {e}")
        return False

async def get_cached_normalization(user_text: str):
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT official_value FROM input_normalization_cache WHERE user_input = :txt"),
            {"txt": user_text.strip().lower()}
        )
        row = result.fetchone()
        return row[0] if row else None

async def save_normalization_cache(user_text: str, official_value: dict):
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO input_normalization_cache (user_input, official_value)
                VALUES (:txt, :val)
                ON CONFLICT (user_input) DO NOTHING
            """),
            {"txt": user_text.strip().lower(), "val": json.dumps(official_value)}
        )
        
        
    
def log_usage_and_cost(usage_obj, label="AI Operation"):
    try:
        
        in_tokens = usage_obj.prompt_token_count
        out_tokens = usage_obj.candidates_token_count
        
         # เรทราคา Gemini 1.5 Flash Lite (Input $0.1 / Output $0.4 ต่อล้าน)
        # คิดเรทเงินบาทที่ 36 บาท
        
        cost_thb = ((in_tokens / 1_000_000) * 0.1 + (out_tokens / 1_000_000) * 0.4) * 36
        
        print(f"📊 [{label}] Usage: In {in_tokens} | Out {out_tokens} | Cost: {cost_thb:.4f} THB")
        return {"in": in_tokens, "out": out_tokens, "cost": cost_thb}
    except Exception as e:
        print(f"⚠️ Cannot log usage for {label}: {e}")
        return None