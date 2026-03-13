@app.post("/chat")
async def chat(
    message: str = Body(...),
    session_id: str = Body(...),
    user_id: Optional[str] = Body(None), # ปรับเป็น Optional[str] เพื่อรับค่าจาก PHP
    user_key: str = Body(None),
    user_type: str = Body("Guest")
):
    try:
        if len(message) > MAX_MESSAGE_LENGTH:
            raise HTTPException(status_code=400, detail=f"ข้อความยาวเกินไป...")

        # --- [จุดสำคัญ] จัดการค่า user_id ที่ส่งมาจาก PHP ---
        actual_user_id = None
        # ถ้ามี user_id และไม่ใช่ "null", "0", หรือช่องว่าง ให้แปลงเป็น int
        if user_id and str(user_id).lower() != 'null' and str(user_id) != '0' and str(user_id).strip() != '':
            actual_user_id = int(user_id)
        
        # ปรับ user_type ให้เป็น Guest ทันทีถ้าไม่มี user_id
        if actual_user_id is None:
            user_type = "Guest"

        # 1. เช็ค Semantic Cache (ขุมทรัพย์ความรู้)
        cached_reply, score = await check_semantic_cache(message)
        
        if cached_reply:
            # บันทึกผ่าน handler (ซึ่งตอนนี้มันรู้แล้วว่าถ้าเป็น Guest จะไม่ลง DB หลัก)
            await save_chat_history(session_id, message, cached_reply, actual_user_id, user_key, user_type)
            return {
                "status": "success",
                "answer": cached_reply,
                "source": "cache",
                "similarity": score
            }

        # 2. ถ้าไม่มี Cache ให้รัน RAG
        response = await query_engine.aquery(message)
        answer_text = response.response.strip() if response.response else "ขออภัยครับ ผมไม่พบข้อมูลที่เกี่ยวข้อง"

        # 3. บันทึก (จะแยก Guest/Member อัตโนมัติใน handler ที่เราแก้ไปตะกี้)
        await save_chat_history(session_id, message, answer_text, actual_user_id, user_key, user_type)

        return {
            "status": "success",
            "answer": answer_text,
            "source": "gemini_rag"
        }

    except Exception as e:
        print(f"ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))