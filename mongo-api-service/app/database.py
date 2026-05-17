from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

client: AsyncIOMotorClient = None


async def connect():
    global client
    log.info(f"Connecting to MongoDB at {settings.MONGO_URI}")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    await client.admin.command("ping")
    log.info("MongoDB connection established")


async def disconnect():
    global client
    if client:
        client.close()
        log.info("MongoDB connection closed")


def get_db():
    return client[settings.MONGO_DB]
