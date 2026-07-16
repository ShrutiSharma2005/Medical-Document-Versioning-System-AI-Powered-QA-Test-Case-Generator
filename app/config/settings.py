import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    
    # SQLite Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./tri9t_ai.db"
    
    # MongoDB Configuration
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "tri9t_ai"
    MONGO_COLLECTION: str = "generated_testcases"
    
    # Groq API Configuration
    GROQ_API_KEY: str = ""
    
    # Preferred LLM model
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
