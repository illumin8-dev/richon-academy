"""Draft/policy contract checks. No external requests or personal data."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / 'policy_drafts' / 'member-info-v1'


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.meta, self.refs, self.text, self.tags = {}, [], [], []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        values = dict(attrs)
        if tag == 'meta':
            self.meta[values.get('name')] = values.get('content')
        if 'href' in values:
            self.refs.append(values['href'])

    def handle_data(self, data):
        self.text.append(data)


def test_documents_stay_drafts_and_local_links_resolve():
    assert sorted(p.name for p in DRAFTS.glob('*.html')) == ['privacy.html', 'terms.html']
    for path in DRAFTS.glob('*.html'):
        doc = Document(path.read_text())
        assert doc.meta['policy-status'] == 'draft'
        assert doc.meta['policy-version'] == 'member-info-v1'
        assert doc.meta['robots'] == 'noindex,nofollow'
        assert not {'script', 'form', 'input', 'iframe'} & set(doc.tags)
        for ref in doc.refs:
            assert ref in ('terms.html', 'privacy.html')
            assert (DRAFTS / ref).is_file()
        text = ''.join(doc.text)
        assert '시행 전' in text and '032-236-8944' in text
        assert '[확정 후 기재]' in text
        assert '010-0000-0000' not in text and 'richon@richon.co.kr' not in text


def test_privacy_matches_approved_notice_without_unapproved_claims():
    privacy = (DRAFTS / 'privacy.html').read_text()
    notice = (ROOT / 'signup_views.py').read_text()
    for phrase in ('이름', '휴대전화번호', '이메일', '선택 / 연령대·성별',
                   '상담 내용 준비 및 상담 진행', '회원 서비스 안내 및 강의자료 발송',
                   '선택정보 제공에 동의하지 않아도', '만 14세 이상', '동의 버전·시점'):
        assert phrase in privacy and phrase in notice
    for phrase in ('Google Cloud', 'Neon', 'Cloudflare', '공식 이메일', '시행일',
                   '본인인증', '세션', '간편로그인', '직접 수집·저장하지 않습니다', '광고성 정보 수신 동의로 취급하지 않습니다'):
        assert phrase in privacy
    assert '만 19세 이상' not in privacy
    assert '생년월일은 수집하지 않습니다' in privacy
    assert '회원 관리와 상담에 필요한 정보를 수집합니다.' in notice


def test_terms_changes_are_bounded_to_approved_membership_amendments():
    text = ''.join(Document((DRAFTS / 'terms.html').read_text()).text)
    assert '전체 약관을 대체하지 않습니다' in text
    assert '주식회사 리치온아카데미' not in text
    assert '서비스 전용 비밀번호를 별도로 설정하게 하거나 수집하지 않습니다' in text
    assert '자기확인' in text and '자동 통합하지 않습니다' in text
    assert '선택정보 제공을 거부하여도' in text
    assert '결제 인증정보' in text and '임의로 변경하지 않습니다' in text


def test_release_checklist_keeps_unresolved_facts_and_no_runtime_draft_copy():
    checklist = (DRAFTS / 'README.md').read_text()
    for phrase in ('공식 이메일', '로그·백업 보유기간', '운영 DB009', '메인 로그인 버튼 계속 비노출',
                   '전체 약관 대체본이 아니다', 'STEP6', '일반 공개 별도 승인'):
        assert phrase in checklist
    docker = (ROOT / 'Dockerfile.portal').read_text()
    assert 'COPY backend/policy_drafts' not in docker
    assert not any(line.strip() == '!backend/policy_drafts/' for line in (ROOT / 'Dockerfile.portal.dockerignore').read_text().splitlines())
