from app.schemas.workflow import NoticeDraftRequest
from app.services.llm_service import get_llm_service


def generate_notice_draft(req: NoticeDraftRequest) -> str:
    llm = get_llm_service()
    key_points = "\n".join(f"- {p}" for p in req.key_points) or "- (핵심 내용을 입력해주세요)"
    prompt = (
        f"'{req.audience}'를 대상으로 하는 '{req.topic}' 관련 공지문을 작성해줘.\n"
        f"어투: {req.tone}\n"
        f"반드시 포함할 핵심 내용:\n{key_points}\n\n"
        "제목, 본문, 문의처 안내 형식을 갖춘 완성된 공지문 초안으로 작성해줘."
    )
    return llm.chat([{"role": "user", "content": prompt}])
