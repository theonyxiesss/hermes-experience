"""
Score / Filter — компонент "обычный код" из архитектуры JobHunter.

Оценивает вакансию на соответствие критериям пользователя ПОЛНОСТЬЮ детерминированно,
по правилам из references/criteria.json. Никакого обращения к ИИ здесь нет и не будет —
это чистый пайплайн (regex/подсчёт совпадений/арифметика), быстрый и бесплатный.

Роль в общем workflow (см. run.py): это ПЕРВЫЙ, дешёвый фильтр — отсекает явный мусор
(красные флаги, чёрный список, исключённые роли/стек) ДО того, как вакансия попадёт
в LLM Gateway. Только вакансии, прошедшие этот фильтр, уходят на LLM Task
(vacancy_fit / cv_match в llm_gateway.py) — так основная масса вакансий обрабатывается
бесплатно, а модель тратится только на действительно неоднозначные случаи.

Формат ответа: {"score": 0-100, "reason": "...", "red_flag": bool}
"""

import json
import re
from pathlib import Path
from typing import Optional

CRITERIA_FILE = Path(__file__).resolve().parent.parent / "references" / "criteria.json"


def load_criteria() -> dict:
    if not CRITERIA_FILE.exists():
        raise FileNotFoundError(
            f"{CRITERIA_FILE} не найден — заполните references/criteria.json перед запуском"
        )
    return json.loads(CRITERIA_FILE.read_text(encoding="utf-8"))


def _text_of(vacancy: dict) -> str:
    return f"{vacancy.get('title', '')} {vacancy.get('description', '')}".lower()


def _parse_salary_number(salary_str: str) -> Optional[int]:
    """Достаёт минимальное число из строки вида '200000-300000 RUR' или '150000 RUR'."""
    numbers = re.findall(r"\d+", (salary_str or "").replace(" ", ""))
    if not numbers:
        return None
    return int(numbers[0])


def rule_based_score(vacancy: dict, criteria: dict) -> dict:
    text = _text_of(vacancy)
    company = (vacancy.get("company") or "").lower()
    weights = criteria.get("score_weights", {"role_match": 35, "keyword_match": 30, "salary_match": 20, "location_match": 15})

    # 1. Красные флаги и чёрный список — сразу 0
    for flag in criteria.get("red_flag_keywords", []):
        if flag.lower() in text:
            return {"score": 0, "reason": f"красный флаг: «{flag}»", "red_flag": True}
    for blacklisted in criteria.get("blacklist_companies", []):
        if blacklisted.lower() in company:
            return {"score": 0, "reason": f"компания в чёрном списке: {blacklisted}", "red_flag": True}

    # 2. Явно исключённые роли/ключевые слова — сразу 0
    for excl in criteria.get("roles_exclude", []) + criteria.get("keywords_exclude", []):
        if excl.lower() in text:
            return {"score": 0, "reason": f"исключающий признак: «{excl}»", "red_flag": True}

    score = 0.0
    reasons = []

    # 3. Совпадение по желаемым ролям
    roles_include = criteria.get("roles_include", [])
    if roles_include:
        hit = any(r.lower() in text for r in roles_include)
        if hit:
            score += weights.get("role_match", 35)
            reasons.append("роль совпадает")
    else:
        score += weights.get("role_match", 35) * 0.5  # нейтрально, если роли не заданы

    # 4. Совпадение по ключевым словам стека
    kws = criteria.get("keywords_include", [])
    if kws:
        hits = sum(1 for kw in kws if kw.lower() in text)
        frac = hits / len(kws)
        score += weights.get("keyword_match", 30) * frac
        if hits:
            reasons.append(f"{hits}/{len(kws)} ключевых слов")

    # 5. Зарплата
    salary_min = criteria.get("salary_min")
    if salary_min:
        found = _parse_salary_number(vacancy.get("salary", ""))
        if found is None:
            score += weights.get("salary_match", 20) * 0.5  # зарплата не указана — нейтрально
        elif found >= salary_min:
            score += weights.get("salary_match", 20)
            reasons.append("зарплата подходит")
        else:
            reasons.append(f"зарплата ниже минимума ({found} < {salary_min})")
    else:
        score += weights.get("salary_match", 20) * 0.5

    # 6. Локация / удалёнка
    #
    # ПРАВКА (2026-08-20): раньше проверка "remote"/"удал" в тексте была ВЛОЖЕНА
    # внутрь `if locations:` — то есть если locations пуст (ровно тот случай,
    # когда пользователь хочет "любая гео, лишь бы remote"), удалённость вообще
    # никогда не проверялась и вакансия просто получала нейтральные полбалла,
    # даже если в тексте явно написано "remote"/"удалённо". Теперь проверка
    # удалённости не зависит от того, задан ли locations.
    locations = [l.lower() for l in criteria.get("locations", [])]
    remote_ok = criteria.get("remote_ok", True)
    loc_hit = any(loc in text for loc in locations) if locations else False
    remote_hit = remote_ok and ("remote" in text or "удал" in text)
    if loc_hit or remote_hit:
        score += weights.get("location_match", 15)
        reasons.append("локация подходит" if loc_hit else "удалёнка подходит")
    else:
        score += weights.get("location_match", 15) * 0.5

    return {
        "score": min(100, round(score)),
        "reason": "; ".join(reasons) if reasons else "нейтральная оценка",
        "red_flag": False,
    }


def score_vacancy(vacancy: dict) -> dict:
    """Единственный вход в этот модуль. Чистая функция, без побочных эффектов и без ИИ."""
    criteria = load_criteria()
    return rule_based_score(vacancy, criteria)


# Вакансии с rule-score ниже этого порога не имеет смысла отправлять в LLM Gateway —
# они либо явно не подходят, либо слишком мало данных совпало. run.py использует эту
# константу, чтобы не тратить LLM-вызовы на заведомо слабые кандидаты.
LOW_BAR_FOR_LLM = 40


if __name__ == "__main__":
    demo_vacancy = {
        "title": "Python Developer",
        "company": "Acme",
        "salary": "250000-300000 RUR",
        "description": "Ищем Python-разработчика с опытом Django и PostgreSQL, удалённо",
    }
    print(json.dumps(score_vacancy(demo_vacancy), ensure_ascii=False, indent=2))
