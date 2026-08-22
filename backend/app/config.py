"""애플리케이션 설정.

모든 설정은 환경변수(.env)에서 읽는다. 코드에 시크릿을 두지 않는다.
필요한 환경변수 목록은 저장소 루트의 .env.example 참고.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://dev:dev@localhost:5432/settlement_hub"

    # Auth (Phase 4에서 사용)
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # AI (Phase 6에서 사용)
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5"

    # 외부 공공 API (Phase 4에서 사용)
    nts_api_key: str = ""  # 국세청 사업자등록 상태조회 (공공데이터포털 serviceKey)
    kasi_api_key: str = ""  # 한국천문연구원 특일 정보 (optional)

    # 파일 저장
    upload_dir: str = "./uploads"

    # 운영(HTTPS) 배포에서 True로 — refresh 쿠키에 Secure 속성을 붙인다
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
