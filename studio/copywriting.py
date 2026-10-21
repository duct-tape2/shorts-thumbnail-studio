"""Conservative, inspectable Korean editorial rules. No LLM or network calls."""
import json
import re
from .paths import ASSETS


def compact(s):
    return re.sub(r'\s+', '', s)


def clean(s):
    return re.sub(r'\s+', ' ', s).strip()


def complete_sentence(s):
    s = clean(s)
    if len(s) < 9:
        return False
    if re.search(r'(?:[가-힣]+)(이|가|은|는|을|를|에서|으로|하고|하면|인데|보다|때문에)[.!?…]*$', s):
        return False
    return bool(re.search(r'(?:다|요|까|죠|세요|십시오|주의|확인|금지|필수|중요|방법|이유|습관|차이)[.!?…]*$', s))


def plan_copy(title, subtitle, all_text):
    rules = json.loads((ASSETS / 'copy_rules.json').read_text(encoding='utf-8'))
    hay = compact(title)
    found = None
    def matches(k):
        if len(k)==1:
            return bool(re.search(r'(^|\s)'+re.escape(k)+r'($|\s|[은는이가을를도,.!?])',title))
        return compact(k) in hay
    for rule in rules:
        if all(any(matches(k) for k in group) for group in rule['match']):
            found = rule
            break
    warnings = []
    changed = False
    if found:
        aux = found['aux']
        # The original full subtitle is preferred when useful, but fragments are never published.
        if complete_sentence(subtitle) and 9 <= len(subtitle) <= 40:
            caption = clean(subtitle)
        else:
            caption = found['caption']
            changed = True
        emphasis = next((k for k in found['emphasis'] if k in title), '')
        rule_id = found['id']
    else:
        words = clean(title).split()
        topic = next((w.strip(',.!?') for w in words if len(w.strip(',.!?')) >= 2), '')
        if complete_sentence(subtitle):
            caption = clean(subtitle)
            aux = topic + ' 체크 포인트'
        else:
            # A question from the headline is safer than inventing a medical/financial conclusion.
            caption = clean(title)
            aux = topic + ' 무엇이 다를까?'
            changed = True
        emphasis = topic
        rule_id = 'headline-fallback'
        warnings.append('등록되지 않은 주제입니다. 문구를 확인해 주세요.')
    if not emphasis or emphasis not in title:
        emphasis = clean(title).split()[0] if title.strip() else ''
    if not title.strip():
        warnings.append('제목을 읽지 못했습니다. 제목 입력이 필요합니다.')
    return dict(aux=aux, caption=caption, emphasis=emphasis, rule=rule_id,
                copy_repaired=changed, warnings=warnings)


def safe_filename(title):
    s = re.sub(r'[^\w\s가-힣]', '', title, flags=re.UNICODE).replace('_', '')
    s = clean(s).strip('. ')[:110]
    if not s:
        raise ValueError('저장할 제목이 없습니다.')
    if s.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        s += ' 썸네일'
    return s + '.png'
