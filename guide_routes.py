"""
guide_routes.py — final version
"""

from fastapi import APIRouter, Body, Request, HTTPException
from guide_handler import guide_search_logic, guide_article_logic, guide_ask_logic
from guide_qa_handler import save_guide_qa, get_faq_by_agency, get_all_faq, vote_helpful
import asyncio

guide_router = APIRouter(prefix="/guide", tags=["Investment Guide"])


@guide_router.post("/search")
async def guide_search(
    request: Request,
    query: str = Body(...),
    category: str = Body("all"),
    user_type: str = Body("Agent"),
    token: str = Body(None),
):
    try:
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="query is required")
        if len(query) > 500:
            raise HTTPException(status_code=400, detail="query too long")

        results = await guide_search_logic(
            query=query.strip(),
            category=category if category != "all" else "",
            top_k=12
        )
        return {"status": "success", "results": results, "count": len(results), "query": query}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ /guide/search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@guide_router.post("/article")
async def guide_article(
    request: Request,
    article_id: str = Body(""),
    query: str = Body(""),
    agency: str = Body(""),
    context_title: str = Body(""),
    content_cache: str = Body(""),
    user_type: str = Body("Agent"),
    token: str = Body(None),
):
    try:
        if not article_id and not query and not content_cache:
            raise HTTPException(status_code=400, detail="article_id, query or content_cache required")

        result = await guide_article_logic(
            article_id=article_id,
            query=query,
            agency=agency,
            content_cache=content_cache
        )

        if not result:
            return {
                "status": "success",
                "body": "",
                "title": context_title,
                "updated_at": "",
                "suggested_questions": [
                    f"{agency}需要哪些文件？",
                    f"{agency}的办理流程需要多长时间？",
                    f"{agency}的相关费用是多少？"
                ],
                "related_topics": []
            }

        return {
            "status": "success",
            "body": result["body"],
            "title": context_title,
            "updated_at": result["updated_at"],
            "suggested_questions": result["suggested_questions"],
            "related_topics": result["related_topics"]
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ /guide/article error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@guide_router.post("/ask")
async def guide_ask(
    request: Request,
    question: str = Body(...),
    agency: str = Body(""),
    article_id: str = Body(""),
    context_title: str = Body(""),
    token: str = Body(None),
    user_type: str = Body("Agent"),
):
    try:
        if not question or not question.strip():
            raise HTTPException(status_code=400, detail="question is required")
        if len(question) > 1000:
            raise HTTPException(status_code=400, detail="question too long")

        # แกะ user_id จาก token
        user_id = None
        if token:
            from config import get_user_id_from_jwt
            user_info = get_user_id_from_jwt(token)
            if user_info:
                val = user_info.get("user_id") or user_info.get("userid")
                user_id = int(val) if val else None

        result = await guide_ask_logic(
            question=question.strip(),
            agency=agency,
            article_id=article_id,
            context_title=context_title
        )

        answer = result["answer"]

        asyncio.create_task(save_guide_qa(
            agency=agency,
            question=question,
            answer=answer,
            article_id=article_id,
            lang="zh",
            user_id=user_id
        ))

        return {"status": "success", "answer": answer, "source": result.get("source", "")}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ /guide/ask error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@guide_router.get("/faq/{agency}")
async def get_faq(agency: str, lang: str = "zh", limit: int = 10):
    try:
        faqs = await get_faq_by_agency(agency=agency, lang=lang, limit=limit)
        return {"status": "success", "agency": agency, "faqs": faqs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guide_router.get("/faq-all")
async def get_all_faqs(lang: str = "zh", limit: int = 6):
    try:
        faqs = await get_all_faq(lang=lang, limit=limit)
        return {"status": "success", "faqs": faqs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guide_router.post("/vote")
async def vote_faq(request: Request):
    try:
        body = await request.json()
        qa_id = int(body.get("qa_id"))
        ok = await vote_helpful(qa_id)
        return {"status": "success" if ok else "error"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))