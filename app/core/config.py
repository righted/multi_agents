import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-before-deploy")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_days: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))


settings = Settings()
