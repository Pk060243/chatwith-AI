"""
guide_handler.py
Handles Investment Guide search, article generation, and Q&A responses.
Separate from chat_handler.py — does not modify existing chat functionality.
"""

from sqlalchemy import text
from config import engine, Settings
import json
import re
import os

TABLE_NAME = "data_data_landlink_v3"


# ===================================================================
# UTILITIES
# ===================================================================

def clean_text(t: str) -> str:
    """Remove Markdown formatting from text."""
    if not t:
        return t
    t = re.sub(r'#{1,6}\s*', '', t)
    t = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'^\s*[-*]\s+', '• ', t, flags=re.MULTILINE)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def detect_agency(content: str) -> str:
    """Detect agency name from content keywords."""
    c = content.lower()
    kw = {
        "BOI": ["boi", "board of investment", "ส่งเสริมการลงทุน", "บัตรส่งเสริม"],
        "กนอ. / IEAT": ["ieat", "กนอ", "นิคมอุตสาหกรรม", "industrial estate"],
        "EEC": ["eec", "อีอีซี", "eastern economic corridor"],
        "DBD": ["dbd", "กรมพัฒนาธุรกิจ", "จดทะเบียนบริษัท", "บจก"],
        "กรมโรงงาน": ["กรมโรงงาน", "diw", "โรงงานอุตสาหกรรม", "รง.4"],
        "องค์กรปกครองส่วนท้องถิ่น": ["อปท", "อบต", "เทศบาล"],
        "ผังเมือง": ["ผังเมือง", "town planning", "color zone", "ผังสี"],
        "EIA / สผ.": ["eia", "onep", "สผ", "environmental impact"],
        "การไฟฟ้า (PEA/MEA)": ["pea", "mea", "การไฟฟ้า", "electricity"],
        "กรมทรัพยากรน้ำบาดาล": ["groundwater", "น้ำบาดาล", "ขุดเจาะ"],
        "สรรพากร": ["สรรพากร", "revenue department", "ภาษีนิติบุคคล", "vat", "wht"],
        "ศุลกากร": ["customs", "ศุลกากร", "นำเข้า", "ส่งออก"],
        "ธนาคารแห่งประเทศไทย": ["bot", "ธนาคารแห่งประเทศไทย", "foreign exchange"],
        "ตม. / วีซ่า": ["immigration", "ตรวจคนเข้าเมือง", "visa", "non-b"],
        "กรมแรงงาน / Work Permit": ["work permit", "ใบอนุญาตทำงาน", "กรมการจัดหางาน"],
        "ประกันสังคม": ["sso", "ประกันสังคม", "social security"],
        "กฎหมายแรงงาน": ["labor law", "กฎหมายแรงงาน", "ค่าจ้างขั้นต่ำ"],
        "อย. / FDA": ["fda", "อย.", "food and drug"],
        "กรมที่ดิน": ["กรมที่ดิน", "land department", "โฉนด"],
        "กรมการค้าต่างประเทศ": ["dft", "กรมการค้าต่างประเทศ", "certificate of origin"],
        "กรมโรงงาน / DPIM": ["dpim", "กรมอุตสาหกรรมพื้นฐาน", "เหมืองแร่"],
        "PDPA": ["pdpa", "personal data", "ข้อมูลส่วนบุคคล"],
        "TISI / มอก.": ["tisi", "มอก", "มาตรฐาน"],
        "FBC / ธุรกิจต่างด้าว": ["fbc", "foreign business certificate"],
        "FBL / ใบอนุญาตต่างด้าว": ["fbl", "foreign business license"],
    }
    for agency, keywords in kw.items():
        if any(k in c for k in keywords):
            return agency
    return "Thailand Investment Info"


def generate_related_topics(content: str, current_agency: str) -> list:
    """Generate related agency topics from content."""
    all_agencies = [
        "BOI", "กนอ. / IEAT", "EEC", "DBD", "กรมโรงงาน",
        "องค์กรปกครองส่วนท้องถิ่น", "ผังเมือง", "EIA / สผ.",
        "การไฟฟ้า (PEA/MEA)", "กรมทรัพยากรน้ำบาดาล", "สรรพากร",
        "ศุลกากร", "ธนาคารแห่งประเทศไทย", "ตม. / วีซ่า",
        "กรมแรงงาน / Work Permit", "ประกันสังคม", "กฎหมายแรงงาน",
        "อย. / FDA", "กรมที่ดิน", "กรมการค้าต่างประเทศ",
        "กรมโรงงาน / DPIM", "PDPA", "TISI / มอก.",
        "FBC / ธุรกิจต่างด้าว", "FBL / ใบอนุญาตต่างด้าว"
    ]
    cl = content.lower()
    related = [
        {"id": a, "label": a, "query": f"ข้อมูลและขั้นตอน {a}"}
        for a in all_agencies
        if a != current_agency and a.lower().split("/")[0].strip() in cl
    ]
    if not related:
        related = [
            {"id": a, "label": a, "query": f"ข้อมูลและขั้นตอน {a}"}
            for a in all_agencies if a != current_agency
        ][:3]
    return related[:4]


async def generate_suggested_questions(content: str, agency: str) -> list:
    """Use LLM to generate 3 suggested follow-up questions in Chinese."""
    try:
        prompt = f"""
Based on this content about {agency} in Thailand:
---
{content[:600]}
---
Generate 3 practical follow-up questions in Chinese (中文) that an investor would ask.
Return JSON array ONLY: ["question1", "question2", "question3"]
No markdown, no explanation.
"""
        response = await Settings.llm.acomplete(prompt)
        clean = response.text.strip().replace('```json', '').replace('```', '').strip()
        questions = json.loads(clean)
        if isinstance(questions, list):
            return questions[:3]
    except Exception as e:
        print(f"Warning: Could not generate suggested questions: {e}")
    # Fallback questions in Chinese
    return [
        f"{agency}需要哪些文件？",
        f"{agency}的办理流程需要多长时间？",
        f"{agency}的相关费用是多少？"
    ]


def get_thai_date() -> str:
    """Return current date in Thai Buddhist calendar format."""
    from datetime import datetime
    months = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.',
              'ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']
    d = datetime.now()
    return f"{d.day} {months[d.month-1]} {d.year+543}"


# ===================================================================
# 1. GUIDE SEARCH
#    Input:  query + category
#    Output: list of article cards (id, title, summary, agency)
#    Speed:  uses direct SQL title extraction (no LLM) for fast response
# ===================================================================
async def guide_search_logic(query: str, category: str = "", top_k: int = 12):
    try:
        query_embedding = await Settings.embed_model.aget_query_embedding(query)

        async with engine.connect() as conn:
            agency_filter = "AND metadata_->>'agency' = :agency" if category and category != "all" else ""
            params = {"vec": str(query_embedding), "top_k": top_k}
            if category and category != "all":
                params["agency"] = category

            result = await conn.execute(
                text(f"""
                    SELECT id, text as content, metadata_,
                           (1 - (embedding <=> :vec)) as similarity
                    FROM {TABLE_NAME}
                    WHERE (1 - (embedding <=> :vec)) >= 0.55
                    {agency_filter}
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """),
                params
            )
            rows = result.fetchall()

        if not rows:
            return []

        cards = []
        seen = set()
        raw_cards = []

        # Step 1: Build raw cards without LLM
        for row in rows:
            metadata = {}
            if row.metadata_:
                try:
                    metadata = json.loads(row.metadata_) if isinstance(row.metadata_, str) else row.metadata_
                except:
                    pass

            clean_content = clean_text(row.content)
            content_key = clean_content[:80]
            if content_key in seen:
                continue
            seen.add(content_key)

            agency = metadata.get("agency") or detect_agency(clean_content)
            title_raw = _extract_title_fast(clean_content, agency)
            summary_raw = _extract_summary_fast(clean_content)

            raw_cards.append({
                "id": str(row.id),
                "title_raw": title_raw,
                "summary_raw": summary_raw,
                "agency": agency,
                "similarity": float(row.similarity),
                "content": clean_content,
            })

        if not raw_cards:
            return []

        # Step 2: Translate ALL titles and summaries in ONE LLM call
        try:
            items_json = json.dumps(
                [{"i": i, "t": c["title_raw"], "s": c["summary_raw"]} for i, c in enumerate(raw_cards)],
                ensure_ascii=False
            )
            translate_prompt = f"""
Translate the following Thai investment content titles and summaries to Chinese (中文).
Return JSON array ONLY with same structure, translated to Chinese.
No explanation, no markdown.

Input: {items_json}

Output format: [{{"i": 0, "t": "Chinese title", "s": "Chinese summary"}}, ...]
"""
            response = await Settings.llm.acomplete(translate_prompt)
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            translated = json.loads(raw)
            zh_map = {item["i"]: item for item in translated}
        except Exception as e:
            print(f"Warning: Batch translation failed: {e}")
            zh_map = {}

        # Step 3: Build final cards with translated text
        for i, card in enumerate(raw_cards):
            zh = zh_map.get(i, {})
            cards.append({
                "id": card["id"],
                "title": zh.get("t") or card["title_raw"],
                "summary": zh.get("s") or card["summary_raw"],
                "agency": card["agency"],
                "similarity": card["similarity"],
                "content": card["content"],
            })

        return cards

    except Exception as e:
        print(f"Error in guide_search_logic: {e}")
        return []


def _extract_title_fast(content: str, agency: str) -> str:
    """
    Extract title from content.
    Looks for section headers like [1. xxx] or ### xxx first,
    then falls back to first meaningful line.
    """
    lines = [re.sub(r'#{1,6}\s*', '', l).strip() for l in content.split('\n') if len(l.strip()) > 10]

    # Try to find a header line (contains Thai section markers)
    for line in lines[:5]:
        # Skip lines that look like body text (long sentences)
        if len(line) < 80 and ('[' in line or line.endswith(']') or '：' in line):
            clean = re.sub(r'[\[\]]', '', line).strip()
            if clean:
                return clean[:60] + ("..." if len(clean) > 60 else "")

    # Fallback: use first line
    if lines:
        return lines[0][:60] + ("..." if len(lines[0]) > 60 else "")
    return f"{agency} — 相关信息"


def _extract_summary_fast(content: str) -> str:
    """
    Extract a clean 2-sentence summary from content.
    Skips header lines, takes first meaningful sentences.
    """
    lines = [re.sub(r'#{1,6}\s*', '', l).strip() for l in content.split('\n') if len(l.strip()) > 20]
    # Skip header-like lines
    body_lines = [l for l in lines if not ('[' in l and ']' in l) and len(l) > 30]
    summary = ' '.join(body_lines[:2])
    return (summary[:160] + "...") if len(summary) > 160 else summary


# ===================================================================
# 2. GUIDE ARTICLE
#    Input:  article_id / query / content_cache
#    Output: full article body + suggested questions + related topics
#    Speed:  uses content_cache if available (skips DB fetch)
# ===================================================================
async def guide_article_logic(article_id: str, query: str, agency: str, content_cache: str = ""):
    try:
        full_content = ""

        # Step 1: Use cached content from search result (fastest)
        if content_cache:
            full_content = clean_text(content_cache)

        # Step 2: Fetch from DB by article id
        if not full_content and article_id:
            try:
                aid = int(article_id)
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text(f"SELECT text FROM {TABLE_NAME} WHERE id = :id"),
                        {"id": aid}
                    )
                    row = result.fetchone()
                    if row:
                        full_content = clean_text(row.text)
            except (ValueError, TypeError):
                pass

        # Step 3: Search by query if still no content
        if not full_content and query:
            cards = await guide_search_logic(f"{agency} {query}", agency, top_k=3)
            if cards:
                full_content = "\n\n".join([c["content"] for c in cards[:2]])

        if not full_content:
            return None

        # Step 4: LLM summarize and translate to Chinese
        summarize_prompt = f"""
You are an investment guide writer for Thailand.
Rewrite the following raw content about {agency} into a clean, readable article in Chinese (中文).

Rules:
- Output in Chinese ONLY
- No Markdown symbols (#, **, ---, ###)
- Use bullet points with •
- Logical order, remove duplicates
- Concise length

Raw content:
{full_content[:2000]}

Write the article in Chinese:
"""
        try:
            response = await Settings.llm.acomplete(summarize_prompt)
            full_content = clean_text(response.text.strip())
        except Exception as e:
            print(f"Warning: Summarize failed, using raw content: {e}")

        # Generate suggested questions and related topics in parallel
        suggested = await generate_suggested_questions(full_content, agency)
        related = generate_related_topics(full_content, agency)

        return {
            "body": full_content,
            "updated_at": get_thai_date(),
            "suggested_questions": suggested,
            "related_topics": related
        }

    except Exception as e:
        print(f"Error in guide_article_logic: {e}")
        return None


# ===================================================================
# 3. GUIDE ASK
#    Input:  question + agency + context
#    Output: answer in Chinese + source reference
#    Speed:  uses direct SQL vector search (no LlamaIndex query engine)
#    Smart:  falls back to general AI knowledge if no DB results found
# ===================================================================
async def guide_ask_logic(question: str, agency: str, article_id: str, context_title: str):
    try:
        # Search relevant content from vector DB
        query_embedding = await Settings.embed_model.aget_query_embedding(question)

        async with engine.connect() as conn:
            agency_filter = "AND metadata_->>'agency' = :agency" if agency else ""
            params = {"vec": str(query_embedding), "top_k": 4}
            if agency:
                params["agency"] = agency

            result = await conn.execute(
                text(f"""
                    SELECT text, metadata_,
                           (1 - (embedding <=> :vec)) as similarity
                    FROM {TABLE_NAME}
                    WHERE (1 - (embedding <=> :vec)) >= 0.5
                    {agency_filter}
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """),
                params
            )
            rows = result.fetchall()

        print(f"DEBUG ask: nodes={len(rows)}")

        # Fallback: use general AI knowledge if no DB results
        if not rows:
            prompt = f"""
You are a Thailand investment regulations expert for LandLink platform.
Your scope is LIMITED to Thailand investment topics only.

Scope includes:
- BOI, IEAT, EEC, DBD, DIW, Revenue Department, Customs, BOT
- Immigration/Visa, Work Permit, Labor Law, SSO
- Land Department, FDA, PDPA, TISI, FBC, FBL, DFT, DPIM
- Factory licenses, environmental law (EIA), town planning
- Any topic related to investing or doing business in Thailand

If question is NOT related to Thailand investment or the agencies above,
reply ONLY with: "抱歉，此问题超出投资咨询范围，请咨询相关专业人士。"

Otherwise answer in Chinese (中文) ONLY with:
- Plain text only, no Markdown
- Use • for bullet points
- Be accurate and concise
- End with: "⚠️ 以上为一般性参考信息，建议向相关部门确认最新规定。"

Agency: {agency}
Question: {question}

Answer in Chinese:
"""
            response = await Settings.llm.acomplete(prompt)
            answer = clean_text(response.text.strip())
            return {
                "answer": answer,
                "source": "⚠️ General reference — please verify with the relevant authority"
            }

        # Build context from DB results
        context = "\n\n".join([clean_text(r.text) for r in rows[:3]])

        # Answer using DB context
        prompt = f"""
You are a Thailand investment guide assistant (LandLink).
Your scope is LIMITED to Thailand investment topics only.

If question is NOT related to Thailand investment, business, taxes, labor law,
or the government agencies listed below, reply ONLY with:
"抱歉，此问题超出投资咨询范围，请咨询相关专业人士。"

Agencies in scope: BOI, IEAT, EEC, DBD, DIW, Revenue Dept, Customs, BOT,
Immigration, Work Permit, Labor Law, SSO, Land Dept, FDA, PDPA, TISI, FBC, FBL

Otherwise answer using the knowledge base below. Reply in Chinese (中文) ONLY.

Rules:
- Plain text only, no Markdown (#, **, ---, ###)
- Use • for bullet points
- Cite regulation/announcement numbers if available
- If knowledge base is insufficient, supplement with general Thai law knowledge
  and note: "⚠️ 部分信息来自一般性参考，建议向相关部门确认。"

Agency: {agency}
Topic: {context_title}

Knowledge Base:
{context[:2500]}

Question: {question}

Answer in Chinese:
"""
        response = await Settings.llm.acomplete(prompt)
        answer = clean_text(response.text.strip())

        if not answer:
            answer = "抱歉，暂时找不到相关信息，请直接联系相关部门咨询。"

        # Extract source from metadata
        source = ""
        if rows:
            try:
                meta = json.loads(rows[0].metadata_) if isinstance(rows[0].metadata_, str) else rows[0].metadata_
                source = meta.get("source") or meta.get("file_name") or f"LandLink Database — {agency}"
            except:
                source = f"LandLink Database — {agency}"

        return {"answer": answer, "source": source}

    except Exception as e:
        print(f"Error in guide_ask_logic: {e}")
        return {
            "answer": "系统错误，请稍后再试。",
            "source": ""
        }