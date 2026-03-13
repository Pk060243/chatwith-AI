import os
import jwt

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from sqlalchemy.ext.asyncio import create_async_engine
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
import time

from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
import tiktoken


load_dotenv()

JWT_SECRET = os.getenv("TOKEN_JWT")
ALGORITHM = "HS256"
def get_user_id_from_jwt(token: str):
    # print(f"DEBUG: Token received = {token[:20]}...")
    if not token:
        return None

    try:
        # 1. ตัด "Bearer " ออก (ถ้ามี)
        # ใช้ .replace() หรือ .split() เพื่อให้เหลือแต่ตัว Code ยาวๆ
        clean_token = token.replace("Bearer ", "").strip()

        # 2. ถอดรหัส (ใช้ Secret Key เดียวกับที่ระบบ Login ใช้เจนออกมา)
        payload = jwt.decode(
            clean_token, 
            JWT_SECRET, # Secret Key ของคุณ
            algorithms=["HS256"]
        )

        # 3. คืนค่าเป็น Dictionary 
        # print("🔍 FULL JWT PAYLOAD:", payload)
        return {
            "user_id": payload.get("ID") or payload.get("userid"),
        }

    except jwt.ExpiredSignatureError:
        print("❌ Token หมดอายุ")
        return None
    except jwt.InvalidTokenError as e:
        print(f"❌ Token ไม่ถูกต้อง: {str(e)}")
        return None
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {str(e)}")
        return None

Settings.llm = GoogleGenAI(model="models/gemini-3.1-flash-lite-preview")
Settings.embed_model = GoogleGenAIEmbedding(model_name="models/gemini-embedding-001",output_dimensionality=3072 )
DB_URL = f"postgresql+asyncpg://{os.getenv('DATABASE_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_async_engine(DB_URL)

token_counter = TokenCountingHandler(
    tokenizer=tiktoken.get_encoding("cl100k_base").encode
)
Settings.callback_manager = CallbackManager([token_counter])



PRO_DB_URL = (
    f"mysql+aiomysql://{os.getenv('PRO_DB_USER')}:{os.getenv('PRO_DB_PASS')}"
    f"@{os.getenv('PRO_DB_HOST')}:{os.getenv('PRO_DB_PORT')}/{os.getenv('PRO_DB_NAME')}"
)
pro_engine = create_async_engine(
    PRO_DB_URL, 
    pool_pre_ping=True, 
    pool_recycle=3600
)


def get_pro_db_engine():
    user = os.getenv("PRO_DB_USER")
    password = os.getenv("PRO_DB_PASS")
    host = os.getenv("PRO_DB_HOST")
    port = os.getenv("PRO_DB_PORT", "3306")
    database = os.getenv("PRO_DB_NAME")
    
    if not all([user, password, host, database]):
        print("❌ Error: ข้อมูล PRO_DB ใน .env ไม่ครบถ้วน")
        return None

    url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
    
    return create_async_engine(
        url, 
        pool_pre_ping=True, 
        pool_recycle=3600
    )

def setup_landlink():
    
   return PGVectorStore.from_params(
        host = os.getenv("DB_HOST"),
        port = os.getenv("DB_PORT"),
        user = os.getenv("DATABASE_USER"),
        password = os.getenv("DB_PASSWORD"),
        database = os.getenv("DB_NAME"),
        table_name = os.getenv("DB_TABLE"),
        schema_name = os.getenv("schema_name"),
        embed_dim=3072      
    )
def setup_chat_store():
    return PGVectorStore.from_params(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DATABASE_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        table_name="chat_messages", 
        schema_name=os.getenv("schema_name", "public"),
        embed_dim=3072      
    )

