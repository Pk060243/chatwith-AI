"""
guide_qa_handler.py
จัดการ Q&A ที่ผู้ใช้ถาม — บันทึกลง DB และดึงมาแสดงเป็น FAQ
"""

from sqlalchemy import text
from config import engine
from typing import Optional


# ===================================================================
# 1. บันทึก Q&A ลง DB
# ===================================================================
async def save_guide_qa(
    agency: str,
    question: str,
    answer: str,
    article_id: str = "",
    lang: str = "zh",
    user_id=None 
):
    """บันทึกคำถาม-คำตอบลง guide_qa table"""
    try:
        # ไม่บันทึกถ้าคำถามสั้นเกินไป (น้อยกว่า 5 ตัวอักษร)
        if len(question.strip()) < 5:
            return None

        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                    INSERT INTO guide_qa (agency, article_id, question, answer, lang, user_id)
                    VALUES (:agency, :article_id, :question, :answer, :lang, :user_id)
                      RETURNING id
                    
                """),
                {
                    "agency": agency,
                    "article_id": article_id or "",
                    "question": question.strip(),
                    "answer": answer.strip(),
                    "lang": lang,
                    "user_id": user_id
                }
            )
            new_id = result.scalar()
            print(f"✅ Saved Q&A id={new_id} agency={agency}")
            return new_id

    except Exception as e:
        print(f"❌ Error saving guide_qa: {e}")
        return None


# ===================================================================
# 2. ดึง FAQ ตาม agency — เรียงตาม helpful_count และความใหม่
# ===================================================================
async def get_faq_by_agency(
    agency: str,
    lang: str = "zh",
    limit: int = 10
):
    """ดึง Q&A ยอดนิยมของหน่วยงานนั้น สำหรับแสดงเป็น FAQ"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT id, question, answer, helpful_count, created_at
                    FROM guide_qa
                    WHERE agency = :agency
                    ORDER BY helpful_count DESC, created_at DESC
                    LIMIT :limit
                """),
                {"agency": agency, "limit": limit}
            )
            rows = result.fetchall()

        return [
            {
                "id": row.id,
                "question": row.question,
                "answer": row.answer,
                "helpful_count": row.helpful_count,
            }
            for row in rows
        ]

    except Exception as e:
        print(f"❌ Error getting FAQ: {e}")
        return []


# ===================================================================
# 3. ดึง FAQ ทุกหน่วยงาน — สำหรับหน้า FAQ รวม
# ===================================================================
async def get_all_faq(lang: str = "zh", limit: int = 20):
    """ดึง Q&A ยอดนิยมทั้งหมด"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT id, agency, question, answer, helpful_count
                    FROM guide_qa
                    ORDER BY helpful_count DESC, created_at DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            )
            rows = result.fetchall()

        return [
            {
                "id": row.id,
                "agency": row.agency,
                "question": row.question,
                "answer": row.answer,
                "helpful_count": row.helpful_count,
            }
            for row in rows
        ]

    except Exception as e:
        print(f"❌ Error getting all FAQ: {e}")
        return []


# ===================================================================
# 4. Vote ว่า Q&A นี้เป็นประโยชน์
# ===================================================================
async def vote_helpful(qa_id: int):
    """เพิ่ม helpful_count +1"""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE guide_qa SET helpful_count = helpful_count + 1 WHERE id = :id"),
                {"id": qa_id}
            )
        return True
    except Exception as e:
        print(f"❌ Error voting: {e}")
        return False