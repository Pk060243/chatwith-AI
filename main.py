import os
from dotenv import load_dotenv
from config import setup_landlink,engine, Settings,get_user_id_from_jwt
from chat_handler import check_semantic_cache,save_chat_history,update_session,get_session_history,delete_session_chat,get_all_chats_history,search_properties_logic,save_property_search_log,format_query_to_text,get_cached_normalization,save_normalization_cache,log_usage_and_cost

from fastapi import FastAPI,HTTPException,Body, Query,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from llama_index.core import VectorStoreIndex,Settings,PromptTemplate
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from typing import Optional,Any
from rate_limit import limiter  # ดึงมาจากไฟล์ที่คุณเพิ่งสร้าง
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import json
from config import token_counter

  

load_dotenv()

vector_store = setup_landlink()

index = VectorStoreIndex.from_vector_store(
    vector_store=vector_store, 
    embed_model=Settings.embed_model
)


SYSTEM_PROMPT = """
[Role]
LandLink Senior Advisor. Expert in Thai industrial investment. Use only provided Knowledge Base.

[Strict Formatting - Critical]
- NO MARKDOWN: Never use #, **, or [brackets]. Use plain text only.
- STRUCTURE: Use "Header Name:" followed by a New Line.
- BULLETS: Use only "•" for sub-points. 
- NO CITATIONS: Do not mention document names or source numbers.
- CONCISENESS: Concise mode. Remove all fluff and unnecessary introductions.

[Response Logic]
- GREETINGS: If the user sends a greeting (e.g., Hello, สวัสดี, 你好), reply with a short professional welcome. Do not trigger RAG or Knowledge Base data. Ask the user what they are looking for and direct them to use the search buttons below for land, warehouses, or factories.
- ACCURACY: Prioritize government data, official figures, and legal timelines.
- LINKS: Provide URLs or Form links immediately if they exist in the context.
- OUT OF SCOPE: If the query is unrelated to industrial investment, politely decline.
- WARNINGS:
  • Wood: Alert on Forestry Act and foreign shareholding limits.
  • Land: If 100% foreign (non-BOI), warn about ownership restrictions outside industrial estates.
  • Service: If production includes design/installation, warn about Foreign Business Act (List 3).

[Persona & Language]
- LANGUAGE: Detect the investor's language and MUST reply in the EXACT SAME LANGUAGE (Thai, Chinese, or English).
- TRANSLATION: If the Database Context is in English but the query is in Thai, translate and summarize into professional Thai naturally.
- TONE: Professional Expert. Use "Advisor" or "ผม" for Thai responses.
- FLOW: Start directly with "According to regulations..." or "ตามระเบียบข้อบังคับ..." No "Searching database" or "In my data".

---------------------
Database Context:
{context_str}

Investor Query:
{query_str}
"""

chat_template = PromptTemplate(SYSTEM_PROMPT)
query_engine = index.as_query_engine(similarity_top_k=3)
query_engine.update_prompts({"response_synthesizer:text_qa_template":chat_template})

app = FastAPI(title="Landlink AI API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
   CORSMiddleware,
    allow_origins=["*"], # ในช่วงพัฒนาใส่ "*" เพื่อให้อนุญาตทุกแหล่งที่มา
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

MAX_MESSAGE_LENGTH = 2000

# @app.get("/test-db-connection")
# async def test_db():
#     from chat_handler import check_domain_db_status
#     result = await check_domain_db_status()
#     return result


@app.post("/chat")
@limiter.limit("5/minute")
async def chat(
    request: Request,
    message: str = Body(None),
    session_id: str = Body(...),
    user_id: Any = Body(None),
    user_key: str = Body(None),
    user_type: str = Body("Guest"),
    token: str = Body(None),
    query_data: Any = Body(None),
    lang: Any = Body(None)
):
    try:
        data = await request.json()
        
        print(f"DEBUG: message = {data.get('message')}")
        print(f"DEBUG: query_data = {data.get('query_data')}")
        
        
        # --- 1. สกัดข้อมูลพื้นฐาน ---
        session_id = data.get("session_id")
        message = data.get("message") or ""
        user_type = data.get("user_type", "Guest")
        token = data.get("token")
        query_data = data.get("query_data")
        current_lang = lang.lower() if lang else "th"
        actual_user_id = None

        # --- 2. แกะ Identity จาก Token หรือ Body ---
        if token:
            user_info = get_user_id_from_jwt(token)
            if user_info:
                val = user_info.get("user_id") or user_info.get("userid")
                if val: actual_user_id = int(val)
        
        if not actual_user_id:
            raw_id = data.get("user_id")
            if raw_id and str(raw_id).lower() != 'null' and str(raw_id) != '0':
                actual_user_id = int(raw_id)

        # --- 3. ตรวจสอบความยาวข้อความ ---
        if message and len(message) > MAX_MESSAGE_LENGTH:
            raise HTTPException(status_code=400, detail=f"ข้อความยาวเกินไป...")
        
        

        # --- 4. Logic แยกทางเดิน ---
        
        # กรณีที่ 1: ค้นหาทรัพย์ (MySQL)
        if query_data:
            # --- [STEP 1: AI ด่านหน้าประมวลผลคำค้น] ---
            

            user_raw_input = query_data.get('province', '')
            
            cached_val = await get_cached_normalization(user_raw_input)
            if cached_val:
                query_data.update(cached_val)
            else:
                standardize_prompt = f"""
                [Task: Data Normalizer]
                1. PROVINCE: Use Official Thai name (e.g. 'Chonburi' -> 'ชลบุรี').
                2. BUDGET: '万' -> multiply by 10000.
                Current Data: {json.dumps(query_data, ensure_ascii=False)}
                Return ONLY JSON.
                
                """
                try:
                    token_counter.reset_counts()
                    
                    std_res = await Settings.llm.acomplete(standardize_prompt)
                    #เช็คเงิน
                    
                    in_t = token_counter.prompt_llm_token_count
                    out_t = token_counter.completion_llm_token_count

                    log_usage_and_cost(UsageMock(in_t, out_t), label="Normalize Data")
                    
                        
                    clean_json = std_res.text.strip().replace('```json', '').replace('```', '')
                    normalized_val = json.loads(clean_json)
                    query_data.update(normalized_val)
                    await save_normalization_cache(user_raw_input, normalized_val)
                except:
                    pass 
            
            # --- [STEP 2: ค้นหาใน Database] ---
            db_results = await search_properties_logic(query_data)
            
            lang_map = {"en": "English", "english": "English", "cn": "Chinese", "chinese": "Chinese", "จีน": "Chinese"}
            lang_label = lang_map.get(current_lang, "Thai")
            
            # --- [STEP 3: กรณีไม่พบข้อมูล - กั้นไม่ให้ AI ตอบมั่ว] ---
            if not db_results:
                no_data_msg = {
                    "th": "ขออภัยครับ ไม่พบทรัพย์ที่ตรงตามเงื่อนไขที่คุณต้องการในขณะนี้ ลองปรับงบประมาณหรือทำเลดูอีกครั้งไหมครับ?",
                    "en": "Sorry, we couldn't find any properties matching your criteria. Would you like to adjust your budget or location?",
                    "cn": "抱歉，目前没有找到符合您条件的房源。您想调整预算或搜索区域吗？"
                }
                answer_text = no_data_msg.get(current_lang, no_data_msg['th'])
                readable_msg = format_query_to_text(query_data,lang=current_lang)
                
                log_id = await save_property_search_log(session_id, query_data, [], answer_text, actual_user_id, user_key, user_type)
                await save_chat_history(session_id, readable_msg, answer_text, actual_user_id, user_key, user_type,search_log_id=log_id,)
                return {
                    "status": "success",
                    "answer": answer_text,
                    "assets": []
                }
        
            # --- [STEP 4: กรณีพบข้อมูล - เตรียม List และรัน Prompt 10 ปี+] ---
            assets_list = []
            for row in db_results:
                 # 1. แปลง varchar เป็น string แล้วเช็ค (หรือแปลงเป็น int เพื่อความชัวร์)
                 # ใช้ str() ครอบเพื่อให้แน่ใจว่าเทียบกับ "1", "3" ที่เป็น string ได้
                t_sell = str(row.get("type_sell") or "") 

                # 2. แปลง decimal/int จาก DB เป็น float/int ของ Python
                try:
                    s_price = float(row.get("sale_price") or 0)
                    r_price = float(row.get("rent_cost") or 0)
                    land_size = int(row.get("land_size_rai") or 0)
                except (ValueError, TypeError):
                    s_price, r_price, land_size = 0, 0, 0

                price_parts = []

                # 3. เช็คเงื่อนไขด้วย String (เพราะใน DB เป็น varchar)
                # หรือเช็คจากงบประมาณที่ลูกค้าส่งมา (query_data) ควบคู่ไปด้วย
                if s_price > 0 and (t_sell in ['1', '3'] or query_data.get('budget_buy')):
                    price_parts.append(f"销售价格: {s_price:,.0f} 泰铢")
                    
                if r_price > 0 and (t_sell in ['2', '3'] or query_data.get('budget_rent')):
                    price_parts.append(f"租金: {r_price:,.0f}/月")

                # 4. รวมผลลัพธ์
                display_price = " | ".join(price_parts) if price_parts else "联系我们"

                assets_list.append({
                    "id": row.get("ID"),
                    "name": row.get("name_asset"),
                    "price": display_price,
                    "province": row.get("province"),
                    "detail_url": f"assetdetail/assetdetail?id={row.get('ID')}",
                    "sale_price": s_price,
                    "rent_cost": r_price,
                    "type_sell": t_sell
                })
        
            prompt = f"""
            [Role: Senior Consultant]
            [Language: {lang_label} ONLY]
            [Context: Found {len(assets_list)} assets in {query_data.get('province', 'Thailand')}]

            Rules:
            - Intro: 1 sentence.
            - Pitch: 1 strategic sentence per asset (logistics/zoning focus, max 12 words).
            - Outro: Short call to action.
            - Format: JSON ONLY.

            Data: {json.dumps(assets_list, ensure_ascii=False)}
            Output: {{"intro": "..", "pitches": [".."], "outro": ".."}}
            """
            
            response = await Settings.llm.acomplete(prompt)
            
            #เช็คเงิน
            in_t = token_counter.prompt_llm_token_count
            out_t = token_counter.completion_llm_token_count

            class UsageMock:
                def __init__(self, p, c):
                    self.prompt_token_count = p
                    self.candidates_token_count = c

            usage_info = log_usage_and_cost(UsageMock(in_t, out_t), label="RAG Chat")
          
            
            
            
                
            raw_text = response.text.strip()
            
            try:
                clean_json = raw_text.replace('```json', '').replace('```', '').strip()
                res_data = json.loads(clean_json)
                
                pitches = res_data.get("pitches", [])
                for i in range(len(assets_list)):
                    assets_list[i]['pitch'] = pitches[i] if i < len(pitches) else ""
            
                answer_text = f"{res_data.get('intro', '')}\n\n{res_data.get('outro', '')}"
            except Exception as e:
                print(f"⚠️ JSON Parsing Error: {e}")
                answer_text = raw_text
        
            # --- [STEP 5: บันทึกประวัติและส่งกลับ] ---
            log_id = await save_property_search_log(session_id, query_data, assets_list, answer_text, actual_user_id, user_key, user_type)
            readable_user_msg = format_query_to_text(query_data, lang=current_lang)
            await save_chat_history(session_id, readable_user_msg, answer_text, actual_user_id, user_key, user_type, search_log_id=log_id)
            return {
                "status": "success",
                "answer": answer_text,
                "source": "property_database",
                "assets": assets_list 
            }
        
        # กรณีที่ 2: ถามตอบปกติ (RAG)
        if message:
            cached_reply, score = await check_semantic_cache(message)
            if cached_reply:
                await save_chat_history(session_id, message, cached_reply, actual_user_id, user_key, user_type)
                return {"status": "success", "answer": cached_reply, "source": "cache", "similarity": score}

            response = await query_engine.aquery(message)
            
            #เช็คเงิน
            in_t = token_counter.prompt_llm_token_count
            out_t = token_counter.completion_llm_token_count

            class UsageMock:
                def __init__(self, p, c):
                    self.prompt_token_count = p
                    self.candidates_token_count = c

            usage_info = log_usage_and_cost(UsageMock(in_t, out_t), label="RAG Chat")
           
            
            
            answer_text = response.response.strip() if response.response else "ขออภัยครับ ผมไม่พบข้อมูลที่เกี่ยวข้อง"
            await save_chat_history(session_id, message, answer_text, actual_user_id, user_key, user_type)

            return {"status": "success","answer": answer_text,"source": "gemini_rag","debug_info": {"nodes_found": len(response.source_nodes)}}

        return {"status": "error", "message": "No query or message provided"}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ ERROR in /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/bind-session")
async def bind_session(
    session_id:str = Body(...),
    user_id : int = Body(None),
    user_type:str = Body(...),
    user_key:str=Body(None) #ของวีแชท
    
):
    try: 
        await update_session(session_id,user_id,user_type,user_key)
        
        return {"status": "success", "message": "Session linked successfully"}
    except Exception as e:
        print(f"BIND ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.api_route("/get-history/{session_id}" , methods=["GET","POST"])
async def get_history(
    request: Request,
    session_id: str, 
    user_id: Optional[str] = Query(None),
    user_type: str = Query("Guest"),
):
    
    
    # print(f"🔔 Incoming Request: {request.method} to {session_id}")
    actual_user_id = None
    try:
        
        if request.method == "POST":
            
            body_bytes = await request.body()
            if body_bytes:
                data= await request.json()
                # print("Data from post:",data)
                
                token = data.get("token")                
                if token :
                    user_info = get_user_id_from_jwt(token)                    
                    if user_info :
                        val = user_info.get("user_id") or user_info.get("userid")
                        if val :
                            actual_user_id = int(val)
                            
                            
                if data.get("user_type"):
                    user_type = data.get("user_type")
        if not actual_user_id and user_type:
            u_id_str = str(user_id).lower()
            if u_id_str != 'null' and u_id_str !='0' and u_id_str.strip() !='':
                actual_user_id = int(user_id)                            
        
        # # จัดการค่า user_id ที่ส่งมาจาก PHP (อาจส่งมาเป็น string "null" หรือ "123")
       
        # if user_id and user_id.lower() != 'null' and user_id != '0' and user_id != '':
        #     actual_user_id = int(user_id)
            
        history = await get_session_history(session_id, actual_user_id, user_type)
        
        if not history:
            return {"status": "success", "history": [], "message": "No history found or access denied"}
            
        return {"status": "success", "history": history}
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
    
@app.post("/delete-chat/{session_id}")
async def delete_chat(session_id:str):
    try:
        await delete_session_chat(session_id)
        return {"status": "success", "message": "ลบสำเร็จ"}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}
 
@app.api_route("/get-all-chats", methods=["GET", "POST"])
async def get_all_chats(
    request: Request,
    user_id: Optional[str] = Query(None), 
    user_type: str = Query("Guest")
):
    actual_user_id = None
    try:
        # 1. ถ้ามาเป็น POST (จากมินิโปรแกรม) ให้แกะ Token
        if request.method == "POST":
            body_bytes = await request.body()
            if body_bytes:
                data = await request.json()
                token = data.get("token")
                if token:
                    user_info = get_user_id_from_jwt(token)
                    if user_info:
                        val = user_info.get("user_id") or user_info.get("userid")
                        actual_user_id = int(val) if val else None
                
                user_type = data.get("user_type", user_type)

        # 2. ถ้ามาเป็น GET (จากเว็บ PHP) หรือไม่มี Token แต่มี user_id ใน Query
        if not actual_user_id and user_id:
            u_id_str = str(user_id).lower()
            if u_id_str != 'null' and u_id_str != '0' and u_id_str.strip() != '':
                actual_user_id = int(user_id)

        
        if not actual_user_id:
            return {"status": "error", "message": "Unauthorized: No user_id found"}

        # 4. เรียกฟังก์ชันเดิมที่คุณมี (ส่ง actual_user_id เข้าไป)
        chats = await get_all_chats_history(actual_user_id, user_type)
        
        # print(f"✅ Fetching all chats for ID: {actual_user_id}")
        return {"status": "success", "chats": chats}

    except Exception as e:
        print(f"❌ Error fetching chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# main.py



    
@app.get("/")
def read_root():
    return {"message": "LandLink AI API is online"}


